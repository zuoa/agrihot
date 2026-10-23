"""ORM models: Item, Tag, Daily, ApiKey."""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (JSON, BigInteger, Boolean, Column, Date, DateTime,
                        ForeignKey, Index, Integer, String, Table, Text, text)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector


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
    # 阅读次数：详情页可见停留后由 POST /items/{id}/view 自增
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    # 规范化 DOI（小写、无 doi.org 前缀）；新闻条目多为 NULL
    doi: Mapped[str | None] = mapped_column(String(200), nullable=True, unique=True, index=True)
    # LLM 给出的检索短语（空格分词长尾）；不入库为 Tag。NULL = 未评分，读时按标签推导
    search_phrases: Mapped[list | None] = mapped_column(JSON, nullable=True)
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
    topic_links: Mapped[list["ItemTopic"]] = relationship(
        back_populates="item", cascade="all, delete-orphan", lazy="selectin",
    )
    classification: Mapped["ItemClassification | None"] = relationship(
        back_populates="item", cascade="all, delete-orphan", uselist=False, lazy="selectin",
    )
    search_job: Mapped["SearchJob | None"] = relationship(
        uselist=False, lazy="selectin", cascade="all, delete-orphan",
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
    kind: Mapped[str] = mapped_column(String(20), default="keyword", server_default="keyword")
    status: Mapped[str] = mapped_column(String(20), default="candidate", server_default="candidate")

    items: Mapped[list[Item]] = relationship(
        secondary=item_tags, back_populates="tags"
    )


class Topic(Base):
    __tablename__ = "topics"

    code: Mapped[str] = mapped_column(String(12), primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    parent_code: Mapped[str | None] = mapped_column(ForeignKey("topics.code"), index=True)
    sort_order: Mapped[int] = mapped_column(default=0)
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")


class ItemTopic(Base):
    __tablename__ = "item_topics"
    __table_args__ = (
        Index("uq_item_topics_primary", "item_id", unique=True,
              postgresql_where=text("is_primary"), sqlite_where=text("is_primary = 1")),
        Index("ix_item_topics_topic", "topic_code", "item_id"),
    )

    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), primary_key=True)
    topic_code: Mapped[str] = mapped_column(ForeignKey("topics.code"), primary_key=True)
    is_primary: Mapped[bool] = mapped_column(default=False)
    topic: Mapped[Topic] = relationship(lazy="joined")
    item: Mapped[Item] = relationship(back_populates="topic_links")


class ItemClassification(Base):
    __tablename__ = "item_classifications"

    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), primary_key=True)
    status: Mapped[str] = mapped_column(String(24), default="unclassified", index=True)
    locked: Mapped[bool] = mapped_column(default=False)
    version: Mapped[str] = mapped_column(String(80), default="")
    input_hash: Mapped[str] = mapped_column(String(64), default="")
    method: Mapped[str] = mapped_column(String(20), default="rules")
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    batch_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    item: Mapped[Item] = relationship(back_populates="classification")


class ClassificationChange(Base):
    """Audit log and conditional rollback; never overwrites a later edit."""
    __tablename__ = "classification_changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(64), index=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    before: Mapped[dict] = mapped_column(JSON)
    after: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TagAlias(Base):
    __tablename__ = "tag_aliases"

    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), index=True)
    tag: Mapped[Tag] = relationship(lazy="joined")


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
    purpose: Mapped[str] = mapped_column(String(20), default="push", server_default="push")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentApplication(Base):
    __tablename__ = "agent_applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    contact: Mapped[str] = mapped_column(String(200))
    use_case: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    note: Mapped[str] = mapped_column(String(500), default="")
    api_key_id: Mapped[int | None] = mapped_column(ForeignKey("api_keys.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SearchJob(Base):
    """Durable per-item indexing queue; revision prevents stale API responses winning."""
    __tablename__ = "search_jobs"

    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), primary_key=True)
    revision: Mapped[int] = mapped_column(default=1)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), default="")
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    attempts: Mapped[int] = mapped_column(default=0)
    error: Mapped[str | None] = mapped_column(String(200), nullable=True)
    retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SearchChunk(Base):
    __tablename__ = "search_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(default=0)
    text: Mapped[str] = mapped_column(Text)
    lexemes: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    # No fixed typmod: model/dimension changes create a new fingerprint.
    embedding: Mapped[list | None] = mapped_column(Vector().with_variant(JSON(none_as_null=True), "sqlite"), nullable=True)


def hash_api_key(raw: str) -> str:
    import hashlib

    return hashlib.sha256(raw.strip().encode()).hexdigest()


# All ORM writers (including CLI maintenance) must invalidate retrieval indexes.
from .services.search_queue import register_queue_hooks

register_queue_hooks()

from .services.taxonomy_hooks import register_taxonomy_hooks

register_taxonomy_hooks()
