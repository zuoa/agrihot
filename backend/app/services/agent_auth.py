"""Shared HTTP/MCP read-key authentication and per-key request budget."""
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from limits import parse
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import get_session
from ..models import ApiKey, hash_api_key, utcnow
from ..security import problem

_budget = FixedWindowRateLimiter(MemoryStorage())
_bearer = HTTPBearer(auto_error=False, scheme_name="AgentReadKey", description="管理员签发的 Agent 读取 Key，与推送 Key 分开。")


async def authenticate(session: AsyncSession, authorization: str | None) -> ApiKey:
    scheme, _, raw = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not raw.strip():
        raise problem(401, "Unauthorized", "请使用 Authorization: Bearer <读取Key>")
    key_hash = hash_api_key(raw)
    key = (await session.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))).scalar_one_or_none()
    if key is None or not key.is_active:
        raise problem(401, "Unauthorized", "读取 Key 无效或已停用")
    if key.purpose != "read":
        raise problem(403, "Forbidden", "此 Key 没有 Agent 读取权限")
    if not _budget.hit(parse(settings.agent_rate_limit), key_hash):
        raise problem(429, "Too Many Requests", "超出 Agent 读取频率限制，请稍后重试")
    key.last_used_at = utcnow()
    await session.commit()
    return key


async def require_read_key(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> ApiKey:
    authorization = f"{credentials.scheme} {credentials.credentials}" if credentials else None
    return await authenticate(session, authorization)
