from datetime import date, time
from decimal import Decimal

import pytest
from django.utils import timezone
from events.models import (
    Event,
    EventObservation,
    EventPurpose,
    EventRevision,
    EventSourceLink,
    VerificationStatus,
)
from ingestion.candidate_validation import validate_candidate
from ingestion.candidates import (
    CandidateVersionConflict,
    candidate_status_for_issues,
    update_event_candidate,
)
from ingestion.canonicalization import (
    apply_canonicalization_plan,
    canonicalize_candidate,
    find_candidate_matches,
)
from ingestion.canonicalization.matching import _date_similarity, normalize_match_url
from ingestion.contracts import (
    AttendanceMode,
    CandidateControlledValues,
    CandidateOccurrence,
    CandidateOrganizer,
    CandidateRegistration,
    CanonicalClassificationChange,
    CanonicalEventCreate,
    CanonicalEventFieldChange,
    CanonicalizationAction,
    CanonicalizationProposal,
    CanonicalOccurrenceChange,
    CanonicalOccurrenceValue,
    ClassificationKind,
    ClassificationOperation,
    EventCandidatePayload,
    EventField,
    FieldOperation,
    ObjectOperation,
    OccurrenceField,
    RegistrationScope,
    TimePrecision,
)
from ingestion.models import (
    CandidateMatch,
    CandidateStatus,
    CanonicalizationPlan,
    CanonicalizationPlanStatus,
    EventCandidate,
    ExtractionRun,
    ExtractionStatus,
)
from ingestion.reference_data import build_candidate_reference_data
from organizers.models import Organizer
from sources.models import (
    ProcessingStatus,
    RawSourceDocument,
    Source,
    SourceRepresentation,
    SourceType,
)
from venues.models import Venue, VenueType

pytestmark = pytest.mark.django_db


def test_complete_candidate_is_automatically_added_through_a_plan() -> None:
    candidate = _make_candidate(_complete_payload())

    review = _canonicalize_new_candidate(candidate)

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
    candidate = _make_candidate(
        EventCandidatePayload(title="Save the date", description="Details will follow.")
    )

    review = _canonicalize_new_candidate(candidate)

    assert review.status == CandidateStatus.PROCESSED
    assert {issue["code"] for issue in review.validation_issues} == {"OCCURRENCE_MISSING"}
    plan = review.canonicalization_plan
    assert plan.status == CanonicalizationPlanStatus.APPLIED, plan.application_error
    assert Event.objects.get().title == "Save the date"


def test_title_only_candidate_blocks_the_whole_candidate() -> None:
    review = _canonicalize_new_candidate(
        _make_candidate(EventCandidatePayload(title="Save the date"))
    )

    assert review.status == CandidateStatus.BLOCKED
    assert not hasattr(review, "canonicalization_plan")
    assert {issue["code"] for issue in review.validation_issues} == {
        "TITLE_ONLY",
        "OCCURRENCE_MISSING",
    }
    assert Event.objects.count() == 0


def test_nonblocking_incomplete_child_is_omitted_from_automatic_add() -> None:
    payload = _complete_payload()
    payload.occurrences.append(
        CandidateOccurrence(
            local_ref="broken",
            time_precision=TimePrecision.EXACT,
            attendance_mode=AttendanceMode.IN_PERSON,
        )
    )

    review = _canonicalize_new_candidate(_make_candidate(payload))

    assert review.status == CandidateStatus.PROCESSED
    assert review.canonicalization_plan.status == CanonicalizationPlanStatus.APPLIED
    assert Event.objects.get().occurrences.count() == 1


def test_invalid_optional_registration_url_is_omitted_from_automatic_add() -> None:
    payload = _complete_payload()
    payload.registrations = [
        CandidateRegistration(
            scope=RegistrationScope.EVENT,
            name="Register at the event desk",
            url="not-a-url",
        )
    ]

    review = _canonicalize_new_candidate(_make_candidate(payload))

    assert review.status == CandidateStatus.PROCESSED
    assert review.canonicalization_plan.status == CanonicalizationPlanStatus.APPLIED
    registration = Event.objects.get().registrations.get()
    assert registration.name == "Register at the event desk"
    assert registration.url == ""


def test_repaired_blocked_candidate_stops_at_ready_and_is_then_frozen() -> None:
    candidate = _make_candidate(EventCandidatePayload(title="Save the date"))
    repaired = _complete_payload().model_dump(mode="json")

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


def test_match_without_a_decision_creates_a_review_required_plan() -> None:
    first = _canonicalize_new_candidate(_make_candidate(_complete_payload(), identity="message-1"))
    event = first.canonicalization_plan.target_event
    second = _canonicalize_new_candidate(_make_candidate(_complete_payload(), identity="message-2"))

    plan = second.canonicalization_plan
    assert plan.status == CanonicalizationPlanStatus.REVIEW_REQUIRED
    assert plan.action == ""
    assert CandidateMatch.objects.get(event_candidate=second).event == event
    assert Event.objects.count() == 1


def test_sparse_follow_up_title_is_matched_by_normalized_percentage() -> None:
    announcement = _complete_payload()
    announcement.title = "Introduction to Git and GitHub"
    first = _canonicalize_new_candidate(_make_candidate(announcement, identity="message-88"))
    event = first.canonicalization_plan.target_event
    follow_up = EventCandidatePayload(
        title="Introduction to Git and GitHub — sign-up reminder",
        description="Please sign up for the workshop.",
        registrations=[
            CandidateRegistration(
                scope=RegistrationScope.EVENT,
                name="Sign-up form",
                url="https://forms.example/github-workshop",
            )
        ],
    )

    review = _canonicalize_new_candidate(_make_candidate(follow_up, identity="message-89"))

    match = CandidateMatch.objects.get(event_candidate=review)
    assert match.event == event
    assert match.score >= Decimal("0.3000")
    summary = match.signals[0]
    assert summary["kind"] == "MATCH_SUMMARY"
    assert summary["match_percentage"] >= 30
    assert "TITLE_SIMILARITY" in summary["evidence_signals"]
    plan = review.canonicalization_plan
    assert plan.status == CanonicalizationPlanStatus.REVIEW_REQUIRED
    assert plan.match_snapshot[0]["match_percentage"] >= 30
    assert "score" not in plan.match_snapshot[0]


def test_match_score_is_a_fixed_sum_without_an_available_field_denominator() -> None:
    Event.objects.create(
        slug="indexed-event",
        title="Indexed event",
        normalized_title="indexed event",
        description="Canonical description",
    )
    payload = EventCandidatePayload(
        title="Indexed event",
        description="Candidate description",
        registrations=[
            CandidateRegistration(
                scope=RegistrationScope.EVENT,
                url="https://forms.example/new-only",
            )
        ],
    )
    review = _make_candidate(payload, identity="indexed-candidate")

    match = find_candidate_matches(review, payload)[0]

    assert Decimal(str(match.score)) == Decimal("0.6500")
    signals = {signal["kind"]: signal for signal in match.signals}
    assert signals["TITLE"]["contribution_percentage"] == 65
    assert signals["REGISTRATION_URL"]["contribution_percentage"] == 0
    assert signals["SOURCE"]["contribution_percentage"] == 0
    assert "comparable_weight_percentage" not in signals["MATCH_SUMMARY"]


def test_moderate_title_similarity_plus_same_date_qualifies_without_an_identity_gate() -> None:
    announcement = _complete_payload()
    announcement.title = "Leather workshop — make your own leather card holder"
    first = _canonicalize_new_candidate(_make_candidate(announcement, identity="message-1"))
    event = first.canonicalization_plan.target_event
    reminder = _complete_payload()
    reminder.title = "Leather Card Holder workshop — same-day reminder"
    candidate = _make_candidate(reminder, identity="message-2")

    matches = find_candidate_matches(candidate, reminder)

    assert matches
    assert matches[0].event == event
    assert matches[0].score >= Decimal("0.3000")


def test_dates_at_least_120_days_apart_contribute_negative_twenty_points() -> None:
    assert _date_similarity({date(2026, 1, 1)}, {date(2026, 5, 1)}) == -2.0
    assert _date_similarity({date(2026, 1, 1)}, {date(2026, 4, 30)}) == 0.0


def test_registration_url_normalization_ignores_scheme_www_and_trailing_slash() -> None:
    assert normalize_match_url("http://www.example.com/register/") == normalize_match_url(
        "https://example.com/register"
    )


def test_only_the_five_highest_percentage_matches_are_stored() -> None:
    for index in range(7):
        Event.objects.create(
            slug=f"indexed-event-{index}",
            title="Indexed event",
            normalized_title="indexed event",
            description=f"Canonical description {index}",
        )
    payload = EventCandidatePayload(
        title="Indexed event",
        description="Candidate description",
    )
    review = _make_candidate(payload, identity="top-five")

    matches = find_candidate_matches(review, payload)

    assert len(matches) == 5
    assert [match.rank for match in matches] == [1, 2, 3, 4, 5]
    assert {Decimal(str(match.score)) for match in matches} == {Decimal("0.6500")}


def test_non_identity_fields_cannot_qualify_a_match() -> None:
    organizer = Organizer.objects.create(
        name="Shared organizer", normalized_name="shared organizer"
    )
    venue = Venue.objects.create(
        name="Shared venue",
        normalized_name="shared venue",
        venue_type=VenueType.OTHER,
        is_verified=True,
    )
    first_payload = _complete_payload()
    first_payload.title = "Robotics design workshop"
    first_payload.organizers = [CandidateOrganizer(name=organizer.name, is_primary=True)]
    first_payload.occurrences[0].suggested_venue_ids = [venue.pk]
    _canonicalize_new_candidate(_make_candidate(first_payload, identity="robotics"))
    unrelated = _complete_payload()
    unrelated.title = "Community garden planning"
    unrelated.organizers = [CandidateOrganizer(name=organizer.name, is_primary=True)]
    unrelated.occurrences[0].suggested_venue_ids = [venue.pk]
    review = _make_candidate(unrelated, identity="garden")

    matches = find_candidate_matches(review, unrelated)

    assert matches == []


def test_update_plan_changes_one_match_and_links_the_new_observation() -> None:
    first = _canonicalize_new_candidate(_make_candidate(_complete_payload(), identity="message-1"))
    event = first.canonicalization_plan.target_event
    follow_up = _complete_payload()
    follow_up.description = "A new source-grounded combined description."
    review = _make_candidate(follow_up, identity="message-2")
    proposal = _update_description_proposal(event.pk, follow_up.description)

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
    original = _complete_payload()
    original.purposes = CandidateControlledValues(supported_codes=["NETWORKING_COMMUNITY"])
    first = _canonicalize_new_candidate(_make_candidate(original, identity="message-1"))
    event = first.canonicalization_plan.target_event
    follow_up = _complete_payload()
    candidate = _make_candidate(follow_up, identity="message-2")
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
    _canonicalize_new_candidate(_make_candidate(_complete_payload(), identity="message-1"))
    review = _make_candidate(_complete_payload(), identity="message-2")
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
    payload = _complete_payload()
    payload.occurrences[0].suggested_venue_ids = [999999]

    review = _canonicalize_new_candidate(_make_candidate(payload))

    plan = review.canonicalization_plan
    assert review.status == CandidateStatus.PROCESSED
    assert plan.status == CanonicalizationPlanStatus.REJECTED
    assert {issue["code"] for issue in plan.validation_issues} == {"VENUE_NOT_FOUND"}
    assert Event.objects.count() == 0


def test_unsupported_classification_rejects_the_entire_plan() -> None:
    payload = _complete_payload()
    payload.formats = CandidateControlledValues(supported_codes=["NOT_SUPPORTED"])

    review = _canonicalize_new_candidate(_make_candidate(payload))

    plan = review.canonicalization_plan
    assert plan.status == CanonicalizationPlanStatus.REJECTED
    assert any(
        issue["code"] == "UNSUPPORTED_CLASSIFICATION_CODE" for issue in plan.validation_issues
    )
    assert Event.objects.count() == 0


def test_stale_update_does_not_overwrite_a_changed_event() -> None:
    first = _canonicalize_new_candidate(_make_candidate(_complete_payload(), identity="message-1"))
    event = first.canonicalization_plan.target_event
    review = _make_candidate(_complete_payload(), identity="message-2")
    plan = canonicalize_candidate(
        review.pk,
        expected_version=review.edit_version,
        decision=_update_description_proposal(event.pk, "Proposed description"),
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
    payload = _complete_payload()
    payload.occurrences[0].attendance_mode = AttendanceMode.IN_PERSON
    payload.occurrences[0].raw_location = "North Spine"
    payload.occurrences[0].meeting_url = None
    payload.occurrences[0].suggested_venue_ids = [venue.pk]
    first = _canonicalize_new_candidate(_make_candidate(payload, identity="message-1"))
    event = first.canonicalization_plan.target_event
    occurrence = event.occurrences.get()
    review = _make_candidate(payload, identity="message-2")
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
                value=_empty_occurrence_value(raw_location_text="TBA", venue_ids=[]),
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
    review = _canonicalize_new_candidate(_make_candidate(_complete_payload()))
    plan = CanonicalizationPlan.objects.get(event_candidate=review)

    apply_canonicalization_plan(plan.pk, expected_version=plan.plan_version)

    assert Event.objects.count() == 1
    assert EventObservation.objects.count() == 1
    assert EventRevision.objects.count() == 1


def _update_description_proposal(event_id: int, description: str) -> CanonicalizationProposal:
    return CanonicalizationProposal(
        action=CanonicalizationAction.UPDATE,
        target_event_id=event_id,
        reasoning="The follow-up changes the description.",
        add_event=None,
        event_changes=[
            CanonicalEventFieldChange(
                field=EventField.DESCRIPTION,
                operation=FieldOperation.SET,
                value=description,
            )
        ],
        classification_changes=[],
        organizer_changes=[],
        occurrence_changes=[],
        registration_changes=[],
    )


def _empty_occurrence_value(**overrides) -> CanonicalOccurrenceValue:
    values = {
        "client_ref": None,
        "label": None,
        "sequence": None,
        "start_date": None,
        "start_time": None,
        "end_date": None,
        "end_time": None,
        "time_precision": None,
        "is_all_day": None,
        "attendance_mode": None,
        "raw_location_text": None,
        "meeting_url": None,
        "occurrence_status": None,
        "venue_ids": None,
    }
    values.update(overrides)
    return CanonicalOccurrenceValue.model_validate(values)


def _complete_payload() -> EventCandidatePayload:
    return EventCandidatePayload(
        title="Test event",
        description="Initial event description.",
        occurrences=[
            CandidateOccurrence(
                local_ref="session-1",
                start_date=date(2026, 9, 1),
                start_time=time(19),
                time_precision=TimePrecision.EXACT,
                attendance_mode=AttendanceMode.ONLINE,
                meeting_url="https://example.com/meeting",
            )
        ],
        source_url="https://t.me/test/1",
    )


def _make_candidate(
    payload: EventCandidatePayload,
    *,
    identity: str = "message-1",
) -> EventCandidate:
    now = timezone.now()
    source, _created = Source.objects.get_or_create(
        name="Review source",
        defaults={"source_type": SourceType.PUBLIC_CHANNEL, "adapter_key": "test"},
    )
    representation = SourceRepresentation.objects.create(
        source=source,
        external_identifier=identity,
        source_url=f"https://t.me/test/{identity}",
        first_seen_at=now,
        last_seen_at=now,
    )
    document = RawSourceDocument.objects.create(
        source_representation=representation,
        fetched_at=now,
        storage_key=f"raw/test/{identity}.json",
        content_hash=identity,
        processing_status=ProcessingStatus.PROCESSED,
    )
    extraction = ExtractionRun.objects.create(
        raw_source_document=document,
        extractor_type="test",
        extractor_version="1",
        started_at=now,
        status=ExtractionStatus.SUCCEEDED,
    )
    validation = validate_candidate(payload, build_candidate_reference_data())
    serialized = payload.model_dump(mode="json")
    return EventCandidate.objects.create(
        extraction_run=extraction,
        source_representation=representation,
        candidate_index=0,
        schema_version=payload.schema_version,
        observation_type=payload.observation_type.value,
        extracted_payload=serialized,
        effective_payload=serialized,
        title=payload.title or "",
        status=candidate_status_for_issues(validation.issues),
        validation_issues=validation.issues,
    )


def _canonicalize_new_candidate(candidate: EventCandidate) -> EventCandidate:
    if candidate.status == CandidateStatus.READY:
        canonicalize_candidate(candidate.pk, expected_version=candidate.edit_version)
        candidate.refresh_from_db()
    return candidate
