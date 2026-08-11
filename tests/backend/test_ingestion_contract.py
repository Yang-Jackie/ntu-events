from datetime import date, time

import pytest
from ingestion.contracts import (
    CandidateOccurrence,
    EventCandidatePayload,
    ExtractionBatch,
    TimePrecision,
)
from pydantic import ValidationError


def test_exact_occurrence_requires_a_start_time() -> None:
    with pytest.raises(ValidationError):
        CandidateOccurrence(
            start_date=date(2026, 8, 1),
            time_precision=TimePrecision.EXACT,
        )


def test_all_day_occurrence_rejects_times() -> None:
    with pytest.raises(ValidationError):
        CandidateOccurrence(
            start_date=date(2026, 8, 1),
            start_time=time(9),
            time_precision=TimePrecision.EXACT,
            is_all_day=True,
        )


def test_crossing_midnight_occurrence_is_one_valid_occurrence() -> None:
    occurrence = CandidateOccurrence(
        start_date=date(2026, 8, 1),
        start_time=time(23),
        end_date=date(2026, 8, 2),
        end_time=time(1),
        time_precision=TimePrecision.EXACT,
    )
    assert occurrence.end_date == date(2026, 8, 2)


def test_extraction_schema_exposes_urls_as_plain_strings() -> None:
    schema = ExtractionBatch.model_json_schema()

    def contains_uri_format(value: object) -> bool:
        if isinstance(value, dict):
            return value.get("format") == "uri" or any(
                contains_uri_format(item) for item in value.values()
            )
        if isinstance(value, list):
            return any(contains_uri_format(item) for item in value)
        return False

    assert not contains_uri_format(schema)


def test_candidate_accepts_valid_http_urls() -> None:
    candidate = _candidate(
        source_url="https://t.me/test_channel/1",
        image_url="https://example.com/poster.png",
    )

    assert candidate.source_url == "https://t.me/test_channel/1"
    assert candidate.image_url == "https://example.com/poster.png"


@pytest.mark.parametrize("source_url", ["not-a-url", "ftp://example.com/event"])
def test_candidate_rejects_invalid_or_non_http_source_urls(source_url: str) -> None:
    with pytest.raises(ValidationError):
        _candidate(source_url=source_url)


def _candidate(**overrides: object) -> EventCandidatePayload:
    values: dict[str, object] = {
        "title": "Test event",
        "occurrences": [
            CandidateOccurrence(
                start_date=date(2026, 8, 1),
                start_time=time(9),
                time_precision=TimePrecision.EXACT,
            )
        ],
        "source_url": "https://t.me/test_channel/1",
    }
    values.update(overrides)
    return EventCandidatePayload.model_validate(values)
