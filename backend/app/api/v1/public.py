"""Public read-only endpoints (anonymous)."""
from datetime import date as date_type
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer, noload, raiseload, selectinload

from ...database import get_session
from ...models import Daily, Item, ItemClassification, PaperMeta, Tag
from ...schemas import (DailyListItem, DailyListOut, DailyOut, DailySummaryOut,
                        DirectionOut, ItemListOut, ItemOut, ItemSummaryListOut,
                        ItemSummaryOut, PaperAuthorOut, PaperCardOut,
                        PaperMetaOut, SourceOut, StatsOut, TagOut, TopicOut,
                        TopicSummaryOut, ViewOut)
from ...services.topic_service import (apply_tag_match, effective_phrases,
                                       item_slug, parse_tag_query,
                                       related_items, resolve_topic)
from ...services import embedding_service, taxonomy_service
from ...services.taxonomy_catalog import canonical_name

router = APIRouter(prefix="/api/v1", tags=["public"])

PAGE_SIZE_MAX = 100


def _list_load_options(compact: bool):
    # Keep full text and editorial evidence out of list queries as well as JSON.
    if not compact:
        return ()
    return (
        defer(Item.content, raiseload=True),
        defer(Item.score_detail, raiseload=True),
        noload(Item.classification),
    )


def _detail_load_options():
    # One article loads the rows the page renders. The audit blob stays out.
    return (
        selectinload(Item.tags),
        selectinload(Item.paper),
        selectinload(Item.topic_links),
        selectinload(Item.search_job),
        selectinload(Item.classification).load_only(
            ItemClassification.status, ItemClassification.locked,
        ),
    )


def _to_paper_out(item: Item) -> PaperMetaOut | None:
    meta = item.paper
    if meta is None:
        return None
    card = None
    if isinstance(meta.card, dict) and meta.card.get("tldr"):
        card = PaperCardOut(
            tldr=str(meta.card.get("tldr") or ""),
            method=str(meta.card.get("method") or ""),
            finding=str(meta.card.get("finding") or ""),
            direction=str(meta.card.get("direction") or ""),
            opportunity=str(meta.card.get("opportunity") or ""),
        )
    authors: list[PaperAuthorOut] = []
    for raw in meta.authors or []:
        if isinstance(raw, dict) and raw.get("name"):
            authors.append(
                PaperAuthorOut(name=str(raw["name"]), orcid=raw.get("orcid"))
            )
    return PaperMetaOut(
        doi=item.doi,
        openalex_id=meta.openalex_id,
        authors=authors,
        venue=meta.venue,
        cited_by_count=meta.cited_by_count or 0,
        oa_url=meta.oa_url,
        card=card,
        direction=meta.direction,
        ingested_from=meta.ingested_from or "agent",
    )


def _to_item_out(item: Item, *, compact: bool = False) -> ItemOut | ItemSummaryOut:
    tags = list(dict.fromkeys(canonical_name(t.name) for t in item.tags))
    phrases = effective_phrases(tags, item.search_phrases)
    detail = {} if compact else {
        "content": item.content,
        "score_detail": item.score_detail,
        "classification": ({"status": item.classification.status, "locked": item.classification.locked}
                            if item.classification else {}),
    }
    model = ItemSummaryOut if compact else ItemOut
    return model(
        **detail,
        id=item.id,
        title=item.title,
        url=item.url,
        summary=item.summary,
        summary_zh=item.summary_zh,
        source_name=item.source_name,
        source_url=item.source_url,
        published_at=item.published_at,
        category=item.category,
        cover_url=item.cover_url,
        hotness=item.hotness,
        is_selected=item.is_selected,
        embedding_ready=bool(item.search_job and item.search_job.status == "ready"
                             and item.search_job.fingerprint == embedding_service.fingerprint()),
        score=item.score,
        sources=[SourceOut(**s) for s in (item.sources or [])],
        tags=tags,
        primary_topic=next((taxonomy_service.topic_ref(l.topic_code) for l in item.topic_links if l.is_primary), None),
        secondary_topics=[taxonomy_service.topic_ref(l.topic_code) for l in item.topic_links if not l.is_primary],
        search_phrases=phrases,
        slug=item_slug(item.id, item.title, phrases),
        view_count=item.view_count,
        doi=item.doi,
        paper=_to_paper_out(item),
        created_at=item.created_at,
    )


@router.get("/items", response_model=ItemListOut | ItemSummaryListOut)
async def list_items(
    mode: str = Query(default="all", pattern="^(all|selected)$"),
    window: str | None = Query(default=None, pattern="^(24h|7d)$"),
    category: str | None = None,
    tag: str | None = None,
    tags: str | None = None,
    match: str = Query(default="all", pattern="^(all|any)$"),
    direction: str | None = None,
    topic: str | None = None,
    technologies: list[str] = Query(default=[]),
    q: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=PAGE_SIZE_MAX),
    compact: bool = False,
    session: AsyncSession = Depends(get_session),
) -> ItemListOut | ItemSummaryListOut:
    stmt = select(Item).options(*_list_load_options(compact))
    count_stmt = select(func.count(Item.id))
    try:
        conditions = taxonomy_service.filter_conditions(topic, technologies)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    stmt, count_stmt = stmt.where(*conditions), count_stmt.where(*conditions)

    if mode == "selected":
        stmt = stmt.where(Item.is_selected.is_(True))
        count_stmt = count_stmt.where(Item.is_selected.is_(True))
    if window:
        since = datetime.now(timezone.utc) - (
            timedelta(hours=24) if window == "24h" else timedelta(days=7)
        )
        stmt = stmt.where(Item.created_at >= since)
        count_stmt = count_stmt.where(Item.created_at >= since)
    if category:
        stmt = stmt.where(Item.category == category)
        count_stmt = count_stmt.where(Item.category == category)
    tag_names = parse_tag_query(tag, tags)
    if tag_names:
        stmt = apply_tag_match(stmt, tag_names, match)
        count_stmt = apply_tag_match(count_stmt, tag_names, match)
    if direction:
        stmt = stmt.join(Item.paper).where(PaperMeta.direction == direction)
        count_stmt = count_stmt.join(Item.paper).where(PaperMeta.direction == direction)
    if q:
        cond = taxonomy_service.keyword_condition(q)
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)

    total = (await session.execute(count_stmt)).scalar_one()
    rows = (
        await session.execute(
            stmt.order_by(Item.created_at.desc(), Item.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    model = ItemSummaryListOut if compact else ItemListOut
    return model(
        total=total, page=page, page_size=page_size,
        items=[_to_item_out(i, compact=compact) for i in rows],
    )


@router.get("/taxonomy")
async def get_taxonomy(session: AsyncSession = Depends(get_session)):
    return await taxonomy_service.tree(session)


@router.get("/taxonomy/facets")
async def get_topic_facets(topic: str | None = None, category: str | None = None,
                           technologies: list[str] = Query(default=[]), session: AsyncSession = Depends(get_session)):
    try:
        return await taxonomy_service.facets(session, topic, category, technologies)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/taxonomy/{slug}")
async def get_taxonomy_node(slug: str, session: AsyncSession = Depends(get_session)):
    data = await taxonomy_service.tree(session)
    for parent in data["topics"]:
        for node in [parent, *parent["children"]]:
            if slug in (node["slug"], node["code"]):
                return node | {"parent": parent if node["parent_code"] else None}
    raise HTTPException(status_code=404, detail="主题不存在")


def _item_404() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"title": "Not Found", "status": 404, "detail": "条目不存在"},
    )


@router.get("/items/{item_id}", response_model=ItemOut)
async def get_item(item_id: int, session: AsyncSession = Depends(get_session)) -> ItemOut:
    item = await session.get(Item, item_id, options=_detail_load_options())
    if item is None:
        raise _item_404()
    return _to_item_out(item)


@router.get("/items/{item_id}/related", response_model=ItemListOut | ItemSummaryListOut)
async def list_related_items(
    item_id: int,
    compact: bool = False,
    session: AsyncSession = Depends(get_session),
) -> ItemListOut | ItemSummaryListOut:
    load_options = _list_load_options(compact)
    item = await session.get(Item, item_id, options=load_options)
    if item is None:
        raise _item_404()
    rows = await related_items(session, item, load_options=load_options)
    model = ItemSummaryListOut if compact else ItemListOut
    return model(
        total=len(rows), page=1, page_size=len(rows) or 1,
        items=[_to_item_out(i, compact=compact) for i in rows],
    )


@router.post("/items/{item_id}/view", response_model=ViewOut)
async def record_item_view(
    item_id: int, session: AsyncSession = Depends(get_session)
) -> ViewOut:
    item = await session.get(Item, item_id)
    if item is None:
        raise _item_404()
    # 原子自增避免并发丢失；是否计为阅读由前端在可见停留后调用本接口决定
    await session.execute(
        update(Item).where(Item.id == item_id).values(view_count=Item.view_count + 1)
    )
    await session.commit()
    await session.refresh(item)
    return ViewOut(view_count=item.view_count)


@router.get("/stats", response_model=StatsOut)
async def site_stats(session: AsyncSession = Depends(get_session)) -> StatsOut:
    items, views, since = (
        await session.execute(
            select(
                func.count(Item.id),
                func.coalesce(func.sum(Item.view_count), 0),
                func.min(Item.created_at),
            )
        )
    ).one()
    selected = (
        await session.execute(
            select(func.count(Item.id)).where(Item.is_selected.is_(True))
        )
    ).scalar_one()
    cat_rows = (
        await session.execute(
            select(Item.category, func.count(Item.id)).group_by(Item.category)
        )
    ).all()
    dailies = (await session.execute(select(func.count(Daily.id)))).scalar_one()
    tags = (await session.execute(select(func.count(Tag.id)))).scalar_one()
    sources = (
        await session.execute(
            select(func.count(func.distinct(Item.source_name))).where(
                Item.source_name != ""
            )
        )
    ).scalar_one()
    return StatsOut(
        items=items,
        by_category={name: count for name, count in cat_rows},
        selected=selected,
        dailies=dailies,
        tags=tags,
        sources=sources,
        views=int(views or 0),
        since=since,
    )


@router.get("/paper-directions", response_model=list[DirectionOut])
async def list_paper_directions(
    session: AsyncSession = Depends(get_session),
) -> list[DirectionOut]:
    rows = (
        await session.execute(
            select(PaperMeta.direction, func.count(PaperMeta.item_id))
            .where(PaperMeta.direction.is_not(None), PaperMeta.direction != "")
            .group_by(PaperMeta.direction)
            .order_by(func.count(PaperMeta.item_id).desc())
        )
    ).all()
    return [DirectionOut(name=name, count=count) for name, count in rows]


@router.get("/topics", response_model=TopicOut | TopicSummaryOut)
async def get_topic(
    name: str = Query(..., min_length=1, max_length=400),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=PAGE_SIZE_MAX),
    compact: bool = False,
    session: AsyncSession = Depends(get_session),
) -> TopicOut | TopicSummaryOut:
    """Resolve an atomic tag or a space-separated long-tail phrase. Never writes Tag rows."""
    result = await resolve_topic(
        session, name, page=page, page_size=page_size,
        load_options=_list_load_options(compact),
    )
    model = TopicSummaryOut if compact else TopicOut
    return model(
        name=result.name,
        kind=result.kind,
        tokens=result.tokens,
        total=result.total,
        page=page,
        page_size=page_size,
        items=[_to_item_out(i, compact=compact) for i in result.items],
    )


@router.get("/tags", response_model=list[TagOut])
async def list_tags(session: AsyncSession = Depends(get_session)) -> list[TagOut]:
    rows = (
        await session.execute(
            select(Tag.name, func.count(Item.id))
            .join(Tag.items)
            .group_by(Tag.name)
            .having(func.count(Item.id) > 0)
            .order_by(func.count(Item.id).desc())
        )
    ).all()
    return [TagOut(name=name, count=count) for name, count in rows]


@router.get("/dailies", response_model=DailyListOut)
async def list_dailies(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=PAGE_SIZE_MAX),
    session: AsyncSession = Depends(get_session),
) -> DailyListOut:
    total = (await session.execute(select(func.count(Daily.id)))).scalar_one()
    rows = (
        await session.execute(
            select(Daily).order_by(Daily.date.desc())
            .offset((page - 1) * page_size).limit(page_size)
        )
    ).scalars().all()
    return DailyListOut(
        total=total,
        dailies=[
            DailyListItem(
                date=d.date, title=d.title,
                highlight_count=len(d.highlights or []),
                item_count=len(d.item_ids or []),
            )
            for d in rows
        ],
    )


async def _daily_out(
    d: Daily, session: AsyncSession, *, compact: bool = False,
) -> DailyOut | DailySummaryOut:
    ids = d.item_ids or []
    rows = (await session.execute(
        select(Item).where(Item.id.in_(ids)).options(*_list_load_options(compact))
    )).scalars().all() if ids else []
    by_id = {item.id: item for item in rows}
    model = DailySummaryOut if compact else DailyOut
    return model(
        date=d.date, title=d.title, highlights=d.highlights or [],
        content=d.content, items=[_to_item_out(by_id[i], compact=compact) for i in ids if i in by_id],
    )


@router.get("/dailies/latest", response_model=DailyOut | DailySummaryOut)
async def latest_daily(
    compact: bool = False, session: AsyncSession = Depends(get_session),
) -> DailyOut | DailySummaryOut:
    d = (
        await session.execute(select(Daily).order_by(Daily.date.desc()).limit(1))
    ).scalar_one_or_none()
    if d is None:
        raise HTTPException(status_code=404, detail={"title": "Not Found", "status": 404, "detail": "暂无日报"})
    return await _daily_out(d, session, compact=compact)


@router.get("/dailies/{day}", response_model=DailyOut | DailySummaryOut)
async def get_daily(
    day: date_type, compact: bool = False, session: AsyncSession = Depends(get_session),
) -> DailyOut | DailySummaryOut:
    d = (
        await session.execute(select(Daily).where(Daily.date == day))
    ).scalar_one_or_none()
    if d is None:
        raise HTTPException(status_code=404, detail={"title": "Not Found", "status": 404, "detail": "该日期暂无日报"})
    return await _daily_out(d, session, compact=compact)
