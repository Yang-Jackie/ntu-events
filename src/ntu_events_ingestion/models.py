from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TextEntity(StrictModel):
    kind: str
    offset: int
    length: int
    text: str | None = None
    url: str | None = None


class RawTelegramMessage(StrictModel):
    channel_id: int
    channel_username: str | None
    channel_title: str
    message_id: int
    message_url: str | None
    published_at: datetime
    edited_at: datetime | None = None
    text: str
    text_entities: list[TextEntity] = Field(default_factory=list)
    external_urls: list[str] = Field(default_factory=list)
    reply_to_message_id: int | None = None
    forwarded_from: str | None = None
    views: int | None = None
    content_hash: str
    retrieved_at: datetime
    retrieval_version: str

    @property
    def identity(self) -> str:
        return f"{self.channel_id}:{self.message_id}"


class EventOccurrence(StrictModel):
    date: str | None = None
    start_time: str | None = None
    end_date: str | None = None
    end_time: str | None = None
    timezone: str = "Asia/Singapore"
    all_day: bool = False
    precision: Literal["exact", "date_only", "approximate", "unknown"] = "unknown"
    raw_time_text: str | None = None


class ExtractedEvent(StrictModel):
    title: str
    description: str | None = None
    occurrences: list[EventOccurrence] = Field(default_factory=list)
    raw_location: str | None = None
    organizers: list[str] = Field(default_factory=list)
    registration_urls: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    status: Literal["scheduled", "cancelled", "postponed", "unknown"] = "unknown"
    evidence: list[str] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class MessageExtraction(StrictModel):
    is_event_related: bool
    events: list[ExtractedEvent] = Field(default_factory=list)
    rejection_reason: str | None = None

    @model_validator(mode="after")
    def event_flag_matches_events(self) -> MessageExtraction:
        if self.is_event_related and not self.events:
            raise ValueError("event-related output must contain at least one event")
        if not self.is_event_related and self.events:
            raise ValueError("non-event output cannot contain events")
        return self


class ExtractionRecord(StrictModel):
    source_message_identity: str
    source_content_hash: str
    model: str
    prompt_version: str
    schema_version: str
    processed_at: datetime
    result: MessageExtraction
    response_id: str | None = None
    usage: dict[str, Any] | None = None
    cache_key: str


class FailureRecord(StrictModel):
    source_message_identity: str
    stage: Literal["fetch", "extract", "validate", "write"]
    error_type: str
    error_message: str
    occurred_at: datetime
