"""In-process job runner: named handlers, overlap lock, persisted status.

Single-container FastAPI: an in-memory set is enough to prevent overlapping
runs. Status is stored in `pipeline_state` (`job:{name}`) so the admin UI can
poll across requests.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import date, datetime, timezone
from typing import Any, Awaitable, Callable

from sqlalchemy import or_, select

from ..database import SessionLocal
from ..models import Item, PipelineState, utcnow

log = logging.getLogger(__name__)

Handler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]

JOB_LABELS = {
    "literature_fetch": "拉取文献",
    "daily_generate": "生成日报",
    "rescore_unscored": "补评未评分条目",
    "translate_abstracts": "补译外文摘要",
    "retag": "重切标签",
    "taxonomy_backfill": "回填主题分类",
    "fetch_content": "批量抓取全文",
    "specials_generate": "发现与更新热点专题",
}

JOB_NAMES = tuple(JOB_LABELS)
# Outbound full-text fetches. The API records them; the worker process runs them.
WORKER_JOBS = frozenset({"fetch_content", "specials_generate"})
# Unset (local and tests) keeps jobs in this process. Production API sets "api".
RUNS_JOBS = os.environ.get("AGRIHOT_PROCESS", "all") != "api"

_running: set[str] = set()


class JobBusy(Exception):
    def __init__(self, name: str):
        super().__init__(name)
        self.name = name


def reset() -> None:
    _running.clear()


def is_running(name: str) -> bool:
    return name in _running


def _state_key(name: str) -> str:
    return f"job:{name}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


async def _write_status(name: str, payload: dict[str, Any]) -> None:
    key = _state_key(name)
    async with SessionLocal() as session:
        row = await session.get(PipelineState, key)
        blob = _dumps(payload)
        if row is None:
            session.add(PipelineState(key=key, value=blob, updated_at=utcnow()))
        else:
            row.value = blob
            row.updated_at = utcnow()
        await session.commit()


async def _read_status(name: str) -> dict[str, Any]:
    idle = {
        "name": name,
        "label": JOB_LABELS.get(name, name),
        "status": "idle",
        "started_at": None,
        "finished_at": None,
        "stats": None,
        "error": None,
        "progress": None,
    }
    async with SessionLocal() as session:
        row = await session.get(PipelineState, _state_key(name))
        if row is None or not row.value:
            return idle
        try:
            data = json.loads(row.value)
        except json.JSONDecodeError:
            return idle
    if not isinstance(data, dict):
        return idle
    idle.update({k: data.get(k) for k in ("status", "started_at", "finished_at", "stats", "error", "progress")})
    if name in _running and idle["status"] != "queued":
        idle["status"] = "running"
    return idle


async def list_jobs() -> list[dict[str, Any]]:
    return [await _read_status(name) for name in JOB_NAMES]


async def get_job(name: str) -> dict[str, Any] | None:
    if name not in JOB_LABELS:
        return None
    return await _read_status(name)


async def set_progress(name: str, *, done: int, total: int) -> None:
    current = await _read_status(name)
    current["progress"] = {"done": done, "total": total}
    current["status"] = "running"
    await _write_status(name, current)


async def _execute(name: str, params: dict[str, Any]) -> dict[str, Any]:
    started = _now().isoformat()
    await _write_status(name, {
        "name": name, "label": JOB_LABELS.get(name, name),
        "status": "running", "started_at": started, "finished_at": None,
        "stats": None, "error": None, "progress": None,
        "params": params,
    })
    try:
        handler = HANDLERS[name]
        stats = await handler(params)
        finished = _now().isoformat()
        payload = {
            "name": name, "label": JOB_LABELS.get(name, name),
            "status": "ok", "started_at": started, "finished_at": finished,
            "stats": stats or {}, "error": None, "progress": None,
        }
        await _write_status(name, payload)
        return payload
    except Exception as exc:
        log.exception("job %s failed", name)
        finished = _now().isoformat()
        payload = {
            "name": name, "label": JOB_LABELS.get(name, name),
            "status": "error", "started_at": started, "finished_at": finished,
            "stats": None, "error": str(exc) or exc.__class__.__name__,
            "progress": None,
        }
        await _write_status(name, payload)
        return payload
    finally:
        _running.discard(name)


async def run(name: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run a job and wait. Raises JobBusy if that name is already in flight."""
    if name not in HANDLERS:
        raise KeyError(name)
    if name in _running:
        raise JobBusy(name)
    _running.add(name)
    return await _execute(name, params or {})


async def enqueue(name: str, params: dict[str, Any] | None = None) -> bool:
    """Hand a long job to the worker process. False when one is already waiting."""
    if name not in HANDLERS:
        raise KeyError(name)
    current = await _read_status(name)
    if current["status"] in ("queued", "running") or name in _running:
        return False
    await _write_status(name, {
        "name": name,
        "label": JOB_LABELS.get(name, name),
        "status": "queued",
        "started_at": None,
        "finished_at": None,
        "stats": None,
        "error": None,
        "progress": None,
        "params": params or {},
    })
    return True


async def spawn(name: str, params: dict[str, Any] | None = None) -> bool:
    """Start a job here, or leave it queued for the worker process."""
    if name not in HANDLERS:
        raise KeyError(name)
    if name in WORKER_JOBS and not RUNS_JOBS:
        return await enqueue(name, params)
    if name in _running:
        return False
    _running.add(name)
    asyncio.create_task(_execute(name, params or {}), name=f"job:{name}")
    return True


# ---------- handlers ----------

async def _literature_fetch(_params: dict[str, Any]) -> dict[str, Any]:
    from .literature_scheduler import run_once

    stats = await run_once()
    stats.pop("created_ids", None)
    return stats


async def _daily_generate(params: dict[str, Any]) -> dict[str, Any]:
    from . import daily_service

    raw = params.get("date")
    if raw:
        day = date.fromisoformat(str(raw)[:10])
    else:
        day = datetime.now(daily_service.business_tz()).date()
    async with SessionLocal() as session:
        daily = await daily_service.generate_daily(session, day)
        await session.commit()
    if daily is None:
        return {"skipped": True, "reason": "该日期没有收录资讯", "date": day.isoformat()}
    return {
        "skipped": False,
        "date": daily.date.isoformat(),
        "title": daily.title,
        "highlight_count": len(daily.highlights or []),
        "item_count": len(daily.item_ids or []),
    }


async def _rescore_unscored(_params: dict[str, Any]) -> dict[str, Any]:
    from ..config import settings
    from . import scoring_service

    if not settings.deepseek_api_key:
        raise RuntimeError("DEEPSEEK_API_KEY 未配置，无法评分")
    async with SessionLocal() as session:
        ids = list((await session.execute(
            select(Item.id).where(Item.score.is_(None)).order_by(Item.id)
        )).scalars().all())
    total = len(ids)
    scored = failed = 0
    days: set = set()
    for i, item_id in enumerate(ids, start=1):
        async with SessionLocal() as session:
            item = await session.get(Item, item_id)
            if item is None:
                failed += 1
            else:
                result = await scoring_service.score_item(session, item)
                if result is None:
                    failed += 1
                else:
                    scored += 1
                    days.add(item.created_at.replace(hour=0, minute=0, second=0, microsecond=0))
                    await session.commit()
        if i % 5 == 0 or i == total:
            await set_progress("rescore_unscored", done=i, total=total)
    async with SessionLocal() as session:
        for day in days:
            await scoring_service.refresh_day_selection(session, day)
        await session.commit()
    return {"total": total, "scored": scored, "failed": failed}


async def _translate_abstracts(_params: dict[str, Any]) -> dict[str, Any]:
    from ..config import settings
    from . import abstract_translate_service

    if not settings.deepseek_api_key:
        raise RuntimeError("DEEPSEEK_API_KEY 未配置，无法翻译")
    async with SessionLocal() as session:
        ids = list((await session.execute(
            select(Item.id).where(
                Item.summary_zh.is_(None),
                or_(Item.category == "论文", Item.paper.has()),
            ).order_by(Item.id)
        )).scalars().all())
    total = len(ids)
    translated = skipped = failed = 0
    for i, item_id in enumerate(ids, start=1):
        async with SessionLocal() as session:
            item = await session.get(Item, item_id)
            if item is None or not abstract_translate_service.needs_translation(item):
                skipped += item is not None
                failed += item is None
            else:
                result = await abstract_translate_service.fill_summary_zh(session, item)
                if result:
                    translated += 1
                    await session.commit()
                else:
                    failed += 1
        if i % 5 == 0 or i == total:
            await set_progress("translate_abstracts", done=i, total=total)
    return {"total": total, "translated": translated, "skipped": skipped, "failed": failed}


async def _retag(_params: dict[str, Any]) -> dict[str, Any]:
    from . import ingest_service

    async with SessionLocal() as session:
        stats = await ingest_service.retag_all_items(session)
        await session.commit()
    stats.pop("diffs", None)
    return stats


FETCH_CONTENT_BATCH = 20
FETCH_CONTENT_CURSOR = "content_fetch:last_item_id"


async def missing_content_ids(session, *, limit: int = FETCH_CONTENT_BATCH, after_id: int = 0) -> list[int]:
    """政策/报道/行业且无正文。论文有摘要，不进自动回补。"""
    stmt = (select(Item.id)
        .where(
            or_(Item.content.is_(None), Item.content == ""),
            Item.category != "论文",
            ~Item.paper.has(),
        )
        .order_by(Item.id))
    rows = await session.execute(stmt.where(Item.id > after_id).limit(limit))
    ids = list(rows.scalars().all())
    if after_id and len(ids) < limit:
        rows = await session.execute(stmt.where(Item.id <= after_id).limit(limit - len(ids)))
        ids.extend(rows.scalars().all())
    return ids


async def _prepare_content_fetch(item_id: int, *, force: bool) -> tuple[str, list[str]] | None:
    """Copy the URLs, then return the connection before the outbound request."""
    from . import content_service

    async with SessionLocal() as session:
        item = await session.get(Item, item_id)
        if item is None or (item.content and item.content.strip() and not force):
            return None
        return content_service._fetch_targets(item)


async def _save_content_cursor(item_id: int) -> None:
    async with SessionLocal() as session:
        cursor = await session.get(PipelineState, FETCH_CONTENT_CURSOR)
        if cursor is None:
            cursor = PipelineState(key=FETCH_CONTENT_CURSOR)
            session.add(cursor)
        cursor.value, cursor.updated_at = str(item_id), utcnow()
        await session.commit()


async def _fetch_content(params: dict[str, Any]) -> dict[str, Any]:
    from . import content_service, runtime_settings

    ids = [int(i) for i in (params.get("item_ids") or [])]
    automatic = not ids
    force = bool(params.get("force"))
    if not runtime_settings.get("content_fetch_enabled"):
        raise RuntimeError("全文抓取功能未启用")
    async with SessionLocal() as session:
        if not ids:
            cursor = await session.get(PipelineState, FETCH_CONTENT_CURSOR)
            after_id = int(cursor.value) if cursor and cursor.value.isdecimal() else 0
            ids = await missing_content_ids(session, after_id=after_id)
            force = False
        await session.commit()
    if not ids:
        return {"requested": 0, "fetched": 0, "skipped": 0, "failed": 0}
    fetched = skipped = failed = 0
    for i, item_id in enumerate(ids, start=1):
        target = await _prepare_content_fetch(item_id, force=force)
        if target is None:
            async with SessionLocal() as session:
                exists = await session.get(Item, item_id)
            failed += exists is None
            skipped += exists is not None
        else:
            url, alternatives = target
            kwargs = {"alternative_urls": alternatives} if alternatives else {}
            text = await content_service.fetch_fulltext(url, **kwargs)
            if text is None:
                failed += 1
            else:
                async with SessionLocal() as session:
                    item = await session.get(Item, item_id)
                    if item is None:
                        failed += 1
                    else:
                        await content_service.save_and_score_content(session, item, text)
                        fetched += 1
        if automatic:
            await _save_content_cursor(item_id)
        await set_progress("fetch_content", done=i, total=len(ids))
    return {"requested": len(ids), "fetched": fetched, "skipped": skipped, "failed": failed}


async def _taxonomy_backfill(params: dict[str, Any]) -> dict[str, Any]:
    from .taxonomy_jobs import backfill

    async def progress(done, total):
        await set_progress("taxonomy_backfill", done=done, total=total)

    return await backfill(SessionLocal, force=bool(params.get("force")), progress=progress)


HANDLERS: dict[str, Handler] = {
    "literature_fetch": _literature_fetch,
    "daily_generate": _daily_generate,
    "rescore_unscored": _rescore_unscored,
    "translate_abstracts": _translate_abstracts,
    "retag": _retag,
    "taxonomy_backfill": _taxonomy_backfill,
    "fetch_content": _fetch_content,
}


async def _specials_generate(params: dict[str, Any]) -> dict[str, Any]:
    from .special_service import run_once
    async with SessionLocal() as session:
        await runtime_settings.load(session)
    return await run_once(special_id=params.get("special_id"), dry_run=bool(params.get("dry_run")))


HANDLERS["specials_generate"] = _specials_generate
