"""Validated generation documents; every factual block carries source excerpts."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Citation(BaseModel):
    source_id: str = Field(min_length=1, max_length=50)
    quote: str = Field(min_length=8, max_length=1200)


class Claim(BaseModel):
    text: str = Field(min_length=5, max_length=2000)
    kind: Literal["finding", "shared", "difference", "question", "inference"] = "finding"
    citations: list[Citation] = Field(min_length=1, max_length=8)


class Extension(BaseModel):
    kind: Literal["entity", "method", "question"]
    title: str = Field(min_length=2, max_length=100)
    body: Claim


class TimelineEntry(BaseModel):
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    claim: Claim


class Comparison(BaseModel):
    item_id: int
    object: str = Field(max_length=250)
    method: str = Field(max_length=400)
    data: str = Field(max_length=400)
    result: str = Field(max_length=600)
    limitation: str = Field(max_length=400)
    citations: list[Citation] = Field(min_length=1, max_length=8)


class SpecialDocument(BaseModel):
    overview: Claim
    findings: list[Claim] = Field(min_length=3, max_length=5)
    timeline: list[TimelineEntry] = Field(default_factory=list, max_length=15)
    comparisons: list[Comparison] = Field(default_factory=list, max_length=8)
    extensions: list[Extension] = Field(default_factory=list, max_length=4)


class CandidateItem(BaseModel):
    item_id: int
    role: Literal["core", "background"] = "core"
    reason: str = Field(min_length=5, max_length=400)
    # All reports about one paper/result share this key, irrespective of outlet.
    evidence_group: str = Field(min_length=1, max_length=100)


class Candidate(BaseModel):
    existing_id: int | None = None
    kind: Literal["event", "research"]
    title: str = Field(min_length=5, max_length=200)
    scope: str = Field(min_length=10, max_length=1000)
    items: list[CandidateItem] = Field(min_length=3, max_length=40)
    queries: list[str] = Field(default_factory=list, max_length=3)

    @field_validator("items")
    @classmethod
    def unique_items(cls, items):
        if len({item.item_id for item in items}) != len(items):
            raise ValueError("关联文章 ID 不能重复")
        return items


class Discovery(BaseModel):
    candidates: list[Candidate] = Field(default_factory=list, max_length=30)


class SpecialPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=5, max_length=200)
    scope: str | None = Field(default=None, min_length=10, max_length=1000)
    status: Literal["published", "archived", "withdrawn"] | None = None
    pinned: bool | None = None
    locked_fields: list[Literal["title", "scope", "items", "document"]] | None = None
    items: list[CandidateItem] | None = Field(default=None, min_length=3, max_length=40)
    document: SpecialDocument | None = None

    @field_validator("items")
    @classmethod
    def unique_items(cls, items):
        return Candidate.unique_items(items) if items is not None else items


class MergeIn(BaseModel):
    target_id: int = Field(gt=0)
