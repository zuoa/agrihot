"""Admin console endpoints (password login -> HMAC token)."""
from datetime import date as date_type
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import settings
from ...database import get_session
from ...models import ApiKey, Daily, Item, PaperMeta, Tag, hash_api_key
from ...schemas import (
    AdminItemUpdate,
    AdminLoginIn,
    AdminLoginOut,
    AdminMeOut,
    AdminSettingsOut,
    AdminSettingsPatch,
    AdminSettingsReadonly,
    ApiKeyCreateIn,
    ApiKeyCreatedOut,
    ApiKeyOut,
    ApiKeyPatchIn,
    BatchDeleteOut,
    BatchFetchIn,
    BatchIdsIn,
    DailyGenerateOut,
    ItemListOut,
    ItemOut,
    JobListOut,
    JobRunIn,
    JobStatusOut,
    LiteratureFetchOut,
    OverviewOut,
    SchedulerInfoOut,
    SettingValueOut,
    WatchlistOut,
)
from ...security import (
    check_admin_password,
    issue_admin_token,
    problem,
    require_admin,
)
from ...services import (
    content_scheduler,
    content_service,
    daily_service,
    ingest_service,
    job_runner,
    literature_scheduler,
    runtime_settings,
    scoring_service,
    watchlist_service,
)
from .ingest import limiter  # shared app limiter; login keys on remote IP
from .public import _to_item_out

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

PAGE_SIZE_MAX = 100


def _as_dt(value) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _job_out(raw: dict) -> JobStatusOut:
    return JobStatusOut(
        name=raw.get("name") or "",
        label=raw.get("label") or "",
        status=raw.get("status") or "idle",
        started_at=_as_dt(raw.get("started_at")),
        finished_at=_as_dt(raw.get("finished_at")),
        stats=raw.get("stats"),
        error=raw.get("error"),
        progress=raw.get("progress"),
    )


# ---------- auth ----------

@router.post("/login", response_model=AdminLoginOut)
@limiter.limit("10/minute")  # brute-force guard
async def login(request: Request, payload: AdminLoginIn) -> AdminLoginOut:
    if not check_admin_password(payload.password):
        raise problem(401, "Unauthorized", "密码错误")
    return AdminLoginOut(token=issue_admin_token())


@router.get("/me", response_model=AdminMeOut)
async def me(_: None = Depends(require_admin)) -> AdminMeOut:
    return AdminMeOut(ok=True)


# ---------- overview ----------

@router.get("/overview", response_model=OverviewOut)
async def overview(
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> OverviewOut:
    items = (await session.execute(select(func.count(Item.id)))).scalar_one()
    selected = (
        await session.execute(select(func.count(Item.id)).where(Item.is_selected.is_(True)))
    ).scalar_one()
    dailies = (await session.execute(select(func.count(Daily.id)))).scalar_one()
    tags = (await session.execute(select(func.count(Tag.id)))).scalar_one()
    missing_content = (
        await session.execute(
            select(func.count(Item.id)).where(
                or_(Item.content.is_(None), Item.content == "")
            )
        )
    ).scalar_one()
    unscored = (
        await session.execute(select(func.count(Item.id)).where(Item.score.is_(None)))
    ).scalar_one()
    tz = settings.daily_timezone
    schedulers = {
        "daily_generate": SchedulerInfoOut(
            enabled=bool(runtime_settings.get("daily_generate_enabled")),
            time=str(runtime_settings.get("daily_generate_time")),
            timezone=tz,
            next_run_at=runtime_settings.next_run_at(
                str(runtime_settings.get("daily_generate_time")), tz, default=(20, 0),
            ),
        ),
        "literature_fetch": SchedulerInfoOut(
            enabled=bool(runtime_settings.get("literature_fetch_enabled")),
            time=str(runtime_settings.get("literature_fetch_time")),
            timezone=tz,
            next_run_at=runtime_settings.next_run_at(
                str(runtime_settings.get("literature_fetch_time")), tz, default=(7, 30),
            ),
        ),
        "content_fetch": SchedulerInfoOut(
            enabled=bool(runtime_settings.get("content_fetch_enabled")),
            time="每 10 分钟",
            timezone=tz,
            next_run_at=content_scheduler.next_run_at(),
        ),
    }
    jobs = [_job_out(j) for j in await job_runner.list_jobs()]
    return OverviewOut(
        items=items, selected=selected, dailies=dailies, tags=tags,
        missing_content=missing_content, unscored=unscored,
        schedulers=schedulers, jobs=jobs,
    )


# ---------- items ----------

@router.get("/items", response_model=ItemListOut)
async def list_admin_items(
    q: str | None = None,
    category: str | None = None,
    tag: str | None = None,
    is_selected: bool | None = None,
    has_content: bool | None = None,
    scored: bool | None = None,
    min_score: int | None = Query(default=None, ge=0, le=100),
    max_score: int | None = Query(default=None, ge=0, le=100),
    ingested_from: str | None = Query(default=None, pattern="^(agent|openalex)$"),
    sort: str = Query(default="created_at", pattern="^(created_at|score|view_count)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=PAGE_SIZE_MAX),
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ItemListOut:
    stmt = select(Item)
    count_stmt = select(func.count(Item.id))

    def _apply(condition):
        nonlocal stmt, count_stmt
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    if q:
        like = f"%{q}%"
        _apply(or_(Item.title.ilike(like), Item.summary.ilike(like)))
    if category:
        _apply(Item.category == category)
    if tag:
        _apply(Item.tags.any(Tag.name == tag))
    if is_selected is not None:
        _apply(Item.is_selected.is_(is_selected))
    if has_content is True:
        _apply(Item.content.is_not(None))
        _apply(Item.content != "")
    elif has_content is False:
        _apply(or_(Item.content.is_(None), Item.content == ""))
    if scored is True:
        _apply(Item.score.is_not(None))
    elif scored is False:
        _apply(Item.score.is_(None))
    if min_score is not None:
        _apply(Item.score >= min_score)
    if max_score is not None:
        _apply(Item.score <= max_score)
    if ingested_from == "openalex":
        stmt = stmt.join(Item.paper).where(PaperMeta.ingested_from == "openalex")
        count_stmt = count_stmt.join(Item.paper).where(PaperMeta.ingested_from == "openalex")
    elif ingested_from == "agent":
        _apply(or_(Item.paper.has(PaperMeta.ingested_from == "agent"), ~Item.paper.has()))

    order = {
        "score": Item.score.desc().nulls_last(),
        "view_count": Item.view_count.desc(),
        "created_at": Item.created_at.desc(),
    }[sort]
    total = (await session.execute(count_stmt)).scalar_one()
    rows = (
        await session.execute(
            stmt.order_by(order, Item.id.desc())
            .offset((page - 1) * page_size).limit(page_size)
        )
    ).scalars().all()
    return ItemListOut(
        total=total, page=page, page_size=page_size,
        items=[_to_item_out(it) for it in rows],
    )


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
    if not runtime_settings.get("content_fetch_enabled"):
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


@router.post("/items/{item_id}/rescore", response_model=ItemOut)
async def rescore_item(
    item_id: int,
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ItemOut:
    if not settings.deepseek_api_key:
        raise problem(503, "Service Unavailable", "未配置 DEEPSEEK_API_KEY，无法评分")
    item = await session.get(Item, item_id)
    if item is None:
        raise problem(404, "Not Found", "条目不存在")
    if await scoring_service.score_item(session, item) is None:
        raise problem(502, "Bad Gateway", "评分失败，请稍后重试")
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


@router.post("/items/batch-delete", response_model=BatchDeleteOut)
async def batch_delete_items(
    payload: BatchIdsIn,
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> BatchDeleteOut:
    deleted: list[int] = []
    missing: list[int] = []
    for item_id in payload.ids:
        if await ingest_service.delete_item(session, item_id):
            deleted.append(item_id)
        else:
            missing.append(item_id)
    await session.commit()
    return BatchDeleteOut(deleted=deleted, missing=missing)


@router.post("/items/batch-fetch-content", response_model=JobStatusOut, status_code=202)
async def batch_fetch_content(
    payload: BatchFetchIn,
    _: None = Depends(require_admin),
) -> JobStatusOut:
    if not job_runner.spawn("fetch_content", {
        "item_ids": payload.ids, "force": payload.force,
    }):
        raise problem(409, "Conflict", "批量抓取正在进行，请稍后再试")
    raw = await job_runner.get_job("fetch_content")
    return _job_out(raw or {"name": "fetch_content", "label": "批量抓取全文", "status": "running"})


# ---------- jobs ----------

@router.get("/jobs", response_model=JobListOut)
async def list_jobs(_: None = Depends(require_admin)) -> JobListOut:
    return JobListOut(jobs=[_job_out(j) for j in await job_runner.list_jobs()])


@router.post("/jobs/{name}/run", response_model=JobStatusOut, status_code=202)
async def run_job(
    name: str,
    payload: JobRunIn | None = None,
    _: None = Depends(require_admin),
) -> JobStatusOut:
    if name not in job_runner.JOB_LABELS:
        raise problem(404, "Not Found", "未知任务")
    params: dict = {}
    body = payload or JobRunIn()
    if name == "daily_generate" and body.date is not None:
        params["date"] = body.date.isoformat()
    if name == "fetch_content":
        params["item_ids"] = body.item_ids or []
        params["force"] = body.force
    try:
        started = job_runner.spawn(name, params)
    except KeyError:
        raise problem(404, "Not Found", "未知任务")
    if not started:
        raise problem(409, "Conflict", "该任务正在运行，请稍后再试")
    raw = await job_runner.get_job(name)
    return _job_out(raw or {"name": name, "label": job_runner.JOB_LABELS[name], "status": "running"})


# ---------- settings / watchlist ----------

@router.get("/settings", response_model=AdminSettingsOut)
async def get_settings(_: None = Depends(require_admin)) -> AdminSettingsOut:
    writable = {
        k: SettingValueOut(value=v["value"], source=v["source"])
        for k, v in runtime_settings.snapshot().items()
    }
    return AdminSettingsOut(
        writable=writable,
        readonly=AdminSettingsReadonly(**runtime_settings.readonly_snapshot()),
    )


@router.patch("/settings", response_model=AdminSettingsOut)
async def patch_settings(
    payload: AdminSettingsPatch,
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> AdminSettingsOut:
    updates = payload.model_dump(exclude_unset=True)
    try:
        snap = await runtime_settings.patch(session, updates)
        await session.commit()
    except ValueError as exc:
        raise problem(422, "Unprocessable Entity", str(exc))
    if runtime_settings.get("content_fetch_enabled"):
        job_runner.spawn("fetch_content", {})
    writable = {
        k: SettingValueOut(value=v["value"], source=v["source"])
        for k, v in snap.items()
    }
    return AdminSettingsOut(
        writable=writable,
        readonly=AdminSettingsReadonly(**runtime_settings.readonly_snapshot()),
    )


@router.get("/watchlist", response_model=WatchlistOut)
async def get_watchlist(_: None = Depends(require_admin)) -> WatchlistOut:
    return WatchlistOut(**watchlist_service.get_watchlist())


@router.put("/watchlist", response_model=WatchlistOut)
async def put_watchlist(
    payload: WatchlistOut,
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> WatchlistOut:
    try:
        saved = await watchlist_service.save(session, payload.model_dump())
        await session.commit()
    except ValueError as exc:
        raise problem(422, "Unprocessable Entity", str(exc))
    return WatchlistOut(**saved)


# ---------- api keys ----------

@router.get("/api-keys", response_model=list[ApiKeyOut])
async def list_api_keys(
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> list[ApiKeyOut]:
    rows = (
        await session.execute(select(ApiKey).order_by(ApiKey.id.desc()))
    ).scalars().all()
    return [
        ApiKeyOut(
            id=k.id, name=k.name, is_active=k.is_active,
            last_used_at=k.last_used_at, created_at=k.created_at,
        )
        for k in rows
    ]


@router.post("/api-keys", response_model=ApiKeyCreatedOut)
async def create_api_key(
    payload: ApiKeyCreateIn,
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ApiKeyCreatedOut:
    import secrets

    raw = f"agri_{secrets.token_urlsafe(32)}"
    key = ApiKey(key_hash=hash_api_key(raw), name=payload.name.strip())
    session.add(key)
    await session.commit()
    await session.refresh(key)
    return ApiKeyCreatedOut(
        id=key.id, name=key.name, is_active=key.is_active,
        last_used_at=key.last_used_at, created_at=key.created_at, key=raw,
    )


@router.patch("/api-keys/{key_id}", response_model=ApiKeyOut)
async def patch_api_key(
    key_id: int,
    payload: ApiKeyPatchIn,
    _: None = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> ApiKeyOut:
    key = await session.get(ApiKey, key_id)
    if key is None:
        raise problem(404, "Not Found", "API Key 不存在")
    key.is_active = payload.is_active
    await session.commit()
    await session.refresh(key)
    return ApiKeyOut(
        id=key.id, name=key.name, is_active=key.is_active,
        last_used_at=key.last_used_at, created_at=key.created_at,
    )


# ---------- legacy sync triggers (public-site shortcuts) ----------

@router.post("/literature/fetch", response_model=LiteratureFetchOut)
async def fetch_literature(
    _: None = Depends(require_admin),
) -> LiteratureFetchOut:
    """手动触发一轮 OpenAlex 拉取（与定时任务同一入口）。同步等待，供脚本兼容。"""
    if job_runner.is_running("literature_fetch"):
        raise problem(409, "Conflict", "文献拉取正在运行，请稍后再试")
    stats = await literature_scheduler.run_once()
    return LiteratureFetchOut(
        fetched=stats.get("fetched", 0),
        screened_out=stats.get("screened_out", 0),
        created=stats.get("created", 0),
        duplicate=stats.get("duplicate", 0),
        errors=stats.get("errors", 0),
        from_date=stats.get("from_date"),
        truncated=bool(stats.get("truncated")),
    )


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
