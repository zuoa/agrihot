"""无全文条目的定时回补：content_fetch_enabled 开启时周期性跑 fetch_content。

入库时的 BackgroundTasks 只覆盖新建非论文条目；关掉开关期间积压的、
以及 seed / 脚本写入的旧数据不会被那条路径扫到。这个循环补上缺口。
论文仍不抓（Jina 对 DOI 落地页易 403）。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from ..config import settings
from . import job_runner, runtime_settings

log = logging.getLogger(__name__)

INTERVAL_SECONDS = 10 * 60
_START_DELAY = 5

_next_run: datetime | None = None


def next_run_at() -> datetime:
    return _next_run or (datetime.now(timezone.utc) + timedelta(seconds=_START_DELAY))


async def _loop() -> None:
    global _next_run
    await asyncio.sleep(_START_DELAY)
    while True:
        if runtime_settings.get("content_fetch_enabled"):
            try:
                await job_runner.run("fetch_content", {})
            except job_runner.JobBusy:
                log.info("content fetch already running, skip this tick")
            except Exception:
                log.exception("content fetch tick failed")
        _next_run = datetime.now(timezone.utc) + timedelta(seconds=INTERVAL_SECONDS)
        await asyncio.sleep(INTERVAL_SECONDS)


def start_content_scheduler() -> asyncio.Task:
    global _next_run
    _next_run = datetime.now(timezone.utc) + timedelta(seconds=_START_DELAY)
    task = asyncio.create_task(_loop(), name="content-scheduler")
    log.info(
        "content fetch scheduler started (every %ss, timezone %s)",
        INTERVAL_SECONDS, settings.daily_timezone,
    )
    return task
