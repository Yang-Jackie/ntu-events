import pytest
from events.models import Event, EventObservation, EventRevision, VerificationStatus
from ingestion.candidates import CandidateVersionConflict, update_event_candidate
from ingestion.contracts import (
    AttendanceMode,
    CandidateOccurrence,
    CandidateRegistration,
    CanonicalizationAction,
    EventCandidatePayload,
    RegistrationScope,
    TimePrecision,
)
from ingestion.models import CandidateStatus, CanonicalizationPlanStatus

from .canonicalization_test_support import (
    canonicalize_new_candidate,
    complete_payload,
    make_candidate,
)

pytestmark = pytest.mark.django_db


def test_complete_candidate_is_automatically_added_through_a_plan() -> None:
    candidate = make_candidate(complete_payload())

    review = canonicalize_new_candidate(candidate)

    assert review.status == CandidateStatus.PROCESSED
    assert review.edit_version == 1
    plan = review.canonicalization_plan
    assert plan.action == CanonicalizationAction.ADD
    assert plan.status == CanonicalizationPlanStatus.APPLIED, plan.application_error
    event = plan.target_event
    assert event is not None
    assert event.verification_status == VerificationStatus.UNVERIFIED
    assert event.occurrences.get().meeting_url == "https://example.com/meeting"
    observation = EventObservation.objects.get(event_candidate=candidate)
    assert observation.source_link.event == event
    assert EventRevision.objects.get(event=event).before_snapshot == {}


def test_sparse_but_useful_candidate_creates_an_event_shell() -> None:
    candidate = make_candidate(
        EventCandidatePayload(title="Save the date", description="Details will follow.")
    )

    review = canonicalize_new_candidate(candidate)

    assert review.status == CandidateStatus.PROCESSED
    assert {issue["code"] for issue in review.validation_issues} == {"OCCURRENCE_MISSING"}
    plan = review.canonicalization_plan
    assert plan.status == CanonicalizationPlanStatus.APPLIED, plan.application_error
    assert Event.objects.get().title == "Save the date"


def test_title_only_candidate_blocks_the_whole_candidate() -> None:
    review = canonicalize_new_candidate(
        make_candidate(EventCandidatePayload(title="Save the date"))
    )

    assert review.status == CandidateStatus.BLOCKED
    assert not hasattr(review, "canonicalization_plan")
    assert {issue["code"] for issue in review.validation_issues} == {
        "TITLE_ONLY",
        "OCCURRENCE_MISSING",
    }
    assert Event.objects.count() == 0


def test_nonblocking_incomplete_child_is_omitted_from_automatic_add() -> None:
    payload = complete_payload()
    payload.occurrences.append(
        CandidateOccurrence(
            local_ref="broken",
            time_precision=TimePrecision.EXACT,
            attendance_mode=AttendanceMode.IN_PERSON,
        )
    )

    review = canonicalize_new_candidate(make_candidate(payload))

    assert review.status == CandidateStatus.PROCESSED
    assert review.canonicalization_plan.status == CanonicalizationPlanStatus.APPLIED
    assert Event.objects.get().occurrences.count() == 1


def test_invalid_optional_registration_url_is_omitted_from_automatic_add() -> None:
    payload = complete_payload()
    payload.registrations = [
        CandidateRegistration(
            scope=RegistrationScope.EVENT,
            name="Register at the event desk",
            url="not-a-url",
        )
    ]

    review = canonicalize_new_candidate(make_candidate(payload))

    assert review.status == CandidateStatus.PROCESSED
    assert review.canonicalization_plan.status == CanonicalizationPlanStatus.APPLIED
    registration = Event.objects.get().registrations.get()
    assert registration.name == "Register at the event desk"
    assert registration.url == ""


def test_repaired_blocked_candidate_stops_at_ready_and_is_then_frozen() -> None:
    candidate = make_candidate(EventCandidatePayload(title="Save the date"))
    repaired = complete_payload().model_dump(mode="json")

    update_event_candidate(
        candidate.pk,
        expected_version=candidate.edit_version,
        effective_payload=repaired,
        reviewer_notes="Repaired from the source.",
        edited_by_id=None,
    )

    candidate.refresh_from_db()
    assert candidate.status == CandidateStatus.READY
    assert candidate.edit_version == 2
    assert not hasattr(candidate, "canonicalization_plan")
    with pytest.raises(CandidateVersionConflict, match="can no longer be edited"):
        update_event_candidate(
            candidate.pk,
            expected_version=candidate.edit_version,
            effective_payload=repaired,
            reviewer_notes="Second edit",
            edited_by_id=None,
        )
