from __future__ import annotations

from datetime import date, time
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    TypeAdapter,
    model_validator,
)

CANDIDATE_SCHEMA_VERSION = "event-candidate-v1"
SCREENING_SCHEMA_VERSION = "telegram-screening-v1"
EXTRACTION_SCHEMA_VERSION = "telegram-extraction-v1"

_HTTP_URL_ADAPTER = TypeAdapter(HttpUrl)


def _validate_http_url(value: str) -> str:
    _HTTP_URL_ADAPTER.validate_python(value)
    return value


HttpUrlString = Annotated[str, AfterValidator(_validate_http_url)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TimePrecision(StrEnum):
    EXACT = "EXACT"
    APPROXIMATE = "APPROXIMATE"
    DATE_ONLY = "DATE_ONLY"
    UNKNOWN = "UNKNOWN"


class OccurrenceStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    POSTPONED = "POSTPONED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"


class RegistrationScope(StrEnum):
    SERIES = "SERIES"
    EVENT = "EVENT"
    OCCURRENCE = "OCCURRENCE"


class ScreeningLabel(StrEnum):
    EVENT = "EVENT"
    UNCERTAIN = "UNCERTAIN"
    NOT_EVENT = "NOT_EVENT"


class ScreeningItem(StrictModel):
    message_identity: str = Field(min_length=1)
    decision: ScreeningLabel
    reason: str = Field(max_length=500)
    confidence: float = Field(ge=0, le=1)


class ScreeningBatch(StrictModel):
    results: list[ScreeningItem]


class CandidateOccurrence(StrictModel):
    label: str | None = None
    start_date: date
    start_time: time | None = None
    end_date: date | None = None
    end_time: time | None = None
    time_precision: TimePrecision
    is_all_day: bool = False
    raw_location: str | None = None
    status: OccurrenceStatus = OccurrenceStatus.SCHEDULED

    @model_validator(mode="after")
    def validate_time_shape(self) -> CandidateOccurrence:
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("end_date must not precede start_date")
        if self.end_time is not None and self.end_date is None:
            raise ValueError("end_time requires end_date")
        if self.end_time is not None and self.start_time is None:
            raise ValueError("end_time requires start_time")
        if (
            self.end_date == self.start_date
            and self.start_time is not None
            and self.end_time is not None
            and self.end_time < self.start_time
        ):
            raise ValueError("same-day end_time must not precede start_time")
        if self.is_all_day and (self.start_time is not None or self.end_time is not None):
            raise ValueError("all-day occurrences cannot contain times")
        if self.time_precision == TimePrecision.EXACT and self.start_time is None:
            raise ValueError("exact occurrences require start_time")
        if self.time_precision == TimePrecision.DATE_ONLY and self.start_time is not None:
            raise ValueError("date-only occurrences cannot contain times")
        return self


class CandidateOrganizer(StrictModel):
    name: str = Field(min_length=1)
    role: str | None = None
    is_primary: bool = False


class CandidateRegistration(StrictModel):
    scope: RegistrationScope
    name: str = Field(min_length=1)
    url: HttpUrlString | None = None
    opens_date: date | None = None
    opens_time: time | None = None
    closes_date: date | None = None
    closes_time: time | None = None
    instructions: str | None = None


class CandidateEvidence(StrictModel):
    field: str
    source_path: str
    value: str


class EventCandidatePayload(StrictModel):
    schema_version: Literal["event-candidate-v1"] = CANDIDATE_SCHEMA_VERSION
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    occurrences: list[CandidateOccurrence] = Field(min_length=1)
    organizers: list[CandidateOrganizer] = Field(default_factory=list)
    registrations: list[CandidateRegistration] = Field(default_factory=list)
    format_codes: list[str] = Field(default_factory=list)
    topic_codes: list[str] = Field(default_factory=list)
    purpose_codes: list[str] = Field(default_factory=list)
    audience_codes: list[str] = Field(default_factory=list)
    image_url: HttpUrlString | None = None
    source_url: HttpUrlString
    evidence: list[CandidateEvidence] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    overall_confidence: float | None = Field(default=None, ge=0, le=1)


class ExtractedMessage(StrictModel):
    message_identity: str = Field(min_length=1)
    events: list[EventCandidatePayload] = Field(default_factory=list)


class ExtractionBatch(StrictModel):
    results: list[ExtractedMessage]
