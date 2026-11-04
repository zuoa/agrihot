"""Worker-owned schedule for fixed sources, with live configuration refresh."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from ..database import SessionLocal
from . import job_runner, runtime_settings

log = logging.getLogger(__name__)


async def tick() -> None:
    async with SessionLocal() as session:
        await runtime_settings.load(session)
    if runtime_settings.get("sources_fetch_enabled"):
        from .source_service import list_sources
        from .source_adapters import parse_date
        now = datetime.now(timezone.utc)
        for source in await list_sources():
            checked = parse_date(source["state"].get("last_checked_at", ""))
            if source["enabled"] and (checked is None or now >= checked + timedelta(minutes=source["interval_minutes"])):
                await job_runner.spawn("sources_fetch", {"force": False})
                break


async def loop() -> None:
    while True:
        try:
            await tick()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("fixed source schedule failed")
        await asyncio.sleep(60)


def start_source_scheduler():
    return asyncio.create_task(loop(), name="sources-scheduler")
