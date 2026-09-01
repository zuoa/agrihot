"""Pydantic request/response schemas."""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, HttpUrl, field_validator


def _coerce_tag_list(v):
    """Accept a single string (LLM agents often send one blob) as a 1-item list.

    Splitting / filtering happens later in ingest_service.normalize_tags.
    Missing field is untouched; explicit null becomes an empty list.
    """
    if v is None or v == "":
        return []
    if isinstance(v, str):
        return [v]
    return v


# ---------- ingest (agent push) ----------

class IngestItemIn(BaseModel):
    title: str = Field(..., min_length=4, max_length=500)
    url: str = Field(..., max_length=2000)
    summary: str = Field(..., min_length=10)
    source_name: str = Field(default="", max_length=200)
    source_url: str | None = None
    published_at: datetime | None = None
    category: str | None = Field(default=None, max_length=50)
    tags: list[str] = Field(default_factory=list, max_length=20)
    cover_url: str | None = None
    content: str | None = None
    lang: str | None = Field(default=None, max_length=10)

    @field_validator("tags", mode="before")
    @classmethod
    def coerce_tags(cls, v):
        return _coerce_tag_list(v)


class IngestBatchIn(BaseModel):
    items: list[IngestItemIn] = Field(..., min_length=1, max_length=50)


class IngestResultOut(BaseModel):
    status: str  # created | duplicate | invalid
    item_id: int | None = None
    duplicate_of: int | None = None
    dup_reason: str | None = None  # exact_url | similar_title
    message: str = ""


# ---------- admin console ----------

class AdminLoginIn(BaseModel):
    password: str = Field(..., min_length=1, max_length=200)


class AdminLoginOut(BaseModel):
    token: str


class AdminItemUpdate(BaseModel):
    """Partial update; only provided fields are applied."""
    title: str | None = Field(default=None, min_length=4, max_length=500)
    url: str | None = Field(default=None, max_length=2000)
    summary: str | None = Field(default=None, min_length=10)
    content: str | None = None
    source_name: str | None = Field(default=None, max_length=200)
    source_url: str | None = None
    published_at: datetime | None = None
    category: str | None = Field(default=None, max_length=50)
    tags: list[str] | None = Field(default=None, max_length=20)
    cover_url: str | None = None
    hotness: int | None = Field(default=None, ge=0)
    is_selected: bool | None = None

    @field_validator("tags", mode="before")
    @classmethod
    def coerce_tags(cls, v):
        if v is None:
            return None
        return _coerce_tag_list(v)


# ---------- public read ----------

class TagOut(BaseModel):
    name: str
    count: int = 0


class SourceOut(BaseModel):
    name: str = ""
    url: str | None = None


class ItemOut(BaseModel):
    id: int
    title: str
    url: str
    summary: str
    content: str | None
    source_name: str
    source_url: str | None
    published_at: datetime | None
    category: str
    cover_url: str | None
    hotness: int
    is_selected: bool
    score: int | None = None
    score_detail: dict | None = None
    sources: list[SourceOut]
    tags: list[str]
    view_count: int = 0
    created_at: datetime


class ItemListOut(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[ItemOut]


class DailyOut(BaseModel):
    date: date
    title: str
    highlights: list[str]
    content: str
    items: list[ItemOut] = []


class DailyListItem(BaseModel):
    date: date
    title: str
    highlight_count: int
    item_count: int


class DailyListOut(BaseModel):
    total: int
    dailies: list[DailyListItem]


class DailyGenerateOut(BaseModel):
    date: date
    title: str
    highlight_count: int
    item_count: int


class StatsOut(BaseModel):
    """Site-wide aggregation counts for the About page."""
    items: int
    by_category: dict[str, int]
    selected: int
    dailies: int
    tags: int
    sources: int
    views: int
    since: datetime | None
