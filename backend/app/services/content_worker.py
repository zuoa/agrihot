"""Runs queued full-text fetches outside the API process.

The API writes `job:fetch_content` as queued. This process claims that row
and runs the handler, so a 60s origin fetch never holds an API connection.
Search indexing stays in the API process.
"""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress

from sqlalchemy import select

from ..database import SessionLocal, ensure_schema
from ..models import PipelineState
from . import job_runner, runtime_settings, watchlist_service

log = logging.getLogger(__name__)

POLL_SECONDS = 2
_JOB_PREFIX = "job:"


async def _claim(name: str) -> dict | None:
    if job_runner.is_running(name):
        return None
    async with SessionLocal() as session:
        row = await session.get(PipelineState, f"{_JOB_PREFIX}{name}")
        if row is None or not row.value:
            return None
        try:
            data = json.loads(row.value)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict) or data.get("status") != "queued":
            return None
        params = data.get("params") or {}
        row.value = ""
        await session.commit()
        return params


async def drain_once() -> bool:
    claimed = False
    for name in job_runner.WORKER_JOBS:
        params = await _claim(name)
        if params is None:
            continue
        claimed = True
        await job_runner.run(name, params)
    return claimed


async def _recover_interrupted() -> None:
    """A restart drops an in-memory run. Put it back on the queue."""
    async with SessionLocal() as session:
        rows = (await session.execute(
            select(PipelineState).where(PipelineState.key.like(f"{_JOB_PREFIX}%"))
        )).scalars().all()
        for row in rows:
            try:
                data = json.loads(row.value or "")
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and data.get("status") == "running":
                data["status"] = "queued"
                row.value = json.dumps(data, ensure_ascii=False, default=str)
        await session.commit()


async def serve() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    await ensure_schema()
    async with SessionLocal() as session:
        await runtime_settings.load(session)
        await watchlist_service.load_from_db(session)
        await session.commit()
    await _recover_interrupted()
    from .content_scheduler import start_content_scheduler
    scheduler = start_content_scheduler()
    log.info("content worker ready")
    try:
        await _serve_until_stopped()
    finally:
        scheduler.cancel()
        with suppress(asyncio.CancelledError):
            await scheduler


async def _serve_until_stopped() -> None:
    while True:
        try:
            if not await drain_once():
                await asyncio.sleep(POLL_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("content worker tick failed")
            await asyncio.sleep(POLL_SECONDS)


def main() -> None:
    asyncio.run(serve())


if __name__ == "__main__":
    main()
