"""ORM models: Item, Tag, Daily, ApiKey."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (JSON, BigInteger, Boolean, Column, Date, DateTime,
                        ForeignKey, Integer, String, Table, Text)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


item_tags = Table(
    "item_tags",
    Base.metadata,
    Column("item_id", ForeignKey("items.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Item(Base):
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(Text)
    url_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # signed 64-bit storage of the unsigned simhash value
    title_simhash: Mapped[int] = mapped_column(BigInteger)
    summary: Mapped[str] = mapped_column(Text)
    # 外文摘要的中文译文；原文始终在 summary。中文原文保持 NULL。
    summary_zh: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_name: Mapped[str] = mapped_column(String(200), default="")
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    category: Mapped[str] = mapped_column(String(50), default="报道", index=True)
    cover_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    hotness: Mapped[int] = mapped_column(Integer, default=0)
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # AI 精选评分：总分（0-100）与各维度明细；NULL = 未评分（旧数据或评分被关闭）
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    score_detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # merged multi-source reports: [{"name": ..., "url": ...}, ...]
    sources: Mapped[list] = mapped_column(JSON, default=list)
    # 阅读次数：详情页每打开一次 +1
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    # 规范化 DOI（小写、无 doi.org 前缀）；新闻条目多为 NULL
    doi: Mapped[str | None] = mapped_column(String(200), nullable=True, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )

    tags: Mapped[list["Tag"]] = relationship(
        secondary=item_tags, back_populates="items", lazy="selectin"
    )
    paper: Mapped["PaperMeta | None"] = relationship(
        back_populates="item", uselist=False,
        cascade="all, delete-orphan", lazy="selectin",
    )


class PaperMeta(Base):
    """1:1 论文扩展：OpenAlex / DOAJ / Agent 推送的学术条目。"""
    __tablename__ = "paper_meta"

    item_id: Mapped[int] = mapped_column(
        ForeignKey("items.id", ondelete="CASCADE"), primary_key=True
    )
    openalex_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )
    authors: Mapped[list] = mapped_column(JSON, default=list)
    venue: Mapped[str | None] = mapped_column(String(300), nullable=True)
    cited_by_count: Mapped[int] = mapped_column(Integer, default=0)
    oa_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # {tldr, method, finding, direction, opportunity}
    card: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    direction: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    ingested_from: Mapped[str] = mapped_column(String(20), default="agent")

    item: Mapped[Item] = relationship(back_populates="paper")


class PipelineState(Base):
    """Key/value 游标：文献拉取的上次覆盖日期等。"""
    __tablename__ = "pipeline_state"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)

    items: Mapped[list[Item]] = relationship(
        secondary=item_tags, back_populates="tags"
    )


class Daily(Base):
    __tablename__ = "dailies"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(300))
    highlights: Mapped[list] = mapped_column(JSON, default=list)  # 今日要点 [str]
    content: Mapped[str] = mapped_column(Text, default="")  # markdown body
    item_ids: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ApiKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


def hash_api_key(raw: str) -> str:
    import hashlib

    return hashlib.sha256(raw.strip().encode()).hexdigest()
