"""Async SQLAlchemy engine + session factory."""
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import settings

_engine_kwargs = {"echo": False, "pool_pre_ping": True}
if settings.database_url.startswith("postgresql"):
    # SQLite's default pool rejects these arguments. PostgreSQL needs a short
    # wait so a busy pool becomes a 503 before the edge times out.
    _engine_kwargs.update(
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
    )
engine = create_async_engine(settings.database_url, **_engine_kwargs)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
# Article reads stay available while list and taxonomy queries fill the main pool.
_detail_kwargs = dict(_engine_kwargs)
if settings.database_url.startswith("postgresql"):
    _detail_kwargs.update(pool_size=2, max_overflow=2)
detail_engine = create_async_engine(settings.database_url, **_detail_kwargs)
DetailSession = async_sessionmaker(detail_engine, class_=AsyncSession, expire_on_commit=False)

# create_all will not ADD columns to an existing table
_ITEM_COLUMN_PATCHES = (
    ("score", "INTEGER"),
    ("score_detail", "JSON"),
    ("view_count", "INTEGER NOT NULL DEFAULT 0"),
    ("doi", "VARCHAR(200)"),
    ("summary_zh", "TEXT"),
    ("search_phrases", "JSON"),
)


async def ensure_schema(target_engine=None) -> None:
    """Create missing tables and patch new columns onto existing `items`."""
    from .models import Base

    async with (target_engine or engine).begin() as conn:
        if conn.dialect.name == "postgresql":
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)

        def _item_columns(c):
            insp = inspect(c)
            if not insp.has_table("items"):
                return set()
            return {col["name"] for col in insp.get_columns("items")}

        existing = await conn.run_sync(_item_columns)
        for col, ddl in _ITEM_COLUMN_PATCHES:
            if col not in existing:
                await conn.execute(text(f"ALTER TABLE items ADD COLUMN {col} {ddl}"))
        await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_items_doi ON items (doi)"))
        key_columns = await conn.run_sync(lambda c: {col["name"] for col in inspect(c).get_columns("api_keys")})
        if "purpose" not in key_columns:
            await conn.execute(text("ALTER TABLE api_keys ADD COLUMN purpose VARCHAR(20) NOT NULL DEFAULT 'push'"))
        tag_columns = await conn.run_sync(lambda c: {col["name"] for col in inspect(c).get_columns("tags")})
        for col, default in (("kind", "keyword"), ("status", "candidate")):
            if col not in tag_columns:
                await conn.execute(text(f"ALTER TABLE tags ADD COLUMN {col} VARCHAR(20) NOT NULL DEFAULT '{default}'"))
        if conn.dialect.name == "postgresql":
            await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_search_chunks_fts ON search_chunks USING gin (to_tsvector('simple', lexemes))"))


async def get_session() -> AsyncSession:  # FastAPI dependency
    async with SessionLocal() as session:
        yield session


async def get_detail_session() -> AsyncSession:
    # Tests replace get_session with their database. Follow that replacement
    # so a detail read cannot land on the process-wide empty default.
    from .main import app
    override = app.dependency_overrides.get(get_session)
    if override is not None:
        async for session in override():
            yield session
            return
    async with DetailSession() as session:
        yield session
