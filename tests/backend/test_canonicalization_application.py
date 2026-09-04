import pytest
from events.models import (
    Event,
    EventObservation,
    EventPurpose,
    EventRevision,
    EventSourceLink,
)
from ingestion.canonicalization import apply_canonicalization_plan, canonicalize_candidate
from ingestion.contracts import (
    AttendanceMode,
    CandidateControlledValues,
    CanonicalClassificationChange,
    CanonicalEventCreate,
    CanonicalizationAction,
    CanonicalizationProposal,
    CanonicalOccurrenceChange,
    ClassificationKind,
    ClassificationOperation,
    ObjectOperation,
    OccurrenceField,
)
from ingestion.models import (
    CandidateMatch,
    CandidateStatus,
    CanonicalizationPlan,
    CanonicalizationPlanStatus,
)
from venues.models import Venue, VenueType

from .canonicalization_test_support import (
    canonicalize_new_candidate,
    complete_payload,
    empty_occurrence_value,
    make_candidate,
    update_description_proposal,
)

pytestmark = pytest.mark.django_db


def test_update_plan_changes_one_match_and_links_the_new_observation() -> None:
    first = canonicalize_new_candidate(make_candidate(complete_payload(), identity="message-1"))
    event = first.canonicalization_plan.target_event
    follow_up = complete_payload()
    follow_up.description = "A new source-grounded combined description."
    review = make_candidate(follow_up, identity="message-2")
    proposal = update_description_proposal(event.pk, follow_up.description)

    plan = canonicalize_candidate(
        review.pk,
        expected_version=review.edit_version,
        decision=proposal,
    )

    event.refresh_from_db()
    assert plan.status == CanonicalizationPlanStatus.APPLIED
    assert event.description == follow_up.description
    assert EventSourceLink.objects.filter(event=event).count() == 2
    assert EventObservation.objects.filter(source_link__event=event).count() == 2
    assert EventRevision.objects.filter(event=event).count() == 2


def test_classification_add_codes_preserves_existing_codes() -> None:
    EventPurpose.objects.get(code="NETWORKING_COMMUNITY")
    EventPurpose.objects.get(code="LEARNING_RESEARCH")
    original = complete_payload()
    original.purposes = CandidateControlledValues(supported_codes=["NETWORKING_COMMUNITY"])
    first = canonicalize_new_candidate(make_candidate(original, identity="message-1"))
    event = first.canonicalization_plan.target_event
    follow_up = complete_payload()
    candidate = make_candidate(follow_up, identity="message-2")
    proposal = CanonicalizationProposal(
        action=CanonicalizationAction.UPDATE,
        target_event_id=event.pk,
        reasoning="Add a newly supported purpose without replacing the existing purpose.",
        add_event=None,
        event_changes=[],
        classification_changes=[
            CanonicalClassificationChange(
                kind=ClassificationKind.PURPOSE,
                operation=ClassificationOperation.ADD_CODES,
                codes=["LEARNING_RESEARCH"],
            )
        ],
        organizer_changes=[],
        occurrence_changes=[],
        registration_changes=[],
    )

    plan = canonicalize_candidate(
        candidate.pk,
        expected_version=candidate.edit_version,
        decision=proposal,
    )

    event.refresh_from_db()
    assert plan.status == CanonicalizationPlanStatus.APPLIED
    assert set(event.purposes.values_list("code", flat=True)) == {
        "NETWORKING_COMMUNITY",
        "LEARNING_RESEARCH",
    }


def test_add_can_create_a_separate_event_even_when_matches_exist() -> None:
    canonicalize_new_candidate(make_candidate(complete_payload(), identity="message-1"))
    review = make_candidate(complete_payload(), identity="message-2")
    proposal = CanonicalizationProposal(
        action=CanonicalizationAction.ADD,
        target_event_id=None,
        reasoning="The apparent match is a separate event edition.",
        add_event=CanonicalEventCreate(
            title="Test event - separate edition",
            description="Initial event description.",
            image_reference=None,
            audience_notes=None,
            formats=[],
            topics=[],
            purposes=[],
            audiences=[],
            organizers=[],
            occurrences=[],
            registrations=[],
        ),
        event_changes=[],
        classification_changes=[],
        organizer_changes=[],
        occurrence_changes=[],
        registration_changes=[],
    )

    plan = canonicalize_candidate(
        review.pk,
        expected_version=review.edit_version,
        decision=proposal,
    )

    assert plan.status == CanonicalizationPlanStatus.APPLIED, plan.application_error
    assert CandidateMatch.objects.filter(event_candidate=review).exists()
    assert Event.objects.count() == 2


def test_nonexistent_catalog_reference_rejects_the_entire_plan() -> None:
    payload = complete_payload()
    payload.occurrences[0].suggested_venue_ids = [999999]

    review = canonicalize_new_candidate(make_candidate(payload))

    plan = review.canonicalization_plan
    assert review.status == CandidateStatus.PROCESSED
    assert plan.status == CanonicalizationPlanStatus.REJECTED
    assert {issue["code"] for issue in plan.validation_issues} == {"VENUE_NOT_FOUND"}
    assert Event.objects.count() == 0


def test_unsupported_classification_rejects_the_entire_plan() -> None:
    payload = complete_payload()
    payload.formats = CandidateControlledValues(supported_codes=["NOT_SUPPORTED"])

    review = canonicalize_new_candidate(make_candidate(payload))

    plan = review.canonicalization_plan
    assert plan.status == CanonicalizationPlanStatus.REJECTED
    assert any(
        issue["code"] == "UNSUPPORTED_CLASSIFICATION_CODE" for issue in plan.validation_issues
    )
    assert Event.objects.count() == 0


def test_stale_update_does_not_overwrite_a_changed_event() -> None:
    first = canonicalize_new_candidate(make_candidate(complete_payload(), identity="message-1"))
    event = first.canonicalization_plan.target_event
    review = make_candidate(complete_payload(), identity="message-2")
    plan = canonicalize_candidate(
        review.pk,
        expected_version=review.edit_version,
        decision=update_description_proposal(event.pk, "Proposed description"),
        apply_ready=False,
    )
    event.description = "Manual concurrent edit"
    event.save()

    result = apply_canonicalization_plan(plan.pk, expected_version=plan.plan_version)

    event.refresh_from_db()
    plan.refresh_from_db()
    assert result.status == CanonicalizationPlanStatus.STALE
    assert plan.status == CanonicalizationPlanStatus.STALE
    assert event.description == "Manual concurrent edit"


def test_occurrence_update_explicitly_clears_venue_and_sets_tba_text() -> None:
    venue = Venue.objects.create(
        name="North Spine",
        normalized_name="north spine",
        venue_type=VenueType.OTHER,
        is_verified=True,
    )
    payload = complete_payload()
    payload.occurrences[0].attendance_mode = AttendanceMode.IN_PERSON
    payload.occurrences[0].raw_location = "North Spine"
    payload.occurrences[0].meeting_url = None
    payload.occurrences[0].suggested_venue_ids = [venue.pk]
    first = canonicalize_new_candidate(make_candidate(payload, identity="message-1"))
    event = first.canonicalization_plan.target_event
    occurrence = event.occurrences.get()
    review = make_candidate(payload, identity="message-2")
    proposal = CanonicalizationProposal(
        action=CanonicalizationAction.UPDATE,
        target_event_id=event.pk,
        reasoning="The follow-up replaces the known venue with TBA.",
        add_event=None,
        event_changes=[],
        classification_changes=[],
        organizer_changes=[],
        occurrence_changes=[
            CanonicalOccurrenceChange(
                operation=ObjectOperation.UPDATE,
                id=occurrence.pk,
                changed_fields=[OccurrenceField.RAW_LOCATION_TEXT, OccurrenceField.VENUE_IDS],
                value=empty_occurrence_value(raw_location_text="TBA", venue_ids=[]),
            )
        ],
        registration_changes=[],
    )

    plan = canonicalize_candidate(
        review.pk,
        expected_version=review.edit_version,
        decision=proposal,
    )

    occurrence.refresh_from_db()
    assert plan.status == CanonicalizationPlanStatus.APPLIED, plan.application_error
    assert occurrence.raw_location_text == "TBA"
    assert occurrence.venues.count() == 0


def test_reapplying_an_applied_plan_is_idempotent() -> None:
    review = canonicalize_new_candidate(make_candidate(complete_payload()))
    plan = CanonicalizationPlan.objects.get(event_candidate=review)

    apply_canonicalization_plan(plan.pk, expected_version=plan.plan_version)

    assert Event.objects.count() == 1
    assert EventObservation.objects.count() == 1
    assert EventRevision.objects.count() == 1
