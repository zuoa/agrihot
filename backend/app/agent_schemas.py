"""Agent-facing contracts, shared by REST and MCP."""
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ApplicationIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    contact: str = Field(min_length=3, max_length=200)
    use_case: str = Field(min_length=10, max_length=2000)

    @field_validator("name", "contact", "use_case", mode="before")
    @classmethod
    def strip(cls, v):
        return v.strip() if isinstance(v, str) else v


class ApplicationReviewIn(BaseModel):
    decision: Literal["approve", "reject"]
    note: str = Field(default="", max_length=500)


class ContentFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Literal["政策", "报道", "论文", "行业"] | None = None
    tags: list[str] = Field(default_factory=list, max_length=20)
    direction: str | None = Field(default=None, max_length=80)
    topic: str | None = Field(default=None, max_length=80)
    technologies: list[str] = Field(default_factory=list, max_length=20)
    since: datetime | None = None
    until: datetime | None = None
    limit: int = Field(default=10, ge=1, le=50)

    @field_validator("since", "until")
    @classmethod
    def utc(cls, value):
        return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value

    @model_validator(mode="after")
    def date_order(self):
        if self.since and self.until and self.since > self.until:
            raise ValueError("since 不能晚于 until")
        return self


class SearchIn(ContentFilters):
    q: str = Field(min_length=1, max_length=500)

    @field_validator("q", mode="before")
    @classmethod
    def strip_query(cls, value):
        return value.strip() if isinstance(value, str) else value


class ItemListIn(ContentFilters):
    mode: Literal["all", "selected"] = "all"
    before_id: int | None = Field(default=None, ge=1)
