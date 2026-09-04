from datetime import date, time

from django.utils import timezone
from ingestion.candidate_validation import validate_candidate
from ingestion.candidates import candidate_status_for_issues
from ingestion.canonicalization import canonicalize_candidate
from ingestion.contracts import (
    AttendanceMode,
    CandidateOccurrence,
    CanonicalEventFieldChange,
    CanonicalizationAction,
    CanonicalizationProposal,
    CanonicalOccurrenceValue,
    EventCandidatePayload,
    EventField,
    FieldOperation,
    TimePrecision,
)
from ingestion.models import CandidateStatus, EventCandidate, ExtractionRun, ExtractionStatus
from ingestion.reference_data import build_candidate_reference_data
from sources.models import (
    ProcessingStatus,
    RawSourceDocument,
    Source,
    SourceRepresentation,
    SourceType,
)


def update_description_proposal(event_id: int, description: str) -> CanonicalizationProposal:
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


def empty_occurrence_value(**overrides) -> CanonicalOccurrenceValue:
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


def complete_payload() -> EventCandidatePayload:
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


def make_candidate(
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


def canonicalize_new_candidate(candidate: EventCandidate) -> EventCandidate:
    if candidate.status == CandidateStatus.READY:
        canonicalize_candidate(candidate.pk, expected_version=candidate.edit_version)
        candidate.refresh_from_db()
    return candidate
