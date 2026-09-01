"""OpenAlex 文献定时拉取：每天业务时区 literature_fetch_time 跑一轮。

与日报调度独立；失败只记日志。新建条目在提交后走 enrich_and_score
（论文跳过 Jina，做评分 + 结构化卡片）。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from ..config import settings
from ..database import SessionLocal
from . import content_service, daily_service, openalex_service

log = logging.getLogger(__name__)

_DEFAULT_TIME = (7, 30)


def _parse_fetch_time() -> tuple[int, int]:
    try:
        hour_s, minute_s = settings.literature_fetch_time.split(":", 1)
        hour, minute = int(hour_s), int(minute_s)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
    except (ValueError, AttributeError):
        pass
    log.warning(
        "invalid literature_fetch_time %r, falling back to %02d:%02d",
        settings.literature_fetch_time, *_DEFAULT_TIME,
    )
    return _DEFAULT_TIME


def _seconds_until_next_run(now: datetime) -> float:
    hour, minute = _parse_fetch_time()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def run_once() -> dict:
    """Fetch + ingest + score/card newly created papers. Safe to call from admin/script."""
    stats: dict = {
        "fetched": 0, "screened_out": 0, "created": 0,
        "duplicate": 0, "errors": 0, "from_date": None, "truncated": False,
    }
    created_ids: list[int] = []
    try:
        async with SessionLocal() as session:
            raw = await openalex_service.poll_and_ingest(session)
            created_ids = list(raw.pop("created_ids", []))
            stats.update(raw)
            await session.commit()
    except Exception:
        log.exception("OpenAlex literature fetch failed")
        stats["errors"] = stats.get("errors", 0) + 1
        return stats

    for item_id in created_ids:
        try:
            await content_service.enrich_and_score(item_id)
        except Exception:
            log.exception("enrich/score failed for OpenAlex item %s", item_id)
    return stats


async def _loop() -> None:
    while True:
        await asyncio.sleep(_seconds_until_next_run(datetime.now(daily_service.business_tz())))
        await run_once()


def start_literature_scheduler() -> asyncio.Task:
    task = asyncio.create_task(_loop(), name="literature-scheduler")
    log.info(
        "literature scheduler started (fetch at %s %s)",
        settings.literature_fetch_time, settings.daily_timezone,
    )
    return task
