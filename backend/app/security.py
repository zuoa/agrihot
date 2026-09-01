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

ADMIN_TOKEN_TTL_SECONDS = 7 * 24 * 3600  # 7 days
_ADMIN_TOKEN_PREFIX = "agrihot-admin-v2"


def issue_admin_token(now: datetime | None = None) -> str:
    """HMAC token with an expiry timestamp: `{hex_sig}.{exp_unix}`."""
    now = now or datetime.now(timezone.utc)
    exp = int(now.timestamp()) + ADMIN_TOKEN_TTL_SECONDS
    sig = hmac.new(
        settings.admin_password.encode(),
        f"{_ADMIN_TOKEN_PREFIX}|{exp}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"{sig}.{exp}"


def verify_admin_token(token: str) -> bool:
    if not settings.admin_password or not token or "." not in token:
        return False
    sig, _, exp_s = token.partition(".")
    try:
        exp = int(exp_s)
    except ValueError:
        return False
    if exp < int(datetime.now(timezone.utc).timestamp()):
        return False
    expected = hmac.new(
        settings.admin_password.encode(),
        f"{_ADMIN_TOKEN_PREFIX}|{exp}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(sig, expected)


def check_admin_password(raw: str) -> bool:
    return bool(settings.admin_password) and hmac.compare_digest(
        raw.encode(), settings.admin_password.encode()
    )


async def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    if not settings.admin_password:
        raise problem(403, "Forbidden", "管理功能未启用（未配置 ADMIN_PASSWORD）")
    if not x_admin_token or not verify_admin_token(x_admin_token):
        raise problem(401, "Unauthorized", "管理令牌无效或已过期")
