"""AgriHot backend entrypoint."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from .api.v1.admin import router as admin_router
from .api.v1.ingest import limiter, router as ingest_router
from .api.v1.public import router as public_router
from .config import settings
from .database import SessionLocal, ensure_schema


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_schema()
    # one-shot: split concatenated tag blobs left by earlier agents
    async with SessionLocal() as session:
        from .services.ingest_service import maybe_backfill_doi, maybe_retag_existing

        await maybe_retag_existing(session)
        await maybe_backfill_doi(session)
        await session.commit()
    scheduler = None
    literature = None
    if settings.daily_generate_enabled:
        from .services.daily_scheduler import start_daily_scheduler

        scheduler = start_daily_scheduler()
    if settings.literature_fetch_enabled:
        from .services.literature_scheduler import start_literature_scheduler

        literature = start_literature_scheduler()
    yield
    if scheduler is not None:
        scheduler.cancel()
    if literature is not None:
        literature.cancel()


app = FastAPI(
    title="AgriHot API",
    description="农业信息化资讯聚合 · Agent 推送与公开只读接口",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter

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
    return _problem(429, "Too Many Requests", f"超出推送频率限制（{settings.ingest_rate_limit}），请稍后重试")


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    return _problem(422, "Unprocessable Entity", exc.errors())


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    from fastapi import HTTPException

    if isinstance(exc, HTTPException) and isinstance(exc.detail, dict):
        return _problem(exc.status_code, exc.detail.get("title", "Error"), exc.detail.get("detail", ""))
    return _problem(500, "Internal Server Error", exc.__class__.__name__)


app.include_router(ingest_router)
app.include_router(admin_router)
app.include_router(public_router)


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "service": "agrihot"}
