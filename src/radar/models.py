"""Pydantic data models shared across the pipeline."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl


class Item(BaseModel):
    """A single normalised, source-agnostic item (a GitHub release, a tender, ...)."""

    source: Literal["github_releases", "contracts_finder"]
    target: str
    item_id: str
    title: str
    url: HttpUrl
    published_at: datetime
    author: str | None = None
    fields: dict[str, str] = Field(default_factory=dict)
    body_excerpt: str = ""

    @property
    def key(self) -> str:
        """Stable identity used for de-duplication: source + ':' + item_id."""
        return f"{self.source}:{self.item_id}"


class FetchResult(BaseModel):
    """Outcome of one source fetch for one target."""

    target: str
    status: Literal["ok", "not_modified", "error", "rate_limited"]
    http_status: int | None = None
    items: list[Item] = Field(default_factory=list)
    etag: str | None = None
    rate_remaining: int | None = None
    duration_ms: int = 0
    error: str | None = None


class FilterDecision(BaseModel):
    """LLM filter verdict for one item."""

    item_key: str
    keep: bool
    reason: str = ""
    summary: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


class AlertRecord(BaseModel):
    """A successfully posted alert."""

    item_key: str
    channel: str
    published_at: datetime
    detected_at: datetime
    alerted_at: datetime
    latency_s: float
    http_status: int | None = None


class CheckResult(BaseModel):
    """One check (per target per cycle) recorded in the `checks` table."""

    cycle_id: str
    target: str
    started_at: datetime
    duration_ms: int
    status: str
    http_status: int | None = None
    new_items: int = 0
    rate_remaining: int | None = None
    error: str | None = None


def jsonable(obj: Any) -> Any:
    """Best-effort conversion for JSON logs."""
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj
