"""AgriHot backend entrypoint."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
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
        from .services import runtime_settings, watchlist_service

        await maybe_retag_existing(session)
        await maybe_backfill_doi(session)
        await runtime_settings.load(session)
        await watchlist_service.load_from_db(session)
        await session.commit()

    from .services.daily_scheduler import start_daily_scheduler
    from .services.literature_scheduler import start_literature_scheduler

    # Always start loops; each tick reads the effective enabled flag so the
    # admin console can toggle schedulers without a process restart.
    scheduler = start_daily_scheduler()
    literature = start_literature_scheduler()
    yield
    scheduler.cancel()
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


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok", "service": "agrihot"}
