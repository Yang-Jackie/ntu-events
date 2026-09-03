from datetime import date, time

import pytest
from ingestion.contracts import (
    AttendanceMode,
    CandidateOccurrence,
    CandidateRegistration,
    CanonicalOccurrenceValue,
    CanonicalRegistrationValue,
    EventCandidatePayload,
    ExtractionBatch,
    TimePrecision,
)
from pydantic import ValidationError


def test_business_rule_problem_remains_structurally_valid() -> None:
    occurrence = CandidateOccurrence(
        local_ref="occurrence-1",
        start_date=date(2026, 8, 1),
        time_precision=TimePrecision.EXACT,
    )

    assert occurrence.start_time is None


def test_source_inconsistency_remains_structurally_valid() -> None:
    occurrence = CandidateOccurrence(
        local_ref="occurrence-1",
        start_date=date(2026, 8, 1),
        start_time=time(9),
        time_precision=TimePrecision.EXACT,
        is_all_day=True,
    )

    assert occurrence.is_all_day


def test_crossing_midnight_occurrence_is_one_valid_occurrence() -> None:
    occurrence = CandidateOccurrence(
        local_ref="occurrence-1",
        start_date=date(2026, 8, 1),
        start_time=time(23),
        end_date=date(2026, 8, 2),
        end_time=time(1),
        time_precision=TimePrecision.EXACT,
    )
    assert occurrence.end_date == date(2026, 8, 2)


@pytest.mark.parametrize(
    ("model", "values"),
    [
        (
            CandidateOccurrence,
            {"local_ref": "occurrence-1", "start_time": "01:00:00+14:00"},
        ),
        (
            CandidateRegistration,
            {"scope": "EVENT", "opens_time": "23:00:00-05:00"},
        ),
        (
            CandidateOccurrence,
            {"local_ref": "occurrence-1", "start_time": "19:00:00-23:30"},
        ),
        (
            CanonicalOccurrenceValue,
            {
                "client_ref": None,
                "label": None,
                "sequence": None,
                "start_date": None,
                "start_time": "01:00:00+14:00",
                "end_date": None,
                "end_time": None,
                "time_precision": None,
                "is_all_day": None,
                "attendance_mode": None,
                "raw_location_text": None,
                "meeting_url": None,
                "occurrence_status": None,
                "venue_ids": None,
            },
        ),
        (
            CanonicalRegistrationValue,
            {
                "name": None,
                "scope": None,
                "occurrence_id": None,
                "occurrence_client_ref": None,
                "url": None,
                "opens_date": None,
                "opens_time": None,
                "closes_date": None,
                "closes_time": "23:00:00-05:00",
                "instructions": None,
            },
        ),
    ],
)
def test_time_contracts_reject_non_singapore_offsets(model, values) -> None:
    with pytest.raises(ValidationError, match="offset-free Singapore wall-clock"):
        model.model_validate(values)


@pytest.mark.parametrize(
    ("model", "values", "field"),
    [
        (
            CandidateOccurrence,
            {"local_ref": "occurrence-1", "start_time": "01:00:00+08:00"},
            "start_time",
        ),
        (
            CandidateRegistration,
            {"scope": "EVENT", "opens_time": "23:00:00+08:00"},
            "opens_time",
        ),
        (
            CanonicalOccurrenceValue,
            {
                "client_ref": None,
                "label": None,
                "sequence": None,
                "start_date": None,
                "start_time": "01:00:00+08:00",
                "end_date": None,
                "end_time": None,
                "time_precision": None,
                "is_all_day": None,
                "attendance_mode": None,
                "raw_location_text": None,
                "meeting_url": None,
                "occurrence_status": None,
                "venue_ids": None,
            },
            "start_time",
        ),
        (
            CanonicalRegistrationValue,
            {
                "name": None,
                "scope": None,
                "occurrence_id": None,
                "occurrence_client_ref": None,
                "url": None,
                "opens_date": None,
                "opens_time": None,
                "closes_date": None,
                "closes_time": "23:00:00+08:00",
                "instructions": None,
            },
            "closes_time",
        ),
    ],
)
def test_time_contracts_normalize_singapore_offsets(model, values, field) -> None:
    parsed = model.model_validate(values)

    normalized = getattr(parsed, field)
    assert normalized is not None
    assert normalized.tzinfo is None
    assert normalized == time.fromisoformat(values[field]).replace(tzinfo=None)


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


def test_candidate_registration_rejects_removed_series_scope() -> None:
    with pytest.raises(ValidationError):
        CandidateRegistration(scope="SERIES", name="Series registration")


@pytest.mark.parametrize("source_url", ["not-a-url", "ftp://example.com/event"])
def test_candidate_keeps_semantically_invalid_url_for_business_validation(source_url: str) -> None:
    candidate = _candidate(source_url=source_url)

    assert candidate.source_url == source_url


def _candidate(**overrides: object) -> EventCandidatePayload:
    values: dict[str, object] = {
        "title": "Test event",
        "occurrences": [
            CandidateOccurrence(
                local_ref="occurrence-1",
                start_date=date(2026, 8, 1),
                start_time=time(9),
                time_precision=TimePrecision.EXACT,
                attendance_mode=AttendanceMode.ONLINE,
                meeting_url="https://example.com/meeting",
            )
        ],
        "source_url": "https://t.me/test_channel/1",
    }
    values.update(overrides)
    return EventCandidatePayload.model_validate(values)
