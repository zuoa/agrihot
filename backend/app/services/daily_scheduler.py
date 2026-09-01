"""每日日报定时生成：一个 asyncio 后台任务，每天到点生成当天日报。

内嵌在 FastAPI lifespan 中启停（单容器部署，无需外部 cron）。
调度时刻与「今天」的口径都按业务时区（settings.daily_timezone），
不受容器系统时区影响。生成失败只记日志、不影响下一次调度；
DeepSeek 不可用时走 daily_service 的降级逻辑，保证日报照常产出。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from ..config import settings
from . import daily_service, job_runner, runtime_settings

log = logging.getLogger(__name__)

_DEFAULT_TIME = (20, 0)


def _parse_generate_time() -> tuple[int, int]:
    """Parse effective daily_generate_time ("HH:MM"); fall back to 20:00."""
    value = str(runtime_settings.get("daily_generate_time"))
    parsed = runtime_settings.parse_hhmm(value, _DEFAULT_TIME)
    if parsed == _DEFAULT_TIME and runtime_settings.parse_hhmm(value, (99, 99)) == (99, 99):
        log.warning("invalid daily_generate_time %r, falling back to %02d:%02d", value, *_DEFAULT_TIME)
    return parsed


def _seconds_until_next_run(now: datetime) -> float:
    """`now` 须为业务时区的 aware 当前时刻。"""
    hour, minute = _parse_generate_time()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def _loop() -> None:
    while True:
        delay = _seconds_until_next_run(datetime.now(daily_service.business_tz()))
        await asyncio.sleep(min(delay, 60))
        if delay > 60:
            continue
        if not runtime_settings.get("daily_generate_enabled"):
            continue
        try:
            await job_runner.run("daily_generate")
        except job_runner.JobBusy:
            log.info("daily generate already running, skip this tick")
        except Exception:
            log.exception("daily generation failed")


def start_daily_scheduler() -> asyncio.Task:
    """Create the background task; cancelled from the app lifespan on shutdown."""
    task = asyncio.create_task(_loop(), name="daily-scheduler")
    log.info(
        "daily scheduler started (generate at %s %s)",
        runtime_settings.get("daily_generate_time"), settings.daily_timezone,
    )
    return task
