from __future__ import annotations

from datetime import date, time, timedelta
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

CANDIDATE_SCHEMA_VERSION = "event-candidate-v3"
SCREENING_SCHEMA_VERSION = "telegram-screening-v2"
EXTRACTION_SCHEMA_VERSION = "telegram-extraction-v5"
CANONICALIZATION_SCHEMA_VERSION = "canonicalization-plan-v3"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _normalize_singapore_wall_clock(value: time | None) -> time | None:
    """Canonicalize an explicit Singapore offset without changing clock or date."""
    if value is not None and value.utcoffset() == timedelta(hours=8):
        return value.replace(tzinfo=None)
    return value


def _require_singapore_wall_clock(value: time | None) -> time | None:
    """Reject non-Singapore offsets that cannot be converted without a date."""
    if value is not None and value.tzinfo is not None:
        raise ValueError(
            "Times must be offset-free Singapore wall-clock values or use the +08:00 offset."
        )
    return value


LocalTime = Annotated[
    time | None,
    AfterValidator(_normalize_singapore_wall_clock),
    AfterValidator(_require_singapore_wall_clock),
]


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


class ObservationType(StrEnum):
    EVENT_ANNOUNCEMENT = "EVENT_ANNOUNCEMENT"
    EVENT_FOLLOW_UP = "EVENT_FOLLOW_UP"
    UNKNOWN = "UNKNOWN"


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


class ExtractedMessage(StrictModel):
    message_identity: str = Field(min_length=1)
    events: list[EventCandidatePayload] = Field(default_factory=list)


class ExtractionBatch(StrictModel):
    results: list[ExtractedMessage]


class CanonicalizationAction(StrEnum):
    ADD = "ADD"
    UPDATE = "UPDATE"
    LINK_ONLY = "LINK_ONLY"


class ObjectOperation(StrEnum):
    ADD = "ADD"
    UPDATE = "UPDATE"
    REMOVE = "REMOVE"


class FieldOperation(StrEnum):
    SET = "SET"
    CLEAR = "CLEAR"


class EventField(StrEnum):
    TITLE = "TITLE"
    DESCRIPTION = "DESCRIPTION"
    IMAGE_REFERENCE = "IMAGE_REFERENCE"
    AUDIENCE_NOTES = "AUDIENCE_NOTES"


class ClassificationKind(StrEnum):
    FORMAT = "FORMAT"
    TOPIC = "TOPIC"
    PURPOSE = "PURPOSE"
    AUDIENCE = "AUDIENCE"


class ClassificationOperation(StrEnum):
    ADD_CODES = "ADD_CODES"
    REMOVE_CODES = "REMOVE_CODES"
    REPLACE_CODES = "REPLACE_CODES"


class OccurrenceField(StrEnum):
    LABEL = "LABEL"
    SEQUENCE = "SEQUENCE"
    START_DATE = "START_DATE"
    START_TIME = "START_TIME"
    END_DATE = "END_DATE"
    END_TIME = "END_TIME"
    TIME_PRECISION = "TIME_PRECISION"
    IS_ALL_DAY = "IS_ALL_DAY"
    ATTENDANCE_MODE = "ATTENDANCE_MODE"
    RAW_LOCATION_TEXT = "RAW_LOCATION_TEXT"
    MEETING_URL = "MEETING_URL"
    OCCURRENCE_STATUS = "OCCURRENCE_STATUS"
    VENUE_IDS = "VENUE_IDS"


class RegistrationField(StrEnum):
    NAME = "NAME"
    OWNER = "OWNER"
    URL = "URL"
    OPENS_DATE = "OPENS_DATE"
    OPENS_TIME = "OPENS_TIME"
    CLOSES_DATE = "CLOSES_DATE"
    CLOSES_TIME = "CLOSES_TIME"
    INSTRUCTIONS = "INSTRUCTIONS"


class OrganizerField(StrEnum):
    ORGANIZER_ID = "ORGANIZER_ID"
    ROLE = "ROLE"
    IS_PRIMARY = "IS_PRIMARY"
    POSITION = "POSITION"


class CanonicalEventFieldChange(StrictModel):
    field: EventField
    operation: FieldOperation
    value: str | None

    @model_validator(mode="after")
    def validate_operation(self) -> CanonicalEventFieldChange:
        if self.operation == FieldOperation.SET and self.value is None:
            raise ValueError("SET requires a value")
        if self.operation == FieldOperation.CLEAR and self.value is not None:
            raise ValueError("CLEAR requires a null value")
        if self.field == EventField.TITLE and self.operation == FieldOperation.CLEAR:
            raise ValueError("Event title cannot be cleared")
        return self


class CanonicalClassificationChange(StrictModel):
    kind: ClassificationKind
    operation: ClassificationOperation
    codes: list[str]

    @model_validator(mode="after")
    def validate_codes(self) -> CanonicalClassificationChange:
        if len(self.codes) != len(set(self.codes)):
            raise ValueError("Classification codes cannot contain duplicates")
        if self.operation != ClassificationOperation.REPLACE_CODES and not self.codes:
            raise ValueError("ADD_CODES and REMOVE_CODES require at least one code")
        return self


class CanonicalOrganizerValue(StrictModel):
    organizer_id: int
    role: str | None
    is_primary: bool
    position: int


class CanonicalOrganizerChange(StrictModel):
    operation: ObjectOperation
    id: int | None
    changed_fields: list[OrganizerField]
    value: CanonicalOrganizerValue | None


class CanonicalOccurrenceValue(StrictModel):
    client_ref: str | None
    label: str | None
    sequence: int | None
    start_date: date | None
    start_time: LocalTime
    end_date: date | None
    end_time: LocalTime
    time_precision: TimePrecision | None
    is_all_day: bool | None
    attendance_mode: AttendanceMode | None
    raw_location_text: str | None
    meeting_url: str | None
    occurrence_status: OccurrenceStatus | None
    venue_ids: list[int] | None


class CanonicalOccurrenceChange(StrictModel):
    operation: ObjectOperation
    id: int | None
    changed_fields: list[OccurrenceField]
    value: CanonicalOccurrenceValue | None


class CanonicalRegistrationValue(StrictModel):
    name: str | None
    scope: RegistrationScope | None
    occurrence_id: int | None
    occurrence_client_ref: str | None
    url: str | None
    opens_date: date | None
    opens_time: LocalTime
    closes_date: date | None
    closes_time: LocalTime
    instructions: str | None


class CanonicalRegistrationChange(StrictModel):
    operation: ObjectOperation
    id: int | None
    changed_fields: list[RegistrationField]
    value: CanonicalRegistrationValue | None


class CanonicalEventCreate(StrictModel):
    title: str = Field(min_length=1, max_length=500)
    description: str | None
    image_reference: str | None
    audience_notes: str | None
    formats: list[str]
    topics: list[str]
    purposes: list[str]
    audiences: list[str]
    organizers: list[CanonicalOrganizerValue]
    occurrences: list[CanonicalOccurrenceValue]
    registrations: list[CanonicalRegistrationValue]


class CanonicalizationProposal(StrictModel):
    schema_version: Literal["canonicalization-plan-v3"] = CANONICALIZATION_SCHEMA_VERSION
    action: CanonicalizationAction
    target_event_id: int | None
    reasoning: str
    add_event: CanonicalEventCreate | None
    event_changes: list[CanonicalEventFieldChange]
    classification_changes: list[CanonicalClassificationChange]
    organizer_changes: list[CanonicalOrganizerChange]
    occurrence_changes: list[CanonicalOccurrenceChange]
    registration_changes: list[CanonicalRegistrationChange]

    @model_validator(mode="after")
    def validate_action_shape(self) -> CanonicalizationProposal:
        changes = (
            self.event_changes
            or self.classification_changes
            or self.organizer_changes
            or self.occurrence_changes
            or self.registration_changes
        )
        if self.action == CanonicalizationAction.ADD:
            if self.target_event_id is not None or self.add_event is None or changes:
                raise ValueError("ADD requires add_event only and no target event")
        elif self.action == CanonicalizationAction.UPDATE:
            if self.target_event_id is None or self.add_event is not None or not changes:
                raise ValueError("UPDATE requires a target and at least one change")
        elif self.action == CanonicalizationAction.LINK_ONLY:
            if self.target_event_id is None or self.add_event is not None or changes:
                raise ValueError("LINK_ONLY requires a target and no changes")
        return self
