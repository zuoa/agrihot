"""Incremental publisher PDF backfill in the content worker."""
from __future__ import annotations

import asyncio
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import or_, select

from ..database import SessionLocal
from ..models import Item, PaperPdf, PipelineState, utcnow
from . import job_runner, paper_pdf
from .fulltext.base import FulltextFetchError

CURSOR = "paper_pdf:last_item_id"
BATCH = 20
MIN_FREE_BYTES = 1024 * 1024 * 1024


async def _batch_ids() -> tuple[list[int], int | None]:
    async with SessionLocal() as session:
        cursor = await session.get(PipelineState, CURSOR)
        after = int(cursor.value) if cursor and cursor.value.isdecimal() else 0
        priority = (select(Item.id).join(PaperPdf, PaperPdf.item_id == Item.id)
                    .where(or_(Item.category == "论文", Item.paper.has()),
                           PaperPdf.status == "pending", PaperPdf.error == "pdf_file_missing")
                    .order_by(Item.id).limit(BATCH))
        recovery_ids = list((await session.scalars(priority)).all())
        if len(recovery_ids) == BATCH:
            return recovery_ids, None
        retry_before = datetime.now(timezone.utc) - timedelta(hours=24)
        eligible = or_(PaperPdf.item_id.is_(None), PaperPdf.status == "pending",
                       (PaperPdf.status == "running") & (PaperPdf.updated_at < datetime.now(timezone.utc) - timedelta(minutes=20)),
                       (PaperPdf.status == "failed") & (PaperPdf.attempts < 3) & (PaperPdf.updated_at < retry_before))
        query = (select(Item.id).outerjoin(PaperPdf, PaperPdf.item_id == Item.id)
                 .where(or_(Item.category == "论文", Item.paper.has()), eligible,
                        Item.id.not_in(recovery_ids))
                 .order_by(Item.id).limit(BATCH - len(recovery_ids)))
        ids = list((await session.scalars(query.where(Item.id > after))).all())
        if not ids and after:
            ids = list((await session.scalars(query)).all())
        return recovery_ids + ids, max(ids) if ids else None


async def _cursor(item_id: int) -> None:
    async with SessionLocal() as session:
        state = await session.get(PipelineState, CURSOR)
        if state is None:
            state = PipelineState(key=CURSOR)
            session.add(state)
        state.value, state.updated_at = str(item_id), utcnow()
        await session.commit()


async def fetch_one(item_id: int, *, force: bool = False) -> str:
    async with SessionLocal() as session:
        item = await session.get(Item, item_id)
        if item is None or not (item.category == "论文" or item.paper):
            return "skipped"
        record = item.pdf
        if record and record.status == "ready" and not force:
            return "skipped"
        if record is None:
            record = PaperPdf(item_id=item_id)
            session.add(record)
        record.status, record.error = "running", None
        record.attempts = (record.attempts or 0) + 1
        record.updated_at = utcnow()
        doi = item.doi
        urls = list(dict.fromkeys(filter(None, (item.paper.oa_url if item.paper else None,
                                              item.url, item.source_url))))
        await session.commit()
    try:
        result = await paper_pdf.download_pdf(urls, doi=doi)
        await asyncio.to_thread(paper_pdf.validate_pdf, result.data)
        digest, size = await asyncio.to_thread(paper_pdf.store_pdf, result.data)
        extracted = await paper_pdf.extract_pdf_text(result.data)
    except (FulltextFetchError, TimeoutError, OSError) as exc:
        async with SessionLocal() as session:
            record = await session.get(PaperPdf, item_id)
            record.status, record.error = "failed", (exc.reason if isinstance(exc, FulltextFetchError)
                                                       else "fetch_timeout" if isinstance(exc, TimeoutError) else "storage_error")
            record.updated_at = utcnow()
            await session.commit()
        return "failed"
    async with SessionLocal() as session:
        item = await session.get(Item, item_id)
        if item is None:
            return "skipped"
        record = item.pdf
        record.status, record.error = "ready", None
        record.sha256, record.size_bytes = digest, size
        record.source_url, record.plugin = result.url, result.plugin
        record.updated_at = utcnow()
        if extracted and not (item.content and item.content.strip()):
            item.content = extracted[:100_000]
        await session.commit()
    return "downloaded"


async def run(params: dict) -> dict:
    from . import runtime_settings
    from ..config import settings
    if not runtime_settings.get("content_fetch_enabled"):
        raise RuntimeError("全文抓取功能未启用")
    ids = [int(x) for x in (params.get("item_ids") or [])]
    automatic = not ids
    scanned_through = None
    if automatic:
        pdf_dir = Path(settings.paper_pdf_dir)
        if os.environ.get("AGRIHOT_PROCESS") == "worker" and not pdf_dir.is_mount():
            await job_runner.append_log("fetch_paper_pdfs", stage="pdf", level="warning",
                                        message="PDF 共享卷未挂载，暂停自动下载")
            return {"requested": 0, "downloaded": 0, "failed": 0, "skipped": 0,
                    "storage_paused": True, "reason": "volume_missing"}
        if pdf_dir.is_dir():
            free_bytes = shutil.disk_usage(pdf_dir).free
            required_bytes = MIN_FREE_BYTES + BATCH * settings.paper_pdf_max_bytes
            if free_bytes < required_bytes:
                await job_runner.append_log("fetch_paper_pdfs", stage="pdf", level="warning",
                                            message="PDF 存储空间不足，暂停自动下载")
                return {"requested": 0, "downloaded": 0, "failed": 0, "skipped": 0,
                        "storage_paused": True, "free_bytes": free_bytes}
        ids, scanned_through = await _batch_ids()
    stats = {"requested": len(ids), "downloaded": 0, "failed": 0, "skipped": 0}
    semaphore = asyncio.Semaphore(3)

    async def work(item_id: int) -> tuple[int, str]:
        async with semaphore:
            return item_id, await fetch_one(item_id, force=bool(params.get("force")))

    tasks = [asyncio.create_task(work(item_id)) for item_id in ids]
    try:
        for index, task in enumerate(asyncio.as_completed(tasks), 1):
            item_id, outcome = await task
            stats[outcome] += 1
            await job_runner.append_log("fetch_paper_pdfs", stage="pdf", message=f"论文 #{item_id}：{outcome}",
                                        level="warning" if outcome == "failed" else "info",
                                        details={"item_id": item_id, "result": outcome})
            await job_runner.set_progress("fetch_paper_pdfs", done=index, total=len(ids))
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    if automatic and scanned_through is not None:
        await _cursor(scanned_through)
    return stats
