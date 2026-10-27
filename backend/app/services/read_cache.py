"""Short cache for public reads that many requests ask for at once.

A theme page and a crawler both repeat taxonomy, facets, and item lists.
Caching the finished value lets those requests share one database checkout
and leaves pooled connections for article detail.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

from ..database import SessionLocal, get_session

TTL_SECONDS = 30
_MAX_ENTRIES = 256
_slots = asyncio.Semaphore(4)
_values: dict[tuple, tuple[float, object]] = {}
_inflight: dict[tuple, asyncio.Task] = {}


def reset() -> None:
    _values.clear()
    _inflight.clear()


async def get(key: tuple, load: Callable[..., Awaitable[object]], ttl: float = TTL_SECONDS):
    now = time.monotonic()
    cached = _values.get(key)
    if cached and cached[0] > now:
        return cached[1]
    task = _inflight.get(key)
    if task is None:
        task = asyncio.create_task(_load(key, load, ttl))
        _inflight[key] = task
    try:
        return await asyncio.shield(task)
    finally:
        if _inflight.get(key) is task and task.done():
            _inflight.pop(key, None)


def _session_factory():
    """Use the app's session override in tests; otherwise the process pool."""
    from ..main import app
    override = app.dependency_overrides.get(get_session)
    if override is None:
        return SessionLocal
    return override


async def _load(key: tuple, load: Callable[..., Awaitable[object]], ttl: float):
    async with _slots:
        factory = _session_factory()
        if factory is SessionLocal:
            async with SessionLocal() as owned:
                value = await load(owned)
        else:
            async for owned in factory():
                value = await load(owned)
                break
    return _store(key, value, ttl)


def _store(key: tuple, value, ttl: float):
    _values[key] = (time.monotonic() + ttl, value)
    if len(_values) > _MAX_ENTRIES:
        oldest = min(_values, key=lambda item: _values[item][0])
        _values.pop(oldest, None)
    return value
