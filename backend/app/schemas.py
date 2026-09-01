"""Pydantic request/response schemas."""
from __future__ import annotations

from datetime import date as date_type
from datetime import datetime

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
    doi: str | None = Field(default=None, max_length=200)

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


class AdminMeOut(BaseModel):
    ok: bool = True


class SettingValueOut(BaseModel):
    value: bool | int | str
    source: str  # env | override


class AdminSettingsReadonly(BaseModel):
    deepseek_configured: bool
    jina_configured: bool
    openalex_configured: bool
    deepseek_model: str
    openalex_mailto: str
    daily_timezone: str
    ingest_rate_limit: str


class AdminSettingsOut(BaseModel):
    writable: dict[str, SettingValueOut]
    readonly: AdminSettingsReadonly


class AdminSettingsPatch(BaseModel):
    model_config = {"extra": "forbid"}
    selection_threshold: int | None = Field(default=None, ge=0, le=100)
    daily_top_n: int | None = Field(default=None, ge=1, le=50)
    daily_generate_enabled: bool | None = None
    daily_generate_time: str | None = None
    literature_fetch_enabled: bool | None = None
    literature_fetch_time: str | None = None
    literature_lookback_days: int | None = Field(default=None, ge=0, le=30)
    literature_bootstrap_days: int | None = Field(default=None, ge=1, le=90)
    literature_max_new_per_run: int | None = Field(default=None, ge=1, le=500)
    content_fetch_enabled: bool | None = None

    @field_validator("daily_generate_time", "literature_fetch_time")
    @classmethod
    def hhmm(cls, v: str | None) -> str | None:
        if v is None:
            return v
        parts = v.split(":")
        if len(parts) not in (2, 3):
            raise ValueError("应为 HH:MM")
        try:
            hour, minute = int(parts[0]), int(parts[1])
        except ValueError as exc:
            raise ValueError("应为 HH:MM") from exc
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError("应为 HH:MM")
        return f"{hour:02d}:{minute:02d}"


class JobStatusOut(BaseModel):
    name: str
    label: str
    status: str  # idle | running | ok | error
    started_at: datetime | None = None
    finished_at: datetime | None = None
    stats: dict | None = None
    error: str | None = None
    progress: dict | None = None


class JobListOut(BaseModel):
    jobs: list[JobStatusOut]


class JobRunIn(BaseModel):
    date: date_type | None = None
    item_ids: list[int] | None = Field(default=None, max_length=20)
    force: bool = False


class BatchIdsIn(BaseModel):
    ids: list[int] = Field(..., min_length=1, max_length=50)


class BatchFetchIn(BaseModel):
    ids: list[int] = Field(..., min_length=1, max_length=20)
    force: bool = False


class BatchDeleteOut(BaseModel):
    deleted: list[int]
    missing: list[int]


class SchedulerInfoOut(BaseModel):
    enabled: bool
    time: str
    timezone: str
    next_run_at: datetime


class OverviewOut(BaseModel):
    items: int
    selected: int
    dailies: int
    tags: int
    missing_content: int
    unscored: int
    schedulers: dict[str, SchedulerInfoOut]
    jobs: list[JobStatusOut]


class WatchlistDirection(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    queries: list[str] = Field(default_factory=list)


class WatchlistJournal(BaseModel):
    name: str = ""
    issn: str = Field(..., min_length=1, max_length=32)


class WatchlistAuthor(BaseModel):
    name: str = ""
    openalex_id: str = ""


class WatchlistOut(BaseModel):
    directions: list[WatchlistDirection] = []
    journals: list[WatchlistJournal] = []
    authors: list[WatchlistAuthor] = []
    prescreen: list[str] = []


class ApiKeyOut(BaseModel):
    id: int
    name: str
    is_active: bool
    last_used_at: datetime | None
    created_at: datetime


class ApiKeyCreateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class ApiKeyCreatedOut(ApiKeyOut):
    key: str


class ApiKeyPatchIn(BaseModel):
    is_active: bool


class AdminItemUpdate(BaseModel):
    """Partial update; only provided fields are applied."""
    title: str | None = Field(default=None, min_length=4, max_length=500)
    url: str | None = Field(default=None, max_length=2000)
    summary: str | None = Field(default=None, min_length=10)
    summary_zh: str | None = None
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

    @field_validator("summary_zh")
    @classmethod
    def blank_summary_zh(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        return v or None


# ---------- public read ----------

class TagOut(BaseModel):
    name: str
    count: int = 0


class SourceOut(BaseModel):
    name: str = ""
    url: str | None = None


class PaperAuthorOut(BaseModel):
    name: str
    orcid: str | None = None


class PaperCardOut(BaseModel):
    tldr: str = ""
    method: str = ""
    finding: str = ""
    direction: str = ""
    opportunity: str = ""


class PaperMetaOut(BaseModel):
    doi: str | None = None
    openalex_id: str | None = None
    authors: list[PaperAuthorOut] = []
    venue: str | None = None
    cited_by_count: int = 0
    oa_url: str | None = None
    card: PaperCardOut | None = None
    direction: str | None = None
    ingested_from: str = "agent"


class ItemOut(BaseModel):
    id: int
    title: str
    url: str
    summary: str
    summary_zh: str | None = None
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
    doi: str | None = None
    paper: PaperMetaOut | None = None
    created_at: datetime


class ViewOut(BaseModel):
    view_count: int


class ItemListOut(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[ItemOut]


class DailyOut(BaseModel):
    date: date_type
    title: str
    highlights: list[str]
    content: str
    items: list[ItemOut] = []


class DailyListItem(BaseModel):
    date: date_type
    title: str
    highlight_count: int
    item_count: int


class DailyListOut(BaseModel):
    total: int
    dailies: list[DailyListItem]


class DailyGenerateOut(BaseModel):
    date: date_type
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


class DirectionOut(BaseModel):
    name: str
    count: int = 0


class LiteratureFetchOut(BaseModel):
    fetched: int = 0
    screened_out: int = 0
    created: int = 0
    duplicate: int = 0
    errors: int = 0
    from_date: str | None = None
    truncated: bool = False
