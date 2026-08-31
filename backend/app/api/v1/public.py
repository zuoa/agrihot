"""Public read-only endpoints (anonymous)."""
from datetime import date as date_type
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_session
from ...models import Daily, Item, Tag
from ...schemas import (DailyListItem, DailyListOut, DailyOut, ItemListOut,
                        ItemOut, SourceOut, TagOut)

router = APIRouter(prefix="/api/v1", tags=["public"])

PAGE_SIZE_MAX = 100


def _to_item_out(item: Item) -> ItemOut:
    return ItemOut(
        id=item.id,
        title=item.title,
        url=item.url,
        summary=item.summary,
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
        created_at=item.created_at,
    )


@router.get("/items", response_model=ItemListOut)
async def list_items(
    mode: str = Query(default="all", pattern="^(all|selected)$"),
    window: str | None = Query(default=None, pattern="^(24h|7d)$"),
    category: str | None = None,
    tag: str | None = None,
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


@router.get("/items/{item_id}", response_model=ItemOut)
async def get_item(item_id: int, session: AsyncSession = Depends(get_session)) -> ItemOut:
    item = await session.get(Item, item_id)
    if item is None:
        raise HTTPException(
            status_code=404,
            detail={"title": "Not Found", "status": 404, "detail": "条目不存在"},
        )
    # 打开详情页计一次阅读；原子自增避免并发丢失
    await session.execute(
        update(Item).where(Item.id == item_id).values(view_count=Item.view_count + 1)
    )
    await session.commit()
    await session.refresh(item)
    return _to_item_out(item)


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
