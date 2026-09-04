from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from .common import (
    AttendanceMode,
    LocalTime,
    OccurrenceStatus,
    RegistrationScope,
    StrictModel,
    TimePrecision,
)

CANONICALIZATION_SCHEMA_VERSION = "canonicalization-plan-v3"


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
