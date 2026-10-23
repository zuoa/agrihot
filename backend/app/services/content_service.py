"""Full-text strategy integration and durable article enrichment.

The reusable tools live in services.fulltext. Application callers keep the
best-effort background contract and commit fetched text before model scoring.
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import SessionLocal
from ..models import Item
from . import abstract_translate_service, paper_card_service, runtime_settings, scoring_service
from .fulltext import (MAX_CONTENT_CHARS, MIN_CONTENT_CHARS, FetchOptions, FetchResult,
                       FulltextEngine, FulltextFetchError)
from .fulltext.fetchers import strip_jina_preamble as _strip_jina_preamble

log = logging.getLogger(__name__)


def create_fulltext_engine() -> FulltextEngine:
    return FulltextEngine(options=FetchOptions(
        timeout=settings.content_fetch_timeout,
        max_chars=settings.content_max_chars,
        jina_base_url=settings.jina_reader_base_url,
        jina_api_key=settings.jina_api_key,
    ))


async def fetch_fulltext_result(url: str, *, alternative_urls=()) -> FetchResult:
    """Tool entry point with method, resolved source, truncation and attempt metadata."""
    return await create_fulltext_engine().fetch(url, alternative_urls=alternative_urls)


async def fetch_fulltext(url: str, *, raise_errors: bool = False, alternative_urls=()) -> str | None:
    """Application wrapper: background failures return None; manual requests get diagnostics."""
    if not runtime_settings.get("content_fetch_enabled"):
        return None
    try:
        return (await fetch_fulltext_result(url, alternative_urls=alternative_urls)).text
    except FulltextFetchError as error:
        log.warning("Full-text fetch failed for %s: %s (upstream_http=%s, attempts=%s)",
                    url, error.reason, error.upstream_status, len(error.attempts))
        if raise_errors:
            raise
        return None


async def fetch_item_fulltext(item: Item, *, raise_errors: bool = False) -> str | None:
    """Use the item's known source and open-access links when its primary URL fails."""
    alternatives = list(dict.fromkeys(url for url in (
        item.paper.oa_url if item.paper else None, item.source_url,
    ) if url and url != item.url))
    kwargs = {}
    if raise_errors:
        kwargs["raise_errors"] = True
    if alternatives:
        kwargs["alternative_urls"] = alternatives
    return await fetch_fulltext(item.url, **kwargs)


async def enrich_item(session: AsyncSession, item: Item) -> bool:
    """Backfill item.content if empty. True if content was added. Caller commits."""
    if item.content and item.content.strip():
        return False
    text = await fetch_item_fulltext(item)
    if text is None:
        return False
    item.content = text
    log.info("item %s backfilled full text (%d chars)", item.id, len(text))
    return True


async def enrich_and_score(item_id: int) -> None:
    """Background task entry: backfill full text (best effort), then score.

    Opens its own session (the request session is closed by then). Enrichment
    runs even when scoring is disabled; scoring failures stay fail-closed.
    """
    async with SessionLocal() as session:
        item = await session.get(Item, item_id)
        if item is None:
            return
        # Automatic enrichment keeps papers on the abstract/card workflow;
        # manual and explicit batch fetching can retrieve their full text.
        is_paper = item.category == "论文" or item.paper is not None
        if not is_paper:
            await enrich_item(session, item)
            # The fetched source must survive scoring errors and cancellation.
            await session.commit()
        if item.is_selected:
            return
        try:
            if settings.deepseek_api_key:
                if await scoring_service.score_item(session, item) is not None:
                    await scoring_service.refresh_day_selection(session, item.created_at)
                if is_paper:
                    await paper_card_service.fill_card(session, item)
                    await abstract_translate_service.fill_summary_zh(session, item)
            await session.commit()
        except Exception as exc:
            await session.rollback()
            log.warning("Item %s enrichment scoring failed: %s", item_id, type(exc).__name__)


async def save_and_score_content(session: AsyncSession, item: Item, text: str) -> None:
    """Persist each fetched body before attempting optional, best-effort scoring."""
    item_id = item.id
    item.content = text
    await session.commit()
    if settings.deepseek_api_key:
        try:
            if await scoring_service.score_item(session, item) is not None:
                await scoring_service.refresh_day_selection(session, item.created_at)
            await session.commit()
        except Exception as exc:
            await session.rollback()
            log.warning("Full text saved for item %s; rescoring failed: %s", item_id, type(exc).__name__)
    await session.refresh(item)
