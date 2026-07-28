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
from .database import engine
from .models import Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # create_all won't add columns to existing tables; patch them in place
        # (works on both SQLite and Postgres by checking first)
        from sqlalchemy import inspect, text

        existing = await conn.run_sync(
            lambda c: {col["name"] for col in inspect(c).get_columns("items")}
        )
        for col, ddl in (("score", "INTEGER"), ("score_detail", "JSON")):
            if col not in existing:
                await conn.execute(text(f"ALTER TABLE items ADD COLUMN {col} {ddl}"))
    yield


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
