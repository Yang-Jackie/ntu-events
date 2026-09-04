from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field

from .common import (
    AttendanceMode,
    LocalTime,
    ObservationType,
    OccurrenceStatus,
    RegistrationScope,
    StrictModel,
    TimePrecision,
)

CANDIDATE_SCHEMA_VERSION = "event-candidate-v3"


class CandidateOccurrence(StrictModel):
    local_ref: str = Field(min_length=1, max_length=100)
    label: str | None = None
    start_date: date | None = None
    start_time: LocalTime = None
    end_date: date | None = None
    end_time: LocalTime = None
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
    opens_time: LocalTime = None
    closes_date: date | None = None
    closes_time: LocalTime = None
    instructions: str | None = None


class CandidateEvidence(StrictModel):
    field: str
    source_path: str
    value: str


class CandidateControlledValues(StrictModel):
    supported_codes: list[str] = Field(default_factory=list)
    other_values: list[str] = Field(default_factory=list)


class EventCandidatePayload(StrictModel):
    schema_version: Literal["event-candidate-v3"] = CANDIDATE_SCHEMA_VERSION
    observation_type: ObservationType = ObservationType.UNKNOWN
    title: str | None = Field(default=None, max_length=500)
    description: str | None = Field(
        default=None,
        description=(
            "Dense summary for a student deciding whether to attend. At most three sentences "
            "and 60 words. Lead with what happens, then what attendees get: food, prizes, "
            "certificates, swag, funding, fees, prerequisites, what to bring, capacity limits. "
            "State recurrence in prose when the source gives a cadence rather than dates, for "
            "example 'every Thursday during term', since occurrences holds only explicitly "
            "dated sessions. Never restate the title, or dates, times, venues, and registration "
            "deadlines already carried by other fields. Never mention what the source omits; "
            "write nothing instead, and leave genuine uncertainty to ambiguities. Pack related "
            "facts into one clause or a comma list rather than a sentence each, stay in active "
            "voice, and cut filler such as 'will be provided' or 'participants can'. Write only "
            "what the source supports; never invent, pad, or infer."
        ),
    )
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
