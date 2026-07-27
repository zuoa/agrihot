"""Agent push endpoints (require X-API-Key)."""
from fastapi import APIRouter, BackgroundTasks, Depends, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import settings
from ...database import get_session
from ...models import ApiKey
from ...schemas import IngestBatchIn, IngestItemIn, IngestResultOut
from ...security import problem, require_api_key
from ...services import ingest_service, scoring_service


def _key_func(request: Request) -> str:
    return request.headers.get("x-api-key") or get_remote_address(request)


limiter = Limiter(key_func=_key_func)

router = APIRouter(prefix="/api/v1/ingest", tags=["ingest"])


@router.post("/items", response_model=IngestResultOut, status_code=200)
@limiter.limit(settings.ingest_rate_limit)
async def push_item(
    request: Request,
    payload: IngestItemIn,
    background_tasks: BackgroundTasks,
    api_key: ApiKey = Depends(require_api_key),
    session: AsyncSession = Depends(get_session),
) -> IngestResultOut:
    """推送单条资讯。重复内容会合并信源并返回 duplicate，不会报错。"""
    result = await ingest_service.ingest_item(session, payload, pushed_by=api_key.name)
    await session.commit()
    if result.status == "created" and result.item_id is not None:
        background_tasks.add_task(scoring_service.score_and_mark, result.item_id)
    return result


@router.post("/items/batch", response_model=dict, status_code=200)
@limiter.limit(settings.ingest_rate_limit)
async def push_items_batch(
    request: Request,
    payload: IngestBatchIn,
    background_tasks: BackgroundTasks,
    api_key: ApiKey = Depends(require_api_key),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """批量推送（≤50 条），逐条返回 created / duplicate / invalid。"""
    results = await ingest_service.ingest_batch(session, payload.items, pushed_by=api_key.name)
    await session.commit()
    for r in results:
        if r.status == "created" and r.item_id is not None:
            background_tasks.add_task(scoring_service.score_and_mark, r.item_id)
    created = sum(1 for r in results if r.status == "created")
    dup = sum(1 for r in results if r.status == "duplicate")
    invalid = sum(1 for r in results if r.status == "invalid")
    return {
        "total": len(results),
        "created": created,
        "duplicate": dup,
        "invalid": invalid,
        "results": [r.model_dump() for r in results],
    }


@router.delete("/items/{item_id}", status_code=200)
@limiter.limit(settings.ingest_rate_limit)
async def delete_item(
    request: Request,
    item_id: int,
    api_key: ApiKey = Depends(require_api_key),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """删除一条资讯（如下架测试/违规内容），并清理日报中的引用。"""
    if not await ingest_service.delete_item(session, item_id):
        raise problem(404, "Not Found", "条目不存在")
    await session.commit()
    return {"status": "deleted", "item_id": item_id}
