from enum import StrEnum

from pydantic import Field

from ingestion.contracts import EventCandidatePayload, StrictModel

SCREENING_SCHEMA_VERSION = "telegram-screening-v2"
EXTRACTION_SCHEMA_VERSION = "telegram-extraction-v5"


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


class ExtractedMessage(StrictModel):
    message_identity: str = Field(min_length=1)
    events: list[EventCandidatePayload] = Field(default_factory=list)


class ExtractionBatch(StrictModel):
    results: list[ExtractedMessage]
