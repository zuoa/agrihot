"""Minute-based cron schedule, owned by the existing worker process."""
import asyncio
import logging
from datetime import datetime, timezone

from ..database import SessionLocal
from ..models import PipelineState, utcnow
from . import job_runner, runtime_settings
from .cron_schedule import daily_cron, matches
from .daily_service import business_tz

log = logging.getLogger(__name__)


async def tick(now=None):
    current = (now or datetime.now(business_tz())).astimezone(business_tz()).replace(second=0, microsecond=0)
    slot = current.astimezone(timezone.utc).isoformat()
    async with SessionLocal() as session:
        await runtime_settings.load(session)
        if not runtime_settings.get("specials_enabled"):
            return
        expression = runtime_settings.get("specials_cron")
        if not matches(expression, current):
            return
        state = await session.get(PipelineState, "specials:last_scheduled_slot")
        if state and state.value == slot:
            return
        if state is None and matches(daily_cron(runtime_settings.get("specials_time")), current):
            legacy = await session.get(PipelineState, "specials:last_scheduled_day")
            if legacy and legacy.value == current.date().isoformat():
                return
    if await job_runner.spawn("specials_generate"):
        async with SessionLocal() as session:
            state = await session.get(PipelineState, "specials:last_scheduled_slot")
            if not state:
                state = PipelineState(key="specials:last_scheduled_slot", value="")
                session.add(state)
            state.value, state.updated_at = slot, utcnow()
            await session.commit()


async def loop():
    while True:
        try:
            await tick()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("specials schedule failed")
        await asyncio.sleep(60)


def start_special_scheduler():
    return asyncio.create_task(loop(), name="specials-scheduler")
