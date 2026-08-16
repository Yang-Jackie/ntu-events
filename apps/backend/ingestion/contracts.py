from __future__ import annotations

from datetime import date, time
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CANDIDATE_SCHEMA_VERSION = "event-candidate-v2"
SCREENING_SCHEMA_VERSION = "telegram-screening-v2"
EXTRACTION_SCHEMA_VERSION = "telegram-extraction-v2"


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


class AttendanceMode(StrEnum):
    IN_PERSON = "IN_PERSON"
    ONLINE = "ONLINE"
    HYBRID = "HYBRID"
    UNKNOWN = "UNKNOWN"


class RegistrationScope(StrEnum):
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
    local_ref: str = Field(min_length=1, max_length=100)
    label: str | None = None
    start_date: date | None = None
    start_time: time | None = None
    end_date: date | None = None
    end_time: time | None = None
    time_precision: TimePrecision = TimePrecision.UNKNOWN
    is_all_day: bool = False
    attendance_mode: AttendanceMode = AttendanceMode.UNKNOWN
    raw_location: str | None = None
    suggested_venue_ids: list[int] = Field(default_factory=list)
    meeting_url: str | None = None
    status: OccurrenceStatus = OccurrenceStatus.SCHEDULED


class CandidateOrganizer(StrictModel):
    name: str | None = None
    role: str | None = None
    is_primary: bool = False


class CandidateRegistration(StrictModel):
    scope: RegistrationScope
    occurrence_ref: str | None = None
    name: str | None = None
    url: str | None = None
    opens_date: date | None = None
    opens_time: time | None = None
    closes_date: date | None = None
    closes_time: time | None = None
    instructions: str | None = None


class CandidateEvidence(StrictModel):
    field: str
    source_path: str
    value: str


class CandidateControlledValues(StrictModel):
    supported_codes: list[str] = Field(default_factory=list)
    other_values: list[str] = Field(default_factory=list)


class EventCandidatePayload(StrictModel):
    schema_version: Literal["event-candidate-v2"] = CANDIDATE_SCHEMA_VERSION
    title: str | None = Field(default=None, max_length=500)
    description: str | None = None
    occurrences: list[CandidateOccurrence] = Field(default_factory=list)
    organizers: list[CandidateOrganizer] = Field(default_factory=list)
    registrations: list[CandidateRegistration] = Field(default_factory=list)
    formats: CandidateControlledValues = Field(default_factory=CandidateControlledValues)
    topics: CandidateControlledValues = Field(default_factory=CandidateControlledValues)
    purposes: CandidateControlledValues = Field(default_factory=CandidateControlledValues)
    audiences: CandidateControlledValues = Field(default_factory=CandidateControlledValues)
    image_url: str | None = None
    source_url: str | None = None
    evidence: list[CandidateEvidence] = Field(default_factory=list)
    ambiguities: list[str] = Field(default_factory=list)
    overall_confidence: float | None = Field(default=None, ge=0, le=1)


class ExtractedMessage(StrictModel):
    message_identity: str = Field(min_length=1)
    events: list[EventCandidatePayload] = Field(default_factory=list)


class ExtractionBatch(StrictModel):
    results: list[ExtractedMessage]
