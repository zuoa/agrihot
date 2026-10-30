"""Once-a-day durable schedule, owned by the existing worker process."""
import asyncio
import logging
from datetime import datetime

from ..database import SessionLocal
from ..models import PipelineState, utcnow
from . import job_runner, runtime_settings
from .daily_service import business_tz

log = logging.getLogger(__name__)


async def tick(now=None):
    now = now or datetime.now(business_tz())
    async with SessionLocal() as session:
        await runtime_settings.load(session)
        if not runtime_settings.get("specials_enabled"):
            return
        hour, minute = runtime_settings.parse_hhmm(runtime_settings.get("specials_time"), (8, 30))
        if (now.hour, now.minute) < (hour, minute):
            return
        state = await session.get(PipelineState, "specials:last_scheduled_day")
        if state and state.value == now.date().isoformat():
            return
    if await job_runner.spawn("specials_generate"):
        async with SessionLocal() as session:
            state = await session.get(PipelineState, "specials:last_scheduled_day")
            if not state:
                state = PipelineState(key="specials:last_scheduled_day", value="")
                session.add(state)
            state.value, state.updated_at = now.date().isoformat(), utcnow()
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
