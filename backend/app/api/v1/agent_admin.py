"""Private application approval and search-index operations."""
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...agent_schemas import ApplicationReviewIn
from ...database import get_session
from ...models import AgentApplication, ApiKey, hash_api_key, utcnow
from ...security import problem, require_admin
from ...services import search_index_service
from ...services.seo_service import site_origin

router = APIRouter(prefix="/api/v1/admin/agent", dependencies=[Depends(require_admin)], include_in_schema=False)


@router.get("/push-guide")
async def push_guide():
    content = (Path(__file__).parents[2] / "private_docs" / "agent-push.md").read_text(encoding="utf-8")
    return {"content": content.replace("https://agrihot.com", site_origin())}


def application_out(row):
    return {name: getattr(row, name) for name in ("id", "name", "contact", "use_case", "status", "note", "api_key_id", "created_at", "reviewed_at")}


@router.get("/applications")
async def applications(response: Response, page: int = Query(default=1, ge=1), session: AsyncSession = Depends(get_session)):
    response.headers["Cache-Control"] = "no-store"
    rows = (await session.execute(select(AgentApplication).order_by(AgentApplication.id.desc()).offset((page - 1)*50).limit(51))).scalars().all()
    return {"applications": [application_out(row) for row in rows[:50]], "has_more": len(rows) > 50}


@router.post("/applications/{application_id}/review")
async def review(application_id: int, payload: ApplicationReviewIn, response: Response, session: AsyncSession = Depends(get_session)):
    response.headers["Cache-Control"] = "no-store"
    application = (await session.execute(select(AgentApplication).where(AgentApplication.id == application_id).with_for_update())).scalar_one_or_none()
    if application is None:
        raise problem(404, "Not Found", "申请不存在")
    if application.status != "pending":
        raise problem(409, "Conflict", "此申请已处理，请在 API Key 页面管理已签发的 Key")
    raw = None
    if payload.decision == "approve":
        raw = f"agri_read_{secrets.token_urlsafe(32)}"
        key = ApiKey(name=application.name, purpose="read", key_hash=hash_api_key(raw))
        session.add(key)
        await session.flush()
        application.api_key_id = key.id
        application.status = "approved"
    else:
        application.status = "rejected"
    application.reviewed_at, application.note = utcnow(), payload.note.strip()
    await session.commit()
    return {"application": application_out(application), "key": raw}


@router.get("/index")
async def index_status(session: AsyncSession = Depends(get_session)):
    return await search_index_service.status(session)


@router.post("/index/backfill")
async def backfill(session: AsyncSession = Depends(get_session)):
    return {"queued": await search_index_service.enqueue_backfill(session, force=True)}
