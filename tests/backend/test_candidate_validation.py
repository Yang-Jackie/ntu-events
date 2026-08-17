from datetime import date, time

from ingestion.contracts import (
    AttendanceMode,
    CandidateControlledValues,
    CandidateOccurrence,
    CandidateRegistration,
    EventCandidatePayload,
    RegistrationScope,
    TimePrecision,
)
from ingestion.models import ValidationStatus
from ingestion.validation import validate_candidate

REFERENCE_DATA = {
    "classifications": {
        "formats": [{"code": "TALK", "label": "Talk", "description": ""}],
        "topics": [{"code": "TECH", "label": "Technology", "description": ""}],
        "purposes": [],
        "audiences": [],
    },
    "venues": [{"id": 7, "name": "The Arc"}],
}


def test_online_candidate_can_be_ready_without_a_physical_location() -> None:
    candidate = _candidate(
        occurrences=[
            CandidateOccurrence(
                local_ref="online-session",
                start_date=date(2026, 9, 1),
                start_time=time(19),
                time_precision=TimePrecision.EXACT,
                attendance_mode=AttendanceMode.ONLINE,
                meeting_url="https://example.com/meeting",
            )
        ]
    )

    result = validate_candidate(candidate, REFERENCE_DATA)

    assert result.status == ValidationStatus.READY
    assert result.issues == []


def test_business_rule_contradictions_are_returned_as_blocking_issues() -> None:
    candidate = _candidate(
        occurrences=[
            CandidateOccurrence(
                local_ref="session-1",
                start_date=date(2026, 9, 2),
                start_time=time(12),
                end_date=date(2026, 9, 1),
                end_time=time(10),
                time_precision=TimePrecision.EXACT,
                attendance_mode=AttendanceMode.IN_PERSON,
                raw_location="The Arc",
                suggested_venue_ids=[7],
            )
        ],
        registrations=[
            CandidateRegistration(
                scope=RegistrationScope.EVENT,
                name="Register",
                opens_date=date(2026, 8, 10),
                closes_date=date(2026, 8, 9),
            )
        ],
    )

    result = validate_candidate(candidate, REFERENCE_DATA)
    issues = {issue["code"]: issue for issue in result.issues}

    assert result.status == ValidationStatus.REVIEW_REQUIRED
    assert issues["OCCURRENCE_END_BEFORE_START"]["blocks_canonicalization"] is True
    assert issues["REGISTRATION_CLOSE_BEFORE_OPEN"]["blocks_canonicalization"] is True


def test_unknown_controlled_values_are_retained_for_review() -> None:
    candidate = _candidate(
        formats=CandidateControlledValues(
            supported_codes=["NOT_SUPPORTED"],
            other_values=["fireside conversation"],
        )
    )

    result = validate_candidate(candidate, REFERENCE_DATA)
    codes = {issue["code"] for issue in result.issues}

    assert "UNSUPPORTED_CLASSIFICATION_CODE" in codes
    assert "UNMAPPED_CLASSIFICATION" in codes


def test_occurrence_scoped_registration_requires_a_known_stable_reference() -> None:
    candidate = _candidate(
        registrations=[
            CandidateRegistration(
                scope=RegistrationScope.OCCURRENCE,
                occurrence_ref="missing-session",
                name="Register",
            )
        ]
    )

    result = validate_candidate(candidate, REFERENCE_DATA)

    assert any(
        issue["code"] == "REGISTRATION_OCCURRENCE_REFERENCE_UNKNOWN" for issue in result.issues
    )


def test_off_campus_location_is_not_rejected_for_product_eligibility() -> None:
    candidate = _candidate(
        occurrences=[
            CandidateOccurrence(
                local_ref="session-1",
                start_date=date(2026, 9, 1),
                start_time=time(10),
                time_precision=TimePrecision.EXACT,
                attendance_mode=AttendanceMode.IN_PERSON,
                raw_location="National Library, Victoria Street",
            )
        ]
    )

    result = validate_candidate(candidate, REFERENCE_DATA)
    codes = {issue["code"] for issue in result.issues}

    assert "OUTSIDE_NTU_CAMPUS" not in codes
    assert "VENUE_UNRESOLVED" in codes


def test_missing_occurrence_is_review_only_not_a_canonicalization_blocker() -> None:
    result = validate_candidate(_candidate(occurrences=[]), REFERENCE_DATA)

    issue = next(issue for issue in result.issues if issue["code"] == "OCCURRENCE_MISSING")

    assert result.status == ValidationStatus.REVIEW_REQUIRED
    assert issue["blocks_canonicalization"] is False


def test_incomplete_child_fields_are_review_only() -> None:
    candidate = _candidate(
        occurrences=[
            CandidateOccurrence(
                local_ref="unknown-date",
                time_precision=TimePrecision.EXACT,
                attendance_mode=AttendanceMode.UNKNOWN,
            )
        ],
        registrations=[
            CandidateRegistration(
                scope=RegistrationScope.OCCURRENCE,
                occurrence_ref="missing-session",
            )
        ],
    )

    result = validate_candidate(candidate, REFERENCE_DATA)

    assert result.issues
    assert all(issue["blocks_canonicalization"] is False for issue in result.issues)


def _candidate(**overrides: object) -> EventCandidatePayload:
    values: dict[str, object] = {
        "title": "Test event",
        "occurrences": [
            CandidateOccurrence(
                local_ref="session-1",
                start_date=date(2026, 9, 1),
                start_time=time(10),
                time_precision=TimePrecision.EXACT,
                attendance_mode=AttendanceMode.IN_PERSON,
                raw_location="The Arc",
                suggested_venue_ids=[7],
            )
        ],
        "source_url": "https://t.me/test/1",
    }
    values.update(overrides)
    return EventCandidatePayload.model_validate(values)
