"""API-key authentication for ingest endpoints."""
import hashlib
import hmac
from datetime import datetime, timezone

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
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


# ---------- admin console (password from .env, stateless HMAC token) ----------

def issue_admin_token() -> str:
    """Derive the session token from the configured password (stateless)."""
    return hmac.new(
        settings.admin_password.encode(), b"agrihot-admin-v1", hashlib.sha256
    ).hexdigest()


def check_admin_password(raw: str) -> bool:
    return bool(settings.admin_password) and hmac.compare_digest(
        raw.encode(), settings.admin_password.encode()
    )


async def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    if not settings.admin_password:
        raise problem(403, "Forbidden", "管理功能未启用（未配置 ADMIN_PASSWORD）")
    if not x_admin_token or not hmac.compare_digest(
        x_admin_token.encode(), issue_admin_token().encode()
    ):
        raise problem(401, "Unauthorized", "管理令牌无效或已过期")
