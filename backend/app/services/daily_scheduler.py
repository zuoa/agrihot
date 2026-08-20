"""每日日报定时生成：一个 asyncio 后台任务，每天到点生成当天日报。

内嵌在 FastAPI lifespan 中启停（单容器部署，无需外部 cron）。
生成失败只记日志、不影响下一次调度；DeepSeek 不可用时走
daily_service 的降级逻辑，保证日报照常产出。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta

from ..config import settings
from ..database import SessionLocal
from . import daily_service

log = logging.getLogger(__name__)

_DEFAULT_TIME = (20, 0)


def _parse_generate_time() -> tuple[int, int]:
    """Parse settings.daily_generate_time ("HH:MM"); fall back to 20:00."""
    try:
        hour_s, minute_s = settings.daily_generate_time.split(":", 1)
        hour, minute = int(hour_s), int(minute_s)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
    except (ValueError, AttributeError):
        pass
    log.warning(
        "invalid daily_generate_time %r, falling back to %02d:%02d",
        settings.daily_generate_time, *_DEFAULT_TIME,
    )
    return _DEFAULT_TIME


def _seconds_until_next_run(now: datetime) -> float:
    hour, minute = _parse_generate_time()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def _run_once() -> None:
    today = date.today()
    try:
        async with SessionLocal() as session:
            daily = await daily_service.generate_daily(session, today)
            await session.commit()
        if daily is None:
            log.info("daily %s skipped: no items ingested today", today)
    except Exception:
        log.exception("daily generation failed for %s", today)


async def _loop() -> None:
    while True:
        await asyncio.sleep(_seconds_until_next_run(datetime.now()))
        await _run_once()


def start_daily_scheduler() -> asyncio.Task:
    """Create the background task; cancelled from the app lifespan on shutdown."""
    task = asyncio.create_task(_loop(), name="daily-scheduler")
    log.info("daily scheduler started (generate at %s local)", settings.daily_generate_time)
    return task
