"""Literature watchlist: DB overlay with yaml as factory default.

The packaged `app/watchlist.yaml` is the out-of-the-box subscription. Admin PUT
persists a full replacement document in `pipeline_state.watchlist` so container
rebuilds keep operator edits.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import PipelineState, utcnow

log = logging.getLogger(__name__)

STATE_KEY = "watchlist"

_current: dict[str, Any] | None = None


def reset() -> None:
    global _current
    _current = None


def _default_path() -> Path:
    if settings.watchlist_path:
        return Path(settings.watchlist_path)
    return Path(__file__).resolve().parent.parent / "watchlist.yaml"


def load_yaml() -> dict[str, Any]:
    path = _default_path()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError:
        log.warning("watchlist not found at %s", path)
        return {}
    except Exception:
        log.exception("failed to load watchlist %s", path)
        return {}
    return data if isinstance(data, dict) else {}


def get_watchlist() -> dict[str, Any]:
    if _current is not None:
        return _current
    return load_yaml()


def validate(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize and reject obviously broken documents. Returns a clean dict."""
    if not isinstance(data, dict):
        raise ValueError("关注面必须是对象")
    directions_in = data.get("directions") or []
    journals_in = data.get("journals") or []
    authors_in = data.get("authors") or []
    prescreen_in = data.get("prescreen") or []
    if not isinstance(directions_in, list) or not isinstance(journals_in, list):
        raise ValueError("directions / journals 必须是数组")
    if not isinstance(authors_in, list) or not isinstance(prescreen_in, list):
        raise ValueError("authors / prescreen 必须是数组")

    directions: list[dict[str, Any]] = []
    for raw in directions_in:
        if not isinstance(raw, dict) or not str(raw.get("name") or "").strip():
            raise ValueError("每个方向需要 name")
        queries = raw.get("queries") or []
        if not isinstance(queries, list):
            raise ValueError(f"方向 {raw.get('name')} 的 queries 必须是数组")
        directions.append({
            "name": str(raw["name"]).strip(),
            "queries": [str(q).strip() for q in queries if str(q).strip()],
        })

    journals: list[dict[str, Any]] = []
    for raw in journals_in:
        if not isinstance(raw, dict) or not str(raw.get("issn") or "").strip():
            raise ValueError("每种期刊需要 issn")
        journals.append({
            "name": str(raw.get("name") or "").strip(),
            "issn": str(raw["issn"]).strip(),
        })

    authors: list[dict[str, Any]] = []
    for raw in authors_in:
        if not isinstance(raw, dict):
            raise ValueError("authors 项必须是对象")
        aid = str(raw.get("openalex_id") or raw.get("id") or "").strip()
        authors.append({
            "name": str(raw.get("name") or "").strip(),
            "openalex_id": aid,
        })

    prescreen = [str(t).strip() for t in prescreen_in if str(t).strip()]
    return {
        "directions": directions,
        "journals": journals,
        "authors": authors,
        "prescreen": prescreen,
    }


async def load_from_db(session: AsyncSession) -> dict[str, Any]:
    global _current
    row = await session.get(PipelineState, STATE_KEY)
    if row and row.value:
        try:
            parsed = json.loads(row.value)
            _current = validate(parsed) if isinstance(parsed, dict) else load_yaml()
        except (json.JSONDecodeError, ValueError):
            log.warning("watchlist in DB is invalid, falling back to yaml")
            _current = load_yaml()
    else:
        _current = load_yaml()
    return _current


async def save(session: AsyncSession, data: dict[str, Any]) -> dict[str, Any]:
    global _current
    clean = validate(data)
    payload = json.dumps(clean, ensure_ascii=False)
    row = await session.get(PipelineState, STATE_KEY)
    if row is None:
        session.add(PipelineState(key=STATE_KEY, value=payload, updated_at=utcnow()))
    else:
        row.value = payload
        row.updated_at = utcnow()
    await session.flush()
    _current = clean
    return clean
