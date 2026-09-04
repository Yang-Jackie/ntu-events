from datetime import time, timedelta
from enum import StrEnum
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict


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
