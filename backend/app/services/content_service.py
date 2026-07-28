"""Full-text backfill via Jina Reader for items pushed without content.

The crawler is the primary source of full text; this is the server-side
fallback: ingest spawns `enrich_and_score`, which fetches the article through
r.jina.ai (returns clean markdown), stores it, then runs scoring so the
substance/depth dimensions see the real body instead of just the summary.

All failures are best-effort: fetch errors leave content empty and scoring
simply falls back to the summary.
"""
from __future__ import annotations

import logging

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import SessionLocal
from ..models import Item
from . import scoring_service

log = logging.getLogger(__name__)

# storage cap: keeps pathological pages from bloating the row
MAX_CONTENT_CHARS = 20000
# shorter than this is nav boilerplate / an error page, not an article
MIN_CONTENT_CHARS = 200


async def fetch_fulltext(url: str) -> str | None:
    """Fetch url via Jina Reader -> clean markdown. None on any failure."""
    if not settings.content_fetch_enabled:
        return None
    headers = {}
    if settings.jina_api_key:
        headers["Authorization"] = f"Bearer {settings.jina_api_key}"
    try:
        async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
            resp = await client.get(
                f"{settings.jina_reader_base_url.rstrip('/')}/{url}", headers=headers
            )
            resp.raise_for_status()
            text = resp.text.strip()
    except Exception as exc:  # network / 4xx / 5xx — all best-effort
        log.warning("Jina reader fetch failed for %s: %s", url, exc)
        return None
    if len(text) < MIN_CONTENT_CHARS:
        log.info("Jina reader returned too little (%d chars) for %s", len(text), url)
        return None
    return text[:MAX_CONTENT_CHARS]


async def enrich_item(session: AsyncSession, item: Item) -> bool:
    """Backfill item.content if empty. True if content was added. Caller commits."""
    if item.content and item.content.strip():
        return False
    text = await fetch_fulltext(item.url)
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
        if item is None or item.is_selected:
            return
        await enrich_item(session, item)
        if settings.deepseek_api_key:
            if await scoring_service.score_item(session, item) is not None:
                await scoring_service.refresh_day_selection(session, item.created_at)
        await session.commit()
