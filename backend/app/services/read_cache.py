"""Short cache for public reads that many requests ask for at once.

A theme page and a crawler both repeat taxonomy, facets, and item lists.
Caching the finished value lets those requests share one database checkout
and leaves pooled connections for article detail.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from ..database import SessionLocal, get_session

log = logging.getLogger(__name__)

TTL_SECONDS = 30
STALE_SECONDS = 120
_MAX_ENTRIES = 256
_slots = asyncio.Semaphore(4)
# key -> (fresh_until, stale_until, value)
_values: dict[tuple, tuple[float, float, object]] = {}
_inflight: dict[tuple, asyncio.Task] = {}


def reset() -> None:
    _values.clear()
    for task in list(_inflight.values()):
        if not task.done():
            task.cancel()
    _inflight.clear()


def invalidate(*prefixes: str) -> None:
    if not prefixes:
        reset()
        return
    prefix_set = set(prefixes)
    for key in [k for k in _values if k and k[0] in prefix_set]:
        _values.pop(key, None)


def _start_refresh(key: tuple, load: Callable[..., Awaitable[object]], ttl: float, stale_ttl: float) -> asyncio.Task:
    task = _inflight.get(key)
    if task is None or task.done():
        task = asyncio.create_task(_load(key, load, ttl, stale_ttl))
        _inflight[key] = task

        def _cleanup(done_task: asyncio.Task) -> None:
            if _inflight.get(key) is done_task:
                _inflight.pop(key, None)
            if not done_task.cancelled():
                exc = done_task.exception()
                if exc is not None:
                    log.debug("read_cache refresh failed for %s: %s", key[0] if key else key, exc)

        task.add_done_callback(_cleanup)
    return task


async def get(
    key: tuple,
    load: Callable[..., Awaitable[object]],
    ttl: float = TTL_SECONDS,
    stale_ttl: float = STALE_SECONDS,
):
    now = time.monotonic()
    cached = _values.get(key)
    if cached:
        fresh_until, stale_until, value = cached
        if fresh_until > now:
            return value
        if stale_until > now:
            # Serve warm stale data immediately while refreshing once in the background.
            _start_refresh(key, load, ttl, stale_ttl)
            return value
    task = _start_refresh(key, load, ttl, stale_ttl)
    return await asyncio.shield(task)


def _session_factory():
    """Use the app's session override in tests; otherwise the process pool."""
    from ..main import app
    override = app.dependency_overrides.get(get_session)
    if override is None:
        return SessionLocal
    return override


async def _load(key: tuple, load: Callable[..., Awaitable[object]], ttl: float, stale_ttl: float):
    async with _slots:
        factory = _session_factory()
        if factory is SessionLocal:
            async with SessionLocal() as owned:
                value = await load(owned)
        else:
            async for owned in factory():
                value = await load(owned)
                break
    return _store(key, value, ttl, stale_ttl)


def _store(key: tuple, value, ttl: float, stale_ttl: float):
    now = time.monotonic()
    _values[key] = (now + ttl, now + ttl + max(0.0, stale_ttl), value)
    if len(_values) > _MAX_ENTRIES:
        oldest = min(_values, key=lambda item: _values[item][0])
        _values.pop(oldest, None)
    return value
