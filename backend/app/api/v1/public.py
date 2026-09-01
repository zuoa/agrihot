"""Public read-only endpoints (anonymous)."""
from datetime import date as date_type
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_session
from ...models import Daily, Item, PaperMeta, Tag
from ...schemas import (DailyListItem, DailyListOut, DailyOut, DirectionOut,
                        ItemListOut, ItemOut, PaperAuthorOut, PaperCardOut,
                        PaperMetaOut, SourceOut, StatsOut, TagOut, ViewOut)

router = APIRouter(prefix="/api/v1", tags=["public"])

PAGE_SIZE_MAX = 100


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


def _to_item_out(item: Item) -> ItemOut:
    return ItemOut(
        id=item.id,
        title=item.title,
        url=item.url,
        summary=item.summary,
        summary_zh=item.summary_zh,
        content=item.content,
        source_name=item.source_name,
        source_url=item.source_url,
        published_at=item.published_at,
        category=item.category,
        cover_url=item.cover_url,
        hotness=item.hotness,
        is_selected=item.is_selected,
        score=item.score,
        score_detail=item.score_detail,
        sources=[SourceOut(**s) for s in (item.sources or [])],
        tags=[t.name for t in item.tags],
        view_count=item.view_count,
        doi=item.doi,
        paper=_to_paper_out(item),
        created_at=item.created_at,
    )


@router.get("/items", response_model=ItemListOut)
async def list_items(
    mode: str = Query(default="all", pattern="^(all|selected)$"),
    window: str | None = Query(default=None, pattern="^(24h|7d)$"),
    category: str | None = None,
    tag: str | None = None,
    direction: str | None = None,
    q: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=PAGE_SIZE_MAX),
    session: AsyncSession = Depends(get_session),
) -> ItemListOut:
    stmt = select(Item)
    count_stmt = select(func.count(Item.id))

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
    if tag:
        stmt = stmt.where(Item.tags.any(Tag.name == tag))
        count_stmt = count_stmt.where(Item.tags.any(Tag.name == tag))
    if direction:
        stmt = stmt.join(Item.paper).where(PaperMeta.direction == direction)
        count_stmt = count_stmt.join(Item.paper).where(PaperMeta.direction == direction)
    if q:
        like = f"%{q}%"
        cond = or_(Item.title.ilike(like), Item.summary.ilike(like))
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
    return ItemListOut(
        total=total, page=page, page_size=page_size,
        items=[_to_item_out(i) for i in rows],
    )


def _item_404() -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"title": "Not Found", "status": 404, "detail": "条目不存在"},
    )


@router.get("/items/{item_id}", response_model=ItemOut)
async def get_item(item_id: int, session: AsyncSession = Depends(get_session)) -> ItemOut:
    item = await session.get(Item, item_id)
    if item is None:
        raise _item_404()
    return _to_item_out(item)


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


async def _daily_out(d: Daily, session: AsyncSession) -> DailyOut:
    items: list[Item] = []
    for iid in (d.item_ids or []):
        item = await session.get(Item, iid)
        if item is not None:
            items.append(item)
    return DailyOut(
        date=d.date, title=d.title, highlights=d.highlights or [],
        content=d.content, items=[_to_item_out(i) for i in items],
    )


@router.get("/dailies/latest", response_model=DailyOut)
async def latest_daily(session: AsyncSession = Depends(get_session)) -> DailyOut:
    d = (
        await session.execute(select(Daily).order_by(Daily.date.desc()).limit(1))
    ).scalar_one_or_none()
    if d is None:
        raise HTTPException(status_code=404, detail={"title": "Not Found", "status": 404, "detail": "暂无日报"})
    return await _daily_out(d, session)


@router.get("/dailies/{day}", response_model=DailyOut)
async def get_daily(day: date_type, session: AsyncSession = Depends(get_session)) -> DailyOut:
    d = (
        await session.execute(select(Daily).where(Daily.date == day))
    ).scalar_one_or_none()
    if d is None:
        raise HTTPException(status_code=404, detail={"title": "Not Found", "status": 404, "detail": "该日期暂无日报"})
    return await _daily_out(d, session)
