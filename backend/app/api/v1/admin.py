"""Admin console endpoints (password login -> HMAC token)."""
from datetime import date as date_type

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import settings
from ...database import get_session
from ...models import Item
from ...schemas import (AdminItemUpdate, AdminLoginIn, AdminLoginOut,
                        DailyGenerateOut, ItemOut)
from ...security import (check_admin_password, issue_admin_token, problem,
                         require_admin)
from ...services import (content_service, daily_service, ingest_service,
                         scoring_service)
from .ingest import limiter  # shared app limiter; login keys on remote IP
from .public import _to_item_out

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.post("/login", response_model=AdminLoginOut)
@limiter.limit("10/minute")  # brute-force guard
async def login(request: Request, payload: AdminLoginIn) -> AdminLoginOut:
    if not check_admin_password(payload.password):
        raise problem(401, "Unauthorized", "密码错误")
    return AdminLoginOut(token=issue_admin_token())


@router.patch("/items/{item_id}", response_model=ItemOut)
async def update_item(
    item_id: int,
    payload: AdminItemUpdate,
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ItemOut:
    item = await session.get(Item, item_id)
    if item is None:
        raise problem(404, "Not Found", "条目不存在")
    updates = payload.model_dump(exclude_unset=True)
    tags = updates.pop("tags", None)
    for field, value in updates.items():
        if field == "category":
            value = ingest_service._normalize_category(value)
        setattr(item, field, value)
    if tags is not None:
        item.tags = await ingest_service._get_or_create_tags(session, tags)
    await session.commit()
    await session.refresh(item)
    return _to_item_out(item)


@router.post("/items/{item_id}/fetch-content", response_model=ItemOut)
async def fetch_item_content(
    item_id: int,
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ItemOut:
    """手动触发全文抓取（Jina Reader）：成功后保存并重新评分。

    已有全文时调用会覆盖重抓（前端负责确认）；抓取失败不改库、不重评分。
    """
    item = await session.get(Item, item_id)
    if item is None:
        raise problem(404, "Not Found", "条目不存在")
    if not settings.content_fetch_enabled:
        raise problem(503, "Service Unavailable", "全文抓取功能未启用")
    text = await content_service.fetch_fulltext(item.url)
    if text is None:
        raise problem(502, "Bad Gateway", "全文抓取失败，请检查原文链接或稍后重试")
    item.content = text
    if settings.deepseek_api_key:
        if await scoring_service.score_item(session, item) is not None:
            await scoring_service.refresh_day_selection(session, item.created_at)
    await session.commit()
    await session.refresh(item)
    return _to_item_out(item)


@router.delete("/items/{item_id}", status_code=200)
async def admin_delete_item(
    item_id: int,
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if not await ingest_service.delete_item(session, item_id):
        raise problem(404, "Not Found", "条目不存在")
    await session.commit()
    return {"status": "deleted", "item_id": item_id}


@router.post("/dailies/{day}/generate", response_model=DailyGenerateOut)
async def generate_daily(
    day: date_type,
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> DailyGenerateOut:
    """手动生成/重新生成指定日期的日报（已有日报会被覆盖）。"""
    daily = await daily_service.generate_daily(session, day)
    if daily is None:
        raise problem(404, "Not Found", "该日期没有收录资讯，无法生成日报")
    await session.commit()
    return DailyGenerateOut(
        date=daily.date, title=daily.title,
        highlight_count=len(daily.highlights or []),
        item_count=len(daily.item_ids or []),
    )
