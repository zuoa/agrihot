"""Runtime overrides for operational knobs.

Env / .env remains the source of secrets and bootstrap defaults. Operators can
hot-patch an allowlisted subset via the admin API; those values live in
`pipeline_state.settings_overrides` and overlay the env defaults in-process.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import PipelineState, utcnow

log = logging.getLogger(__name__)

STATE_KEY = "settings_overrides"

# key -> (python type, min, max)  min/max only for int
OVERRIDABLE: dict[str, tuple[type, int | None, int | None]] = {
    "selection_threshold": (int, 0, 100),
    "daily_top_n": (int, 1, 50),
    "daily_generate_enabled": (bool, None, None),
    "daily_generate_time": (str, None, None),
    "literature_fetch_enabled": (bool, None, None),
    "literature_fetch_time": (str, None, None),
    "literature_lookback_days": (int, 0, 30),
    "literature_bootstrap_days": (int, 1, 90),
    "literature_max_new_per_run": (int, 1, 500),
    "content_fetch_enabled": (bool, None, None),
}

_overrides: dict[str, Any] = {}


def reset() -> None:
    """Drop in-memory overlays (tests). Next get() falls back to env."""
    _overrides.clear()


def parse_hhmm(value: str, default: tuple[int, int] = (20, 0)) -> tuple[int, int]:
    try:
        hour_s, minute_s = str(value).split(":", 1)
        hour, minute = int(hour_s), int(minute_s)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
    except (ValueError, AttributeError):
        pass
    return default


def _valid_hhmm(value: str) -> bool:
    try:
        hour_s, minute_s = str(value).split(":", 1)
        hour, minute = int(hour_s), int(minute_s)
        return 0 <= hour <= 23 and 0 <= minute <= 59
    except (ValueError, AttributeError):
        return False


def _coerce(key: str, raw: Any) -> Any:
    typ, lo, hi = OVERRIDABLE[key]
    if typ is bool:
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str) and raw.lower() in ("true", "false", "1", "0"):
            return raw.lower() in ("true", "1")
        raise ValueError(f"{key} 应为布尔值")
    if typ is int:
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key} 应为整数") from exc
        if lo is not None and value < lo:
            raise ValueError(f"{key} 不能小于 {lo}")
        if hi is not None and value > hi:
            raise ValueError(f"{key} 不能大于 {hi}")
        return value
    # str — schedule times
    text = str(raw).strip()
    if key.endswith("_time") and not _valid_hhmm(text):
        raise ValueError(f"{key} 应为 HH:MM")
    return text


def get(key: str) -> Any:
    """Effective value: DB overlay if present, otherwise env default."""
    if key in _overrides:
        try:
            return _coerce(key, _overrides[key])
        except ValueError:
            log.warning("ignoring invalid override %s=%r", key, _overrides[key])
    return getattr(settings, key)


async def load(session: AsyncSession) -> dict[str, Any]:
    """Hydrate the in-memory overlay from DB. Called at startup and after writes."""
    global _overrides
    row = await session.get(PipelineState, STATE_KEY)
    data: dict[str, Any] = {}
    if row and row.value:
        try:
            parsed = json.loads(row.value)
            if isinstance(parsed, dict):
                data = {k: v for k, v in parsed.items() if k in OVERRIDABLE}
        except json.JSONDecodeError:
            log.warning("settings_overrides is not valid JSON, ignoring")
    _overrides = data
    return dict(_overrides)


def snapshot() -> dict[str, dict[str, Any]]:
    """writable key -> {value, source} for the admin settings page."""
    out: dict[str, dict[str, Any]] = {}
    for key in OVERRIDABLE:
        if key in _overrides:
            try:
                out[key] = {"value": _coerce(key, _overrides[key]), "source": "override"}
                continue
            except ValueError:
                pass
        out[key] = {"value": getattr(settings, key), "source": "env"}
    return out


def readonly_snapshot() -> dict[str, Any]:
    return {
        "deepseek_configured": bool(settings.deepseek_api_key),
        "jina_configured": bool(settings.jina_api_key),
        "openalex_configured": bool(settings.openalex_api_key),
        "deepseek_model": settings.deepseek_model,
        "openalex_mailto": settings.openalex_mailto,
        "daily_timezone": settings.daily_timezone,
        "ingest_rate_limit": settings.ingest_rate_limit,
    }


async def patch(session: AsyncSession, updates: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Merge allowlisted updates into DB + memory. Unknown keys are rejected."""
    unknown = [k for k in updates if k not in OVERRIDABLE]
    if unknown:
        raise ValueError(f"不可修改的配置项: {', '.join(unknown)}")
    coerced: dict[str, Any] = {}
    for key, raw in updates.items():
        if raw is None:
            continue
        coerced[key] = _coerce(key, raw)
    merged = dict(_overrides)
    merged.update(coerced)
    row = await session.get(PipelineState, STATE_KEY)
    payload = json.dumps(merged, ensure_ascii=False)
    if row is None:
        session.add(PipelineState(key=STATE_KEY, value=payload, updated_at=utcnow()))
    else:
        row.value = payload
        row.updated_at = utcnow()
    await session.flush()
    _overrides.clear()
    _overrides.update(merged)
    return snapshot()


def next_run_at(hhmm: str, tz_name: str, *, default: tuple[int, int] = (20, 0)) -> datetime:
    """Next fire instant (UTC) for a daily HH:MM in the given timezone."""
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = timezone.utc
    now = datetime.now(tz)
    hour, minute = parse_hhmm(hhmm, default)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target.astimezone(timezone.utc)
