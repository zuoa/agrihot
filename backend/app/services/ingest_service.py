"""Ingest business logic: validate -> dedup -> create or merge."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Item, Tag
from ..schemas import IngestItemIn, IngestResultOut
from . import dedup

# canonical categories; unknown values fall back to 报道
CATEGORIES = {"政策", "报道", "论文", "行业"}

# near-duplicate title search window
SIMHASH_WINDOW_DAYS = 30


def _normalize_category(cat: str | None) -> str:
    if cat and cat.strip() in CATEGORIES:
        return cat.strip()
    return "报道"


async def _get_or_create_tags(session: AsyncSession, names: list[str]) -> list[Tag]:
    tags: list[Tag] = []
    for raw in names:
        name = raw.strip().strip("「」")
        if not name:
            continue
        tag = (await session.execute(select(Tag).where(Tag.name == name))).scalar_one_or_none()
        if tag is None:
            tag = Tag(name=name)
            session.add(tag)
            await session.flush()
        tags.append(tag)
    return tags


def _merge_source(item: Item, payload: IngestItemIn) -> bool:
    """Fold the duplicate's source into the existing item. Returns True if new."""
    sources = list(item.sources or [])
    incoming_url = payload.source_url or payload.url
    if not any(s.get("url") == incoming_url for s in sources):
        sources.append({"name": payload.source_name or item.source_name, "url": incoming_url})
        item.sources = sources
        # more independent sources -> hotter story
        item.hotness += 15
        return True
    return False


async def _find_similar_title(
    session: AsyncSession, title: str, simhash: int
) -> Item | None:
    since = datetime.now(timezone.utc) - timedelta(days=SIMHASH_WINDOW_DAYS)
    rows = (
        await session.execute(
            select(Item.id, Item.title, Item.title_simhash).where(Item.created_at >= since)
        )
    ).all()
    norm = dedup.normalize_title(title)
    for item_id, existing_title, stored in rows:
        if dedup.hamming(simhash, dedup.from_signed64(stored)) <= dedup.SIMHASH_THRESHOLD:
            return await session.get(Item, item_id)
        # containment: "…指导意见" vs "…指导意见（全文）" — SimHash on short
        # titles is brittle, so treat one normalized title containing the
        # other (and long enough to be meaningful) as the same story
        existing_norm = dedup.normalize_title(existing_title)
        shorter, longer = sorted((norm, existing_norm), key=len)
        if len(shorter) >= 8 and shorter in longer:
            return await session.get(Item, item_id)
    return None


async def ingest_item(
    session: AsyncSession, payload: IngestItemIn, pushed_by: str = ""
) -> IngestResultOut:
    """Push one item through dedup; create or merge. Caller commits."""
    uhash = dedup.url_hash(payload.url)

    # Level 1: exact URL
    existing = (
        await session.execute(select(Item).where(Item.url_hash == uhash))
    ).scalar_one_or_none()
    if existing is not None:
        merged = _merge_source(existing, payload)
        if merged:
            await session.flush()
        return IngestResultOut(
            status="duplicate",
            item_id=existing.id,
            duplicate_of=existing.id,
            dup_reason="exact_url",
            message="URL 已存在，信源已合并" if merged else "URL 已存在",
        )

    # Level 2: similar title
    shash = dedup.title_simhash(payload.title)
    similar = await _find_similar_title(session, payload.title, shash)
    if similar is not None:
        _merge_source(similar, payload)
        await session.flush()
        return IngestResultOut(
            status="duplicate",
            item_id=similar.id,
            duplicate_of=similar.id,
            dup_reason="similar_title",
            message=f"与已有条目「{similar.title[:30]}…」标题相似，信源已合并",
        )

    # New item
    item = Item(
        title=payload.title.strip(),
        url=payload.url.strip(),
        url_hash=uhash,
        title_simhash=dedup.to_signed64(shash),
        summary=payload.summary.strip(),
        content=payload.content,
        source_name=payload.source_name.strip(),
        source_url=payload.source_url,
        published_at=payload.published_at,
        category=_normalize_category(payload.category),
        cover_url=payload.cover_url,
        hotness=10,
        sources=[{"name": payload.source_name.strip(), "url": payload.source_url or payload.url}],
    )
    item.tags = await _get_or_create_tags(session, payload.tags)
    session.add(item)
    await session.flush()
    return IngestResultOut(status="created", item_id=item.id, message="已收录并直接上线")


async def ingest_batch(
    session: AsyncSession, items: list[IngestItemIn], pushed_by: str = ""
) -> list[IngestResultOut]:
    results: list[IngestResultOut] = []
    for payload in items:
        try:
            async with session.begin_nested():  # savepoint per item
                results.append(await ingest_item(session, payload, pushed_by))
        except Exception as exc:  # keep batch going
            results.append(
                IngestResultOut(status="invalid", message=f"入库失败: {exc.__class__.__name__}")
            )
    return results


async def delete_item(session: AsyncSession, item_id: int) -> bool:
    """Delete an item and scrub it from Daily.item_ids. False if not found. Caller commits."""
    from ..models import Daily

    item = await session.get(Item, item_id)
    if item is None:
        return False
    dailies = (await session.execute(select(Daily))).scalars().all()
    for d in dailies:
        if item_id in (d.item_ids or []):
            d.item_ids = [i for i in d.item_ids if i != item_id]
    await session.delete(item)
    return True
