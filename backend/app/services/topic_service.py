"""Long-tail topic phrases, kept separate from the Tag taxonomy.

Atomic tags stay short and reusable. Space-separated `/tags/{phrase}` URLs
are resolved as AND queries (with text fallback) and never inserted as Tag rows.
"""
from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from urllib.parse import unquote

from sqlalchemy import func, literal, or_, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import Item, ItemTopic, SearchChunk, SearchJob, Tag, item_tags
from . import embedding_service
from .ingest_service import _CJK_CHAR, _is_usable_tag, _split_tag_blob
from .taxonomy_catalog import canonical_name, equivalent_names

log = logging.getLogger(__name__)

GENERIC_TAGS = {
    "政策", "报道", "论文", "行业", "农业", "资讯", "新闻", "动态", "专题",
    "要闻", "热点", "研究", "进展", "分析", "综述", "观点", "评论", "科技",
    "技术", "三农", "农村", "快讯", "关注",
}

NAME_MAX = 120
PHRASE_MAX = 2
PHRASE_TOKEN_MAX = 5
RELATED_LIMIT = 6
SIMILAR_LIMIT = 8
# Cosine distance: 0 is identical, 2 is opposite. Keep clearly related neighbors.
SIMILAR_MAX_DISTANCE = 0.45
_LIKE_UNSAFE = re.compile(r"[%_\\]")
_SLUG_STRIP = re.compile(r"[\s/\\?#&=]+")


def _fully_unquote(raw: str) -> str:
    """Undo one or more layers of percent-encoding (crawler URLs are often doubled)."""
    s = raw.replace("+", " ")
    for _ in range(4):
        nxt = unquote(s)
        if nxt == s:
            break
        s = nxt
    return s


def _clean_name(raw: str | None) -> str:
    return _fully_unquote(raw or "").strip()[:NAME_MAX]


def tokens_of(raw: str | None) -> list[str]:
    name = _clean_name(raw)
    if not name:
        return []
    return [t for t in _split_tag_blob(name) if t]


def parse_tag_query(tag: str | None, tags: str | None) -> list[str]:
    """Split `tag` / comma-separated `tags` into unique exact names (no blob split)."""
    names: list[str] = []
    seen: set[str] = set()
    for raw in (tag, tags):
        if not raw:
            continue
        for part in re.split(r"[,，]", raw):
            n = part.strip()
            if not n or n in seen:
                continue
            seen.add(n)
            names.append(n)
    return names


def apply_tag_match(stmt, names: list[str], match: str):
    if not names:
        return stmt
    if match == "any":
        return stmt.where(Item.tags.any(Tag.name.in_([alias for name in names for alias in equivalent_names(name)])))
    for n in names:
        stmt = stmt.where(Item.tags.any(Tag.name.in_(equivalent_names(n))))
    return stmt


def specific_tags(names: list[str]) -> list[str]:
    spec = [n for n in names if n and n not in GENERIC_TAGS]
    spec.sort(key=lambda t: (-len(_CJK_CHAR.findall(t)), -len(t), t))
    return spec


def normalize_phrase(raw: str | None) -> str | None:
    """Keep 2–5 specific tokens, joined by spaces. Not a Tag name."""
    tokens: list[str] = []
    seen: set[str] = set()
    for token in tokens_of(raw):
        if not _is_usable_tag(token) or token in GENERIC_TAGS:
            continue
        key = token.casefold()
        if key in seen:
            continue
        seen.add(key)
        tokens.append(token)
        if len(tokens) >= PHRASE_TOKEN_MAX:
            break
    if len(tokens) < 2:
        return None
    return " ".join(tokens)


def derive_phrases(tag_names: list[str]) -> list[str]:
    spec = specific_tags(tag_names)
    if len(spec) < 2:
        return []
    out = [" ".join(spec[: min(4, len(spec))])]
    if len(spec) >= 3:
        pair = " ".join(spec[:2])
        if pair != out[0]:
            out.append(pair)
    return out


def effective_phrases(tag_names: list[str], stored: list | None = None) -> list[str]:
    """LLM phrases first (natural query order), then derived from tags. Cap 2."""
    out: list[str] = []
    seen: set[str] = set()

    def add(phrase: str | None) -> None:
        if not phrase or phrase in seen:
            return
        seen.add(phrase)
        out.append(phrase)

    for raw in stored or []:
        if isinstance(raw, str):
            add(normalize_phrase(raw))
    for phrase in derive_phrases(tag_names):
        add(phrase)
        if len(out) >= PHRASE_MAX:
            break
    return out[:PHRASE_MAX]


def parse_search_phrases(data: dict | None) -> list[str]:
    if not isinstance(data, dict):
        return []
    raw = data.get("search_phrases")
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        phrase = normalize_phrase(item)
        if not phrase or phrase in seen:
            continue
        seen.add(phrase)
        out.append(phrase)
        if len(out) >= PHRASE_MAX:
            break
    return out


def item_slug(item_id: int, title: str, phrases: list[str] | None = None) -> str:
    base = (phrases[0] if phrases else "") or title or "item"
    base = _SLUG_STRIP.sub("", base)[:40] or "item"
    return f"{base}-{item_id}"


def parse_item_slug(slug: str | None) -> int | None:
    if not slug:
        return None
    tail = slug.rsplit("-", 1)[-1]
    if tail.isdigit():
        return int(tail)
    return None


def _like_token(token: str) -> str | None:
    cleaned = _LIKE_UNSAFE.sub("", token).strip()
    return cleaned or None


@dataclass
class TopicResult:
    name: str
    kind: str  # tag | phrase
    tokens: list[str]
    total: int
    items: list[Item]


async def _tag_exists(session: AsyncSession, name: str) -> bool:
    row = (
        await session.execute(select(Tag.id).where(Tag.name == name).limit(1))
    ).scalar_one_or_none()
    return row is not None


async def _existing_names(session: AsyncSession, names: list[str]) -> list[str]:
    if not names:
        return []
    found = set(
        (await session.execute(select(Tag.name).where(Tag.name.in_(names)))).scalars().all()
    )
    return [n for n in names if n in found]


async def _paginate_items(
    session: AsyncSession, stmt, count_stmt, page: int, page_size: int, *, load_options=()
) -> tuple[int, list[Item]]:
    total = (await session.execute(count_stmt)).scalar_one()
    rows = (
        await session.execute(
            stmt.options(*load_options).order_by(Item.created_at.desc(), Item.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return total, list(rows)


async def query_by_tags(
    session: AsyncSession,
    names: list[str],
    match: str,
    page: int,
    page_size: int,
    *, load_options=(),
) -> tuple[int, list[Item]]:
    stmt = apply_tag_match(select(Item), names, match)
    count_stmt = apply_tag_match(select(func.count(Item.id)), names, match)
    return await _paginate_items(session, stmt, count_stmt, page, page_size, load_options=load_options)


async def query_by_text_tokens(
    session: AsyncSession, tokens: list[str], page: int, page_size: int, *, load_options=()
) -> tuple[int, list[Item]]:
    likes = [_like_token(t) for t in tokens]
    likes = [t for t in likes if t]
    if not likes:
        return 0, []
    conds = []
    for t in likes:
        pat = f"%{t}%"
        conds.append(
            or_(
                Item.title.ilike(pat),
                Item.summary.ilike(pat),
                Item.summary_zh.ilike(pat),
            )
        )
    where = conds[0]
    for extra in conds[1:]:
        where = where & extra
    stmt = select(Item).where(where)
    count_stmt = select(func.count(Item.id)).where(where)
    return await _paginate_items(session, stmt, count_stmt, page, page_size, load_options=load_options)


async def resolve_topic(
    session: AsyncSession,
    name: str,
    page: int = 1,
    page_size: int = 20,
    *, load_options=(),
) -> TopicResult:
    name = _clean_name(name)
    tokens = tokens_of(name)

    if name and (await _tag_exists(session, name) or await _tag_exists(session, canonical_name(name))):
        total, items = await query_by_tags(session, [name], "all", page, page_size, load_options=load_options)
        return TopicResult(name, "tag", [name], total, items)

    if len(tokens) <= 1:
        token = tokens[0] if tokens else name
        names = [token] if token else []
        total, items = (
            await query_by_tags(session, names, "all", page, page_size, load_options=load_options) if names else (0, [])
        )
        return TopicResult(name, "tag", names, total, items)

    total, items = await query_by_tags(session, tokens, "all", page, page_size, load_options=load_options)
    if total == 0:
        known = await _existing_names(session, tokens)
        if len(known) >= 2:
            total, items = await query_by_tags(session, known, "all", page, page_size, load_options=load_options)
    if total == 0:
        total, items = await query_by_text_tokens(session, tokens, page, page_size, load_options=load_options)
    return TopicResult(name, "phrase", tokens, total, items)


async def related_items(
    session: AsyncSession, item: Item, limit: int = RELATED_LIMIT, *, load_options=()
) -> list[Item]:
    tag_ids = [t.id for t in (item.tags or []) if t.name not in GENERIC_TAGS]
    codes = [link.topic_code for link in item.topic_links]
    if not tag_ids and not codes:
        return []
    tag_overlap = (
        select(item_tags.c.item_id, func.count().label("n"))
        .where(item_tags.c.tag_id.in_(tag_ids), item_tags.c.item_id != item.id)
        .group_by(item_tags.c.item_id)
    )
    topic_overlap = select(ItemTopic.item_id, literal(3).label("n")).where(
        ItemTopic.topic_code.in_(codes), ItemTopic.item_id != item.id)
    matches = union_all(tag_overlap, topic_overlap).subquery()
    overlap = select(matches.c.item_id, func.sum(matches.c.n).label("n")).group_by(matches.c.item_id).subquery()
    rows = (
        await session.execute(
            select(Item)
            .options(*load_options)
            .join(overlap, overlap.c.item_id == Item.id)
            .order_by(overlap.c.n.desc(), Item.created_at.desc(), Item.id.desc())
            .limit(limit)
        )
    ).scalars().all()
    return list(rows)


async def _similar_item_ids(session: AsyncSession, query: str, exclude: set[int], limit: int) -> list[int]:
    """Nearest indexed articles for a tag name. Empty when vectors are unavailable."""
    if not settings.embedding_api_key or not query:
        return []
    try:
        vector = await embedding_service.query_vector(query)
    except embedding_service.EmbeddingUnavailable:
        log.info("tag similar skipped for %s: embedding unavailable", query)
        return []
    fp = embedding_service.fingerprint()
    ready = (
        SearchJob.status == "ready",
        SearchChunk.fingerprint == fp,
        SearchChunk.embedding.is_not(None),
    )
    if session.bind.dialect.name == "postgresql":
        distance = SearchChunk.embedding.cosine_distance(vector)
        best = (
            select(
                SearchChunk.item_id,
                distance.label("distance"),
                func.row_number().over(partition_by=SearchChunk.item_id, order_by=distance).label("position"),
            )
            .join(SearchJob, SearchJob.item_id == SearchChunk.item_id)
            .where(*ready)
            .subquery()
        )
        stmt = select(best.c.item_id).where(best.c.position == 1, best.c.distance <= SIMILAR_MAX_DISTANCE)
        if exclude:
            stmt = stmt.where(best.c.item_id.not_in(exclude))
        rows = (
            await session.execute(stmt.order_by(best.c.distance, best.c.item_id.desc()).limit(limit))
        ).all()
        return [item_id for (item_id,) in rows]

    # SQLite tests only. Production ranks with pgvector.
    chunks = (
        await session.execute(
            select(SearchChunk).join(SearchJob, SearchJob.item_id == SearchChunk.item_id).where(*ready)
        )
    ).scalars().all()
    query_norm = math.sqrt(sum(x * x for x in vector))
    if not query_norm:
        return []
    best_distance: dict[int, float] = {}
    for chunk in chunks:
        values = chunk.embedding or []
        if len(values) != len(vector):
            continue
        chunk_norm = math.sqrt(sum(x * x for x in values))
        if not chunk_norm:
            continue
        cosine = sum(a * b for a, b in zip(values, vector)) / (chunk_norm * query_norm)
        distance = 1 - cosine
        current = best_distance.get(chunk.item_id)
        if current is None or distance < current:
            best_distance[chunk.item_id] = distance
    ranked = [
        (distance, -item_id, item_id)
        for item_id, distance in best_distance.items()
        if item_id not in exclude and distance <= SIMILAR_MAX_DISTANCE
    ]
    ranked.sort()
    return [item_id for _, _, item_id in ranked[:limit]]


async def similar_items(
    session: AsyncSession, name: str, exclude_ids: set[int], *, limit: int = SIMILAR_LIMIT, load_options=()
) -> list[Item]:
    """Articles near this tag that do not carry the tag itself."""
    query = canonical_name(_clean_name(name))
    if not query:
        return []
    tagged = select(Item.id).where(Item.tags.any(Tag.name.in_(equivalent_names(query))))
    exclude = set(exclude_ids)
    exclude.update((await session.execute(tagged)).scalars().all())
    return await items_near_query(session, query, exclude, limit=limit, load_options=load_options)


async def items_near_query(
    session: AsyncSession, query: str, exclude_ids: set[int], *, limit: int = SIMILAR_LIMIT, load_options=()
) -> list[Item]:
    """Nearest indexed articles for a title or tag name, excluding the given ids."""
    ids = await _similar_item_ids(session, query.strip(), set(exclude_ids), limit)
    if not ids:
        return []
    rows = (
        await session.execute(select(Item).options(*load_options).where(Item.id.in_(ids)))
    ).scalars().all()
    by_id = {item.id: item for item in rows}
    return [by_id[item_id] for item_id in ids if item_id in by_id]
