"""API-key authentication for ingest endpoints."""
from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_session
from .models import ApiKey, hash_api_key


def problem(status: int, title: str, detail: str = "") -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={"title": title, "status": status, "detail": detail},
    )


async def require_api_key(
    x_api_key: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> ApiKey:
    if not x_api_key:
        raise problem(401, "Unauthorized", "缺少 X-API-Key 请求头")
    key = (
        await session.execute(
            select(ApiKey).where(ApiKey.key_hash == hash_api_key(x_api_key))
        )
    ).scalar_one_or_none()
    if key is None or not key.is_active:
        raise problem(401, "Unauthorized", "API Key 无效或已停用")
    key.last_used_at = datetime.now(timezone.utc)
    await session.commit()
    return key
