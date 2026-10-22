"""Durable indexing, revision-aware writes, and bounded background backfill."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from datetime import timedelta

import jieba
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from ..config import settings
from ..database import SessionLocal
from ..models import Item, SearchChunk, SearchJob, utcnow
from . import embedding_service

log = logging.getLogger(__name__)
jieba.setLogLevel(logging.WARNING)


def tokens(text: str) -> list[str]:
    return list(dict.fromkeys(w.lower() for w in jieba.cut_for_search(text) if re.search(r"[\w\u4e00-\u9fff]", w)))


def chunks_for(item: Item) -> list[str]:
    header = "\n".join(filter(None, [item.title, item.summary_zh, item.summary, " ".join(t.name for t in item.tags), " ".join(item.search_phrases or [])]))
    # Bound metadata as well as body so one request stays within the provider's batch token limit.
    text = header + ("\n" + item.content if item.content else "")
    chunks, start = [], 0
    while start < len(text):
        end = min(start + 800, len(text))
        while len(text[start:end].encode("utf-8")) > 2800:
            end -= 1
        if text[start:end].strip():
            chunks.append(text[start:end])
        if end == len(text):
            break
        start = end - 100
    return chunks


def content_hash(chunks: list[str]) -> str:
    return hashlib.sha256(json.dumps(chunks, ensure_ascii=False).encode()).hexdigest()


async def enqueue_backfill(session, force: bool = False) -> int:
    """Insert missing jobs and requeue a changed model. Does not repeat successful calls."""
    ids = (await session.execute(select(Item.id).outerjoin(SearchJob, SearchJob.item_id == Item.id).where(SearchJob.item_id.is_(None)))).scalars().all()
    for item_id in ids:
        insert = pg_insert if session.bind.dialect.name == "postgresql" else sqlite_insert
        await session.execute(insert(SearchJob).values(item_id=item_id).on_conflict_do_nothing(index_elements=[SearchJob.item_id]))
    condition = SearchJob.status.in_(["ready", "lexical"])
    if not force:
        condition = condition & (SearchJob.fingerprint != embedding_service.fingerprint())
    updated = await session.execute(update(SearchJob).where(condition).values(status="pending", revision=SearchJob.revision + 1, retry_at=None, attempts=0))
    if force:
        await session.execute(update(SearchJob).where(SearchJob.status == "error").values(status="pending", retry_at=None, attempts=0, revision=SearchJob.revision + 1))
    await session.commit()
    return len(ids) + updated.rowcount


async def process_one(session_factory=SessionLocal) -> bool:
    now = utcnow()
    async with session_factory() as session:
        job = (await session.execute(select(SearchJob).where(or_(
            SearchJob.status == "pending",
            (SearchJob.status.in_(["error", "lexical"])) & (SearchJob.retry_at <= now),
            (SearchJob.status == "working") & (SearchJob.updated_at < now - timedelta(minutes=10)),
        )).order_by(SearchJob.updated_at, SearchJob.item_id).with_for_update(skip_locked=True).limit(1))).scalar_one_or_none()
        if job is None:
            return False
        item = await session.get(Item, job.item_id)
        if item is None:
            await session.delete(job)
            await session.commit()
            return True
        texts = chunks_for(item)
        digest, fp = content_hash(texts), embedding_service.fingerprint()
        vector_count = (await session.execute(select(func.count()).select_from(SearchChunk).where(
            SearchChunk.item_id == job.item_id, SearchChunk.fingerprint == fp, SearchChunk.embedding.is_not(None)
        ))).scalar_one()
        if job.content_hash == digest and job.fingerprint == fp and vector_count == len(texts):
            job.status = "ready"
            job.error, job.retry_at = None, None
            await session.commit()
            return True
        item_id, revision, attempts = job.item_id, job.revision, job.attempts + 1
        job.status, job.updated_at = "working", now
        await session.commit()
    error = None
    try:
        vectors = await embedding_service.embed(texts)
    except embedding_service.EmbeddingUnavailable as exc:
        error = str(exc)
        vectors = [None] * len(texts)
    async with session_factory() as session:
        job = (await session.execute(select(SearchJob).where(SearchJob.item_id == item_id).with_for_update())).scalar_one_or_none()
        if job is None or job.revision != revision:
            return True
        # Preserve previously valid vectors during a transient provider outage.
        if not error or job.content_hash != digest or job.fingerprint != fp:
            await session.execute(delete(SearchChunk).where(SearchChunk.item_id == item_id))
            session.add_all(SearchChunk(item_id=item_id, position=position, text=text, lexemes=" ".join(tokens(text)), embedding=vector, fingerprint=fp) for position, (text, vector) in enumerate(zip(texts, vectors)))
            job.content_hash, job.fingerprint = digest, fp
        job.status = "lexical" if error else "ready"
        job.error, job.attempts, job.updated_at = error, attempts, utcnow()
        job.retry_at = utcnow() + timedelta(seconds=min(3600, 30 * 2 ** min(attempts, 7))) if error else None
        await session.commit()
    return True


async def status(session) -> dict:
    counts = dict((await session.execute(select(SearchJob.status, func.count()).group_by(SearchJob.status))).all())
    total = (await session.execute(select(func.count(Item.id)))).scalar_one()
    ready = (await session.execute(select(func.count()).select_from(SearchJob).where(SearchJob.status == "ready", SearchJob.fingerprint == embedding_service.fingerprint()))).scalar_one()
    errors = (await session.execute(select(SearchJob.item_id, SearchJob.error).where(SearchJob.error.is_not(None)).order_by(SearchJob.updated_at.desc()).limit(10))).all()
    return {"configured": bool(settings.embedding_api_key), "enabled": settings.search_index_enabled,
            "model": settings.embedding_model, "dimensions": settings.embedding_dimensions,
            "total": total, "indexed": ready, "coverage": ready / total if total else 1,
            "pending": total - ready, "counts": counts, "errors": [{"item_id": i, "error": e} for i, e in errors]}


async def run_worker():
    while True:
        try:
            if settings.search_index_enabled:
                async with SessionLocal() as session:
                    await enqueue_backfill(session)
                for _ in range(20):
                    if not await process_one():
                        break
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("Search indexing failed: %s", type(exc).__name__)
        await asyncio.sleep(5)
