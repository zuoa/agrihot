"""One content service for Skill HTTP calls and MCP tools."""
from collections import defaultdict
from datetime import date

from sqlalchemy import and_, case, exists, func, literal_column, or_, select

from ..agent_schemas import ContentFilters, ItemListIn, SearchIn
from ..config import settings
from ..models import Daily, Item, PaperMeta, SearchChunk, SearchJob, Tag
from ..security import problem
from . import embedding_service
from .search_index_service import tokens
from .seo_service import abs_url
from .taxonomy_service import filter_conditions, keyword_condition
from .taxonomy_catalog import equivalent_names


def filters(params: ContentFilters):
    terms = []
    if params.category:
        terms.append(Item.category == params.category)
    for tag in params.tags:
        terms.append(Item.tags.any(Tag.name.in_(equivalent_names(tag))))
    try:
        terms.extend(filter_conditions(params.topic, params.technologies))
    except ValueError as exc:
        raise problem(422, "Unprocessable Entity", str(exc))
    if params.direction:
        terms.append(Item.paper.has(PaperMeta.direction == params.direction))
    if params.since:
        terms.append(Item.created_at >= params.since)
    if params.until:
        terms.append(Item.created_at <= params.until)
    return terms


def item_out(item: Item, full: bool = False):
    from ..api.v1.public import _to_item_out

    data = _to_item_out(item).model_dump(mode="json")
    data["site_url"] = abs_url(f"/items/{item.id}")
    data["original_url"] = item.url
    data["has_fulltext"] = bool(item.content and item.content.strip())
    data["content_status"] = "available" if data["has_fulltext"] else "missing"
    if not full:
        data.pop("content", None)
        data.pop("score_detail", None)
    return data


async def list_items(session, params: ItemListIn):
    conditions = filters(params)
    if params.mode == "selected":
        conditions.append(Item.is_selected.is_(True))
    if params.before_id:
        cursor = await session.get(Item, params.before_id)
        if cursor is None:
            raise problem(422, "Unprocessable Entity", "分页游标已失效，请重新查询")
        conditions.append(or_(Item.created_at < cursor.created_at, and_(Item.created_at == cursor.created_at, Item.id < cursor.id)))
    rows = (await session.execute(select(Item).where(*conditions).order_by(Item.created_at.desc(), Item.id.desc()).limit(params.limit + 1))).scalars().all()
    return {"items": [item_out(item) for item in rows[:params.limit]],
            "next_before_id": rows[params.limit - 1].id if len(rows) > params.limit else None,
            "time_basis": "created_at", "since": params.since, "until": params.until}


async def get_item(session, item_id: int):
    item = await session.get(Item, item_id)
    if item is None:
        raise problem(404, "Not Found", "条目不存在")
    return item_out(item, full=True)


async def list_dailies(session, limit: int = 10, before: date | None = None):
    stmt = select(Daily).order_by(Daily.date.desc()).limit(limit + 1)
    if before:
        stmt = stmt.where(Daily.date < before)
    rows = (await session.execute(stmt)).scalars().all()
    return {"dailies": [{"date": d.date, "title": d.title, "highlights": d.highlights,
                         "site_url": abs_url(f"/dailies/{d.date.isoformat()}")} for d in rows[:limit]],
            "next_before": rows[limit - 1].date if len(rows) > limit else None}


async def get_daily(session, day: date | None = None):
    stmt = select(Daily).order_by(Daily.date.desc()).limit(1)
    if day:
        stmt = stmt.where(Daily.date == day)
    daily = (await session.execute(stmt)).scalar_one_or_none()
    if daily is None:
        raise problem(404, "Not Found", "暂无该日期的日报")
    ids = daily.item_ids or []
    items = (await session.execute(select(Item).where(Item.id.in_(ids)))).scalars().all() if ids else []
    by_id = {item.id: item for item in items}
    return {"date": daily.date, "title": daily.title, "highlights": daily.highlights,
            "content": daily.content, "site_url": abs_url(f"/dailies/{daily.date.isoformat()}"),
            "items": [item_out(by_id[i]) for i in ids if i in by_id]}


async def lexical_candidates(session, params: SearchIn, conditions, fp: str):
    words = list(dict.fromkeys(word for name in equivalent_names(params.q) for word in tokens(name)))[:40]
    if not words:
        return []
    candidates = []
    if session.bind.dialect.name == "postgresql":
        document = func.to_tsvector(literal_column("'simple'"), SearchChunk.lexemes)
        query = func.to_tsquery(literal_column("'simple'"), " | ".join("'" + w.replace("'", "''") + "'" for w in words))
        rank = func.ts_rank_cd(document, query)
        best = (select(SearchChunk.item_id, SearchChunk.text, rank.label("rank"),
                func.row_number().over(partition_by=SearchChunk.item_id, order_by=rank.desc()).label("position"))
            .join(Item, Item.id == SearchChunk.item_id).join(SearchJob, SearchJob.item_id == Item.id)
            .where(*conditions, SearchJob.status.in_(["ready", "lexical"]), SearchChunk.fingerprint == fp, document.op("@@")(query))
            .subquery())
        rows = (await session.execute(select(best.c.item_id, best.c.text, best.c.rank)
            .where(best.c.position == 1).order_by(best.c.rank.desc(), best.c.item_id.desc()).limit(100))).all()
        candidates.extend((i, text) for i, text, _ in rows)
    # Also cover fresh/failed/unindexed rows immediately, including the SQLite test backend.
    matches = [keyword_condition(word, include_content=True) for word in words]
    matches.append(keyword_condition(params.q, include_content=True))
    rank = sum(case((match, 1), else_=0) for match in matches)
    stmt = select(Item).where(*conditions, or_(*matches))
    if session.bind.dialect.name == "postgresql":
        stmt = stmt.where(~exists(select(SearchJob.item_id).where(SearchJob.item_id == Item.id, SearchJob.status.in_(["ready", "lexical"]), SearchJob.fingerprint == fp)))
    raw = (await session.execute(stmt.order_by(rank.desc(), Item.id.desc()).limit(100))).scalars().all()
    for item in raw:
        text = "\n".join(filter(None, [item.title, item.summary_zh or item.summary, item.content]))
        positions = [text.lower().find(w) for w in words if w in text.lower()]
        start = max(0, min(positions, default=0) - 80)
        candidates.append((item.id, text[start:start + 800]))
    return candidates


async def semantic_candidates(session, params, conditions, fp):
    vector = await embedding_service.query_vector(params.q)
    if session.bind.dialect.name == "postgresql":
        distance = SearchChunk.embedding.cosine_distance(vector)
        best = (select(SearchChunk.item_id, SearchChunk.text, distance.label("distance"),
                func.row_number().over(partition_by=SearchChunk.item_id, order_by=distance).label("position"))
            .join(Item, Item.id == SearchChunk.item_id).join(SearchJob, SearchJob.item_id == Item.id)
            .where(*conditions, SearchJob.status == "ready", SearchChunk.fingerprint == fp, SearchChunk.embedding.is_not(None))
            .subquery())
        rows = (await session.execute(select(best.c.item_id, best.c.text).where(best.c.position == 1)
            .order_by(best.c.distance, best.c.item_id.desc()).limit(100))).all()
        return [(i, text) for i, text in rows]
    # SQLite only: deterministic vectors in business tests. Production uses pgvector.
    import math

    chunks = (await session.execute(select(SearchChunk).join(Item).join(SearchJob, SearchJob.item_id == Item.id)
        .where(*conditions, SearchJob.status == "ready", SearchChunk.fingerprint == fp, SearchChunk.embedding.is_not(None)))).scalars().all()
    def cosine(chunk):
        v = chunk.embedding
        return sum(a*b for a, b in zip(v, vector)) / (math.sqrt(sum(x*x for x in v)) * math.sqrt(sum(x*x for x in vector)))
    seen, result = set(), []
    for chunk in sorted(chunks, key=cosine, reverse=True):
        if chunk.item_id not in seen:
            seen.add(chunk.item_id)
            result.append((chunk.item_id, chunk.text))
    return result[:100]


def fuse(lexical, semantic, limit):
    scores = defaultdict(float)
    snippets = {}
    for candidates in (lexical, semantic):
        seen = set()
        for item_id, text in candidates:
            if item_id in seen:
                continue
            seen.add(item_id)
            scores[item_id] += 1 / (60 + len(seen))
            snippets.setdefault(item_id, text)
    ids = sorted(scores, key=lambda i: (-scores[i], -i))[:limit]
    return [(i, scores[i], snippets[i]) for i in ids]


async def search(session, params: SearchIn):
    fp, conditions = embedding_service.fingerprint(), filters(params)
    lexical = await lexical_candidates(session, params, conditions, fp)
    semantic, reasons = [], []
    if not settings.embedding_api_key:
        reasons.append("embedding_not_configured")
    else:
        incomplete = (await session.execute(select(Item.id).where(*conditions, ~exists(select(SearchJob.item_id).where(SearchJob.item_id == Item.id, SearchJob.status == "ready", SearchJob.fingerprint == fp))).limit(1))).first()
        if incomplete:
            reasons.append("index_incomplete")
        try:
            semantic = await semantic_candidates(session, params, conditions, fp)
        except embedding_service.EmbeddingUnavailable as exc:
            reasons.append(str(exc))
    ranked = fuse(lexical, semantic, params.limit)
    ids = [i for i, _, _ in ranked]
    rows = (await session.execute(select(Item).where(Item.id.in_(ids)))).scalars().all() if ids else []
    by_id = {item.id: item for item in rows}
    return {"query": params.q, "mode": "hybrid" if semantic else "keyword",
            "degraded": bool(reasons), "degradation_reasons": reasons,
            "time_basis": "created_at", "since": params.since, "until": params.until,
            "items": [{**item_out(by_id[i]), "relevance": round(score, 6), "snippet": text[:800]} for i, score, text in ranked if i in by_id]}
