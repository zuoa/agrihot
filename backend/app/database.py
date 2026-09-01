"""Async SQLAlchemy engine + session factory."""
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import settings

engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# create_all will not ADD columns to an existing table
_ITEM_COLUMN_PATCHES = (
    ("score", "INTEGER"),
    ("score_detail", "JSON"),
    ("view_count", "INTEGER NOT NULL DEFAULT 0"),
    ("doi", "VARCHAR(200)"),
)


async def ensure_schema() -> None:
    """Create missing tables and patch new columns onto existing `items`."""
    from .models import Base

    async with engine.begin() as conn:
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


async def get_session() -> AsyncSession:  # FastAPI dependency
    async with SessionLocal() as session:
        yield session
