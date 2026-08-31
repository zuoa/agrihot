"""Ingest business logic: validate -> dedup -> create or merge."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Item, Tag, item_tags
from ..schemas import IngestItemIn, IngestResultOut
from . import dedup

log = logging.getLogger(__name__)

# canonical categories; unknown values fall back to 报道
CATEGORIES = {"政策", "报道", "论文", "行业"}

# near-duplicate title search window
SIMHASH_WINDOW_DAYS = 30

# Agents often dump a title-like keyword string as one tag. Split on these
# separators, keep short topical tokens, drop dates / stopwords / leftovers.
_TAG_SEPARATORS = re.compile(
    r"[\s·•・‧、,，;；|/\\#`\"'“”‘’「」『』（）()\[\]【】<>《》~～]+"
)
_ASCII_TOKEN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+\-]*$")
_CJK_CHAR = re.compile(r"[\u4e00-\u9fff]")
_DATE_TAG = re.compile(
    r"^(\d{4}年\d{1,2}月(\d{1,2}日)?|\d{4}[-/.]\d{1,2}([-. /]\d{1,2})?|\d{4}年)$"
)
_ASCII_STOPWORDS = {
    "a", "an", "and", "as", "at", "by", "et", "al", "for", "from", "in",
    "of", "on", "or", "the", "to", "vs", "with",
}
TAG_MIN_LEN = 2
TAG_MAX_CJK = 16
TAG_MAX_ASCII = 40
TAG_MAX_COUNT = 20


def normalize_tags(names: list[str] | None) -> list[str]:
    """Split concatenated tag blobs into short, unique topic names.

    Each incoming element is split on its own (so ``["IoT", "AI"]`` stays two
    tags). Consecutive Latin tokens inside one element are kept as a phrase
    (``Journal of Advanced Research``). Over-long blobs, dates, and English
    stopwords are dropped.
    """
    if not names:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for raw in names:
        for token in _split_tag_blob(str(raw)):
            if not _is_usable_tag(token):
                continue
            key = token.casefold()
            if key in seen:
                continue
            seen.add(key)
            out.append(token)
            if len(out) >= TAG_MAX_COUNT:
                return out
    return out


def _split_tag_blob(raw: str) -> list[str]:
    pieces = [p.strip() for p in _TAG_SEPARATORS.split(raw) if p.strip()]
    merged: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        if not buf:
            return
        words = [w for w in buf if w.casefold() not in _ASCII_STOPWORDS]
        phrase = " ".join(buf)
        buf.clear()
        if not words:
            return
        merged.append(phrase)

    for piece in pieces:
        if _ASCII_TOKEN.match(piece):
            buf.append(piece)
        else:
            flush()
            merged.append(piece)
    flush()
    return merged


def _is_usable_tag(token: str) -> bool:
    if len(token) < TAG_MIN_LEN:
        return False
    if _DATE_TAG.match(token) or token.isdigit():
        return False
    if token.casefold() in _ASCII_STOPWORDS:
        return False
    cjk = len(_CJK_CHAR.findall(token))
    if cjk:
        return cjk <= TAG_MAX_CJK and len(token) <= TAG_MAX_CJK + 8
    return len(token) <= TAG_MAX_ASCII


def _normalize_category(cat: str | None) -> str:
    if cat and cat.strip() in CATEGORIES:
        return cat.strip()
    return "报道"


async def _get_or_create_tags(session: AsyncSession, names: list[str]) -> list[Tag]:
    tags: list[Tag] = []
    for name in normalize_tags(names):
        tag = (await session.execute(select(Tag).where(Tag.name == name))).scalar_one_or_none()
        if tag is None:
            tag = Tag(name=name)
            session.add(tag)
            await session.flush()
        tags.append(tag)
    return tags


async def retag_all_items(session: AsyncSession, *, dry_run: bool = False) -> dict:
    """Re-split every item's tags. Idempotent. Caller commits unless dry_run.

    Returns counts plus ``diffs`` of ``(item_id, old_names, new_names)``.
    """
    items = (await session.execute(select(Item).order_by(Item.id))).scalars().all()
    changed = 0
    before: set[str] = set()
    after: set[str] = set()
    diffs: list[tuple[int, list[str], list[str]]] = []
    for item in items:
        old = [t.name for t in item.tags]
        new = normalize_tags(old)
        before.update(old)
        after.update(new)
        if old == new:
            continue
        changed += 1
        diffs.append((item.id, old, new))
        if not dry_run:
            item.tags = await _get_or_create_tags(session, old)

    orphans = 0
    if not dry_run:
        await session.flush()
        orphan_ids = list(
            (
                await session.execute(
                    select(Tag.id).where(
                        ~Tag.id.in_(select(item_tags.c.tag_id).distinct())
                    )
                )
            ).scalars().all()
        )
        if orphan_ids:
            await session.execute(delete(Tag).where(Tag.id.in_(orphan_ids)))
        orphans = len(orphan_ids)

    return {
        "items": len(items),
        "changed": changed,
        "tags_before": len(before),
        "tags_after": len(after),
        "orphans": orphans,
        "diffs": diffs,
    }


async def maybe_retag_existing(session: AsyncSession) -> dict | None:
    """Startup helper: retag only if some stored names still look like blobs."""
    names = (await session.execute(select(Tag.name))).scalars().all()
    if not any(normalize_tags([n]) != [n] for n in names):
        return None
    stats = await retag_all_items(session)
    log.info(
        "retag existing tags: %s items, %s changed, %s -> %s tags, %s orphans",
        stats["items"], stats["changed"], stats["tags_before"],
        stats["tags_after"], stats["orphans"],
    )
    return stats


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
