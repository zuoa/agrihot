"""Admin console endpoints (password login -> HMAC token)."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ...database import get_session
from ...models import Item
from ...schemas import AdminItemUpdate, AdminLoginIn, AdminLoginOut, ItemOut
from ...security import (check_admin_password, issue_admin_token, problem,
                         require_admin)
from ...services import ingest_service
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
