"""Long-tail topic phrases, kept separate from the Tag taxonomy.

Atomic tags stay short and reusable. Space-separated `/tags/{phrase}` URLs
are resolved as AND queries (with text fallback) and never inserted as Tag rows.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Item, Tag, item_tags
from .ingest_service import _CJK_CHAR, _is_usable_tag, _split_tag_blob

GENERIC_TAGS = {
    "政策", "报道", "论文", "行业", "农业", "资讯", "新闻", "动态", "专题",
    "要闻", "热点", "研究", "进展", "分析", "综述", "观点", "评论", "科技",
    "技术", "三农", "农村", "快讯", "关注",
}

NAME_MAX = 120
PHRASE_MAX = 2
PHRASE_TOKEN_MAX = 5
RELATED_LIMIT = 6
_LIKE_UNSAFE = re.compile(r"[%_\\]")
_SLUG_STRIP = re.compile(r"[\s/\\?#&=]+")


def _clean_name(raw: str | None) -> str:
    return (raw or "").strip()[:NAME_MAX]


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
        return stmt.where(Item.tags.any(Tag.name.in_(names)))
    for n in names:
        stmt = stmt.where(Item.tags.any(Tag.name == n))
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
    session: AsyncSession, stmt, count_stmt, page: int, page_size: int
) -> tuple[int, list[Item]]:
    total = (await session.execute(count_stmt)).scalar_one()
    rows = (
        await session.execute(
            stmt.order_by(Item.created_at.desc(), Item.id.desc())
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
) -> tuple[int, list[Item]]:
    stmt = apply_tag_match(select(Item), names, match)
    count_stmt = apply_tag_match(select(func.count(Item.id)), names, match)
    return await _paginate_items(session, stmt, count_stmt, page, page_size)


async def query_by_text_tokens(
    session: AsyncSession, tokens: list[str], page: int, page_size: int
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
    return await _paginate_items(session, stmt, count_stmt, page, page_size)


async def resolve_topic(
    session: AsyncSession,
    name: str,
    page: int = 1,
    page_size: int = 20,
) -> TopicResult:
    name = _clean_name(name)
    tokens = tokens_of(name)

    if name and await _tag_exists(session, name):
        total, items = await query_by_tags(session, [name], "all", page, page_size)
        return TopicResult(name, "tag", [name], total, items)

    if len(tokens) <= 1:
        token = tokens[0] if tokens else name
        names = [token] if token else []
        total, items = (
            await query_by_tags(session, names, "all", page, page_size) if names else (0, [])
        )
        return TopicResult(name, "tag", names, total, items)

    total, items = await query_by_tags(session, tokens, "all", page, page_size)
    if total == 0:
        known = await _existing_names(session, tokens)
        if len(known) >= 2:
            total, items = await query_by_tags(session, known, "all", page, page_size)
    if total == 0:
        total, items = await query_by_text_tokens(session, tokens, page, page_size)
    return TopicResult(name, "phrase", tokens, total, items)


async def related_items(
    session: AsyncSession, item: Item, limit: int = RELATED_LIMIT
) -> list[Item]:
    tag_ids = [t.id for t in (item.tags or [])]
    if not tag_ids:
        return []
    overlap = (
        select(item_tags.c.item_id, func.count().label("n"))
        .where(item_tags.c.tag_id.in_(tag_ids), item_tags.c.item_id != item.id)
        .group_by(item_tags.c.item_id)
        .subquery()
    )
    rows = (
        await session.execute(
            select(Item)
            .join(overlap, overlap.c.item_id == Item.id)
            .order_by(overlap.c.n.desc(), Item.created_at.desc(), Item.id.desc())
            .limit(limit)
        )
    ).scalars().all()
    return list(rows)
