"""AgriHot backend entrypoint."""
import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from .api.v1.admin import router as admin_router
from .api.v1.ingest import limiter, router as ingest_router
from .api.v1.public import router as public_router
from .api.v1.seo import router as seo_router
from .api.v1.agent import router as agent_router
from .api.v1.agent_admin import router as agent_admin_router
from .mcp_server import mcp, mcp_app
from .config import settings
from .database import SessionLocal, ensure_schema


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_schema()
    # one-shot: split concatenated tag blobs left by earlier agents
    async with SessionLocal() as session:
        from .services.ingest_service import maybe_backfill_doi, maybe_retag_existing
        from .services import runtime_settings, watchlist_service

        await maybe_retag_existing(session)
        await maybe_backfill_doi(session)
        await runtime_settings.load(session)
        await watchlist_service.load_from_db(session)
        from .services.taxonomy_service import sync_catalog
        await sync_catalog(session)
        await session.commit()

    from .services.content_scheduler import start_content_scheduler
    from .services.daily_scheduler import start_daily_scheduler
    from .services.literature_scheduler import start_literature_scheduler

    # Always start loops; each tick reads the effective enabled flag so the
    # admin console can toggle schedulers without a process restart.
    scheduler = start_daily_scheduler()
    literature = start_literature_scheduler()
    content = start_content_scheduler()
    from .services.search_index_service import run_worker
    indexer = asyncio.create_task(run_worker())
    try:
        async with mcp.session_manager.run():
            yield
    finally:
        for task in (scheduler, literature, content, indexer):
            task.cancel()
        for task in (scheduler, literature, content, indexer):
            with suppress(asyncio.CancelledError):
                await task


app = FastAPI(
    title="AgriHot API",
    description="农业信息化资讯 · Agent Skill 与 MCP 读取接入",
    version="2.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter

app.add_middleware(GZipMiddleware, minimum_size=1000, compresslevel=5)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _problem(status: int, title: str, detail) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"title": title, "status": status, "detail": detail},
        media_type="application/problem+json",
    )


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return _problem(429, "Too Many Requests", "请求过于频繁，请稍后重试")


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return _problem(
        422,
        "Unprocessable Entity",
        jsonable_encoder(exc.errors(), custom_encoder={Exception: str}),
    )


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    from fastapi import HTTPException

    if isinstance(exc, HTTPException) and isinstance(exc.detail, dict):
        return _problem(exc.status_code, exc.detail.get("title", "Error"), exc.detail.get("detail", ""))
    return _problem(500, "Internal Server Error", exc.__class__.__name__)


app.include_router(ingest_router)
app.include_router(admin_router)
app.include_router(public_router)
app.include_router(seo_router)
app.include_router(agent_router)
app.include_router(agent_admin_router)
app.add_route("/api/v1/mcp", mcp_app, methods=["GET", "POST", "DELETE"])


@app.middleware("http")
async def private_cache_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(("/api/v1/agent/", "/api/v1/mcp", "/api/v1/admin/")):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "service": "agrihot"}
