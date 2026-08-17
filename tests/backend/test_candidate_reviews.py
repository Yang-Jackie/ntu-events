from datetime import date, time

import pytest
from django.utils import timezone
from events.models import (
    Event,
    EventOccurrence,
    EventProvenance,
    PublicationStatus,
    Registration,
    VerificationStatus,
)
from ingestion.candidate_reviews import create_review_and_sync, synchronize_review
from ingestion.contracts import (
    AttendanceMode,
    CandidateOccurrence,
    CandidateRegistration,
    EventCandidatePayload,
    RegistrationScope,
    TimePrecision,
)
from ingestion.models import (
    CandidateReview,
    EventCandidate,
    ExtractionRun,
    ExtractionStatus,
    PromotionMethod,
    ReviewStatus,
    ReviewSyncStatus,
)
from sources.models import (
    ProcessingStatus,
    RawSourceDocument,
    Source,
    SourceRepresentation,
    SourceType,
)

pytestmark = pytest.mark.django_db


def test_complete_candidate_is_automatically_promoted_through_review() -> None:
    candidate = _make_candidate(_complete_payload())

    review = create_review_and_sync(candidate)

    assert CandidateReview.objects.count() == 1
    assert review.review_status == ReviewStatus.NOT_REQUIRED
    assert review.sync_status == ReviewSyncStatus.SYNCED, review.sync_error
    assert review.promotion_method == PromotionMethod.AUTOMATIC
    assert review.synced_version == review.review_version == 1
    event = review.canonical_event
    assert event is not None
    assert event.publication_status == PublicationStatus.DRAFT
    assert event.verification_status == VerificationStatus.AUTOMATICALLY_VERIFIED
    assert event.occurrences.get().meeting_url == "https://example.com/meeting"
    assert event.registrations.get().name == "Register"
    assert EventProvenance.objects.get(event_candidate=candidate).event == event


def test_sparse_candidate_creates_an_unverified_event_and_keeps_review_flags() -> None:
    candidate = _make_candidate(EventCandidatePayload(title="Save the date"))

    review = create_review_and_sync(candidate)

    assert review.review_status == ReviewStatus.NEEDS_REVIEW
    assert review.sync_status == ReviewSyncStatus.SYNCED
    assert {issue["code"] for issue in review.validation_issues} == {"OCCURRENCE_MISSING"}
    assert review.canonical_event is not None
    assert review.canonical_event.verification_status == VerificationStatus.UNVERIFIED
    assert not review.canonical_event.occurrences.exists()


def test_missing_title_blocks_projection_but_not_review_storage() -> None:
    candidate = _make_candidate(EventCandidatePayload())

    review = create_review_and_sync(candidate)

    assert review.sync_status == ReviewSyncStatus.BLOCKED
    assert review.canonical_event is None
    assert review.synced_version == 0
    assert {issue["code"] for issue in review.validation_issues} == {
        "TITLE_MISSING",
        "OCCURRENCE_MISSING",
    }


def test_impossible_business_window_blocks_projection() -> None:
    payload = _complete_payload()
    payload.occurrences[0].end_date = date(2026, 8, 31)

    review = create_review_and_sync(_make_candidate(payload))

    assert review.sync_status == ReviewSyncStatus.BLOCKED
    assert review.canonical_event is None
    assert any(
        issue["code"] == "OCCURRENCE_END_BEFORE_START" and issue["blocks_canonicalization"]
        for issue in review.validation_issues
    )


def test_manual_correction_updates_the_same_event_and_occurrence() -> None:
    review = create_review_and_sync(_make_candidate(_complete_payload()))
    event_id = review.canonical_event_id
    occurrence_id = review.canonical_event.occurrences.get().pk
    payload = EventCandidatePayload.model_validate(review.effective_payload)
    payload.title = "Corrected event title"
    payload.occurrences[0].start_date = date(2026, 9, 2)
    review.effective_payload = payload.model_dump(mode="json")
    review.review_status = ReviewStatus.APPROVED
    review.has_manual_edits = True
    review.review_version += 1
    review.sync_status = ReviewSyncStatus.PENDING
    review.save()

    result = synchronize_review(review.pk, expected_version=review.review_version)

    review.refresh_from_db()
    assert result.sync_status == ReviewSyncStatus.SYNCED
    assert review.canonical_event_id == event_id
    assert review.promotion_method == PromotionMethod.MANUAL
    assert review.canonical_event.title == "Corrected event title"
    assert review.canonical_event.verification_status == VerificationStatus.MANUALLY_VERIFIED
    occurrence = EventOccurrence.objects.get(pk=occurrence_id)
    assert occurrence.start_date == date(2026, 9, 2)


def test_blocking_edit_keeps_last_good_event_projection() -> None:
    review = create_review_and_sync(_make_candidate(_complete_payload()))
    original_event = review.canonical_event
    original_occurrence = original_event.occurrences.get()
    payload = EventCandidatePayload.model_validate(review.effective_payload)
    payload.title = "Should not be projected"
    payload.occurrences[0].end_date = date(2026, 8, 31)
    review.effective_payload = payload.model_dump(mode="json")
    review.review_status = ReviewStatus.NEEDS_REVIEW
    review.has_manual_edits = True
    review.review_version += 1
    review.sync_status = ReviewSyncStatus.PENDING
    review.save()

    synchronize_review(review.pk, expected_version=review.review_version)

    review.refresh_from_db()
    original_event.refresh_from_db()
    original_occurrence.refresh_from_db()
    assert review.sync_status == ReviewSyncStatus.BLOCKED
    assert review.synced_version == 1
    assert original_event.title == "Test event"
    assert original_occurrence.end_date is None


def test_rejecting_a_review_withholds_its_existing_event() -> None:
    review = create_review_and_sync(_make_candidate(_complete_payload()))
    review.review_status = ReviewStatus.REJECTED
    review.has_manual_edits = True
    review.review_version += 1
    review.sync_status = ReviewSyncStatus.PENDING
    review.save()

    synchronize_review(review.pk, expected_version=review.review_version)

    review.refresh_from_db()
    review.canonical_event.refresh_from_db()
    assert review.sync_status == ReviewSyncStatus.SYNCED
    assert review.canonical_event.publication_status == PublicationStatus.WITHHELD
    assert review.canonical_event.verification_status == VerificationStatus.UNVERIFIED


def test_exact_title_duplicate_requires_explicit_separate_event_decision() -> None:
    first = create_review_and_sync(_make_candidate(_complete_payload(), identity="message-1"))
    second = create_review_and_sync(_make_candidate(_complete_payload(), identity="message-2"))

    assert first.canonical_event is not None
    assert second.sync_status == ReviewSyncStatus.BLOCKED
    assert second.canonical_event is None
    assert any(issue["code"] == "POSSIBLE_DUPLICATE_EVENT" for issue in second.validation_issues)

    second.allow_duplicate = True
    second.review_status = ReviewStatus.APPROVED
    second.has_manual_edits = True
    second.review_version += 1
    second.sync_status = ReviewSyncStatus.PENDING
    second.save()
    synchronize_review(second.pk, expected_version=second.review_version)

    second.refresh_from_db()
    assert second.sync_status == ReviewSyncStatus.SYNCED
    assert second.canonical_event is not None
    assert second.canonical_event_id != first.canonical_event_id
    assert Event.objects.filter(normalized_title="test event").count() == 2


def test_repeating_a_synced_version_is_idempotent() -> None:
    review = create_review_and_sync(_make_candidate(_complete_payload()))

    synchronize_review(review.pk, expected_version=review.review_version)

    assert Event.objects.count() == 1
    assert EventOccurrence.objects.count() == 1
    assert Registration.objects.count() == 1


def _complete_payload() -> EventCandidatePayload:
    return EventCandidatePayload(
        title="Test event",
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
        registrations=[
            CandidateRegistration(
                scope=RegistrationScope.EVENT,
                name="Register",
                url="https://example.com/register",
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
        defaults={
            "source_type": SourceType.PUBLIC_CHANNEL,
            "adapter_key": "test",
        },
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
    validation_status = "READY" if payload.title else "REVIEW_REQUIRED"
    return EventCandidate.objects.create(
        extraction_run=extraction,
        source_representation=representation,
        candidate_index=0,
        schema_version=payload.schema_version,
        payload=payload.model_dump(mode="json"),
        title=payload.title or "",
        validation_status=validation_status,
    )
