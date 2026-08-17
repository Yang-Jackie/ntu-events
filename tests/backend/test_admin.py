import json
from datetime import date
from urllib.parse import urlencode

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from events.models import Event, EventOccurrence
from ingestion.candidate_reviews import create_review_and_sync
from ingestion.models import (
    CandidateReview,
    EventCandidate,
    ExtractionRun,
    IngestionJob,
    IngestionRequest,
    MessageScreening,
    ModelInvocation,
)
from organizers.models import Organizer
from sources.models import RawSourceDocument, Source, SourceRepresentation
from venues.models import Building, Venue, VenueAlias

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "model",
    [
        Source,
        SourceRepresentation,
        RawSourceDocument,
        IngestionRequest,
        IngestionJob,
        ModelInvocation,
        MessageScreening,
        ExtractionRun,
        EventCandidate,
        CandidateReview,
        Organizer,
        Building,
        Venue,
        VenueAlias,
        Event,
        EventOccurrence,
    ],
)
def test_core_models_are_registered_in_admin(model) -> None:
    assert admin.site.is_registered(model)


@pytest.mark.parametrize(
    "url_name",
    [
        "admin:sources_source_changelist",
        "admin:ingestion_eventcandidate_changelist",
        "admin:organizers_organizer_changelist",
        "admin:venues_building_changelist",
        "admin:events_event_changelist",
    ],
)
def test_core_admin_change_lists_are_accessible(client, url_name: str) -> None:
    user_model = get_user_model()
    superuser = user_model.objects.create_superuser(
        username=f"admin-{url_name}",
        email="admin@example.com",
        password="test-password",
    )
    client.force_login(superuser)

    response = client.get(reverse(url_name))

    assert response.status_code == 200


def test_candidate_admin_is_read_only_and_presents_payload_summary(client) -> None:
    now = timezone.now()
    source = Source.objects.create(
        name="Candidate source",
        source_type="PUBLIC_CHANNEL",
        adapter_key="test",
    )
    representation = SourceRepresentation.objects.create(
        source=source,
        external_identifier="message-1",
        first_seen_at=now,
        last_seen_at=now,
    )
    document = RawSourceDocument.objects.create(
        source_representation=representation,
        fetched_at=now,
        storage_key="raw/message-1.json",
        content_hash="a" * 64,
        processing_status="PROCESSED",
    )
    extraction = ExtractionRun.objects.create(
        raw_source_document=document,
        extractor_type="test",
        extractor_version="1",
        started_at=now,
        status="SUCCEEDED",
    )
    candidate = EventCandidate.objects.create(
        extraction_run=extraction,
        source_representation=representation,
        candidate_index=0,
        schema_version="event-candidate-v2",
        payload={
            "title": "Online candidate",
            "occurrences": [
                {
                    "start_date": "2026-09-01",
                    "start_time": "19:00:00",
                    "attendance_mode": "ONLINE",
                    "raw_location": None,
                }
            ],
        },
        title="Online candidate",
        validation_status="READY",
    )
    user_model = get_user_model()
    superuser = user_model.objects.create_superuser(
        username="candidate-admin",
        email="admin@example.com",
        password="test-password",
    )
    client.force_login(superuser)

    response = client.get(reverse("admin:ingestion_eventcandidate_change", args=[candidate.pk]))

    assert response.status_code == 200
    assert b"Candidate overview" in response.content
    assert b"Online candidate" in response.content
    assert b'name="_save"' not in response.content


def test_review_admin_correction_synchronizes_existing_event(client) -> None:
    now = timezone.now()
    source = Source.objects.create(
        name="Review Admin source",
        source_type="PUBLIC_CHANNEL",
        adapter_key="test",
    )
    representation = SourceRepresentation.objects.create(
        source=source,
        external_identifier="review-message-1",
        first_seen_at=now,
        last_seen_at=now,
    )
    document = RawSourceDocument.objects.create(
        source_representation=representation,
        fetched_at=now,
        storage_key="raw/review-message-1.json",
        content_hash="b" * 64,
        processing_status="PROCESSED",
    )
    extraction = ExtractionRun.objects.create(
        raw_source_document=document,
        extractor_type="test",
        extractor_version="1",
        started_at=now,
        status="SUCCEEDED",
    )
    candidate = EventCandidate.objects.create(
        extraction_run=extraction,
        source_representation=representation,
        candidate_index=0,
        schema_version="event-candidate-v2",
        payload={
            "schema_version": "event-candidate-v2",
            "title": "Original title",
            "occurrences": [
                {
                    "local_ref": "session-1",
                    "start_date": "2026-09-01",
                    "time_precision": "DATE_ONLY",
                    "attendance_mode": "IN_PERSON",
                    "raw_location": "Location pending review",
                }
            ],
        },
        title="Original title",
        validation_status="REVIEW_REQUIRED",
    )
    review = create_review_and_sync(candidate)
    event_id = review.canonical_event_id
    occurrence_id = review.canonical_event.occurrences.get().pk
    user_model = get_user_model()
    superuser = user_model.objects.create_superuser(
        username="review-admin",
        email="admin@example.com",
        password="test-password",
    )
    client.force_login(superuser)

    protected_event_response = client.get(reverse("admin:events_event_change", args=[event_id]))

    response = client.post(
        reverse("admin:ingestion_candidatereview_change", args=[review.pk]),
        {
            "effective_payload": json.dumps(
                {
                    "schema_version": "event-candidate-v2",
                    "title": "Corrected by reviewer",
                }
            ),
            "review_status": "APPROVED",
            "reviewer_notes": "Title checked against the source.",
            "expected_version": review.review_version,
            "_save": "Save",
        },
    )

    assert protected_event_response.status_code == 200
    assert (
        reverse("admin:events_eventoccurrence_change", args=[occurrence_id]).encode()
        in protected_event_response.content
    )
    assert response.status_code == 302
    review.refresh_from_db()
    assert review.review_version == 2
    assert review.synced_version == 2
    assert review.has_manual_edits is True
    assert review.reviewed_by == superuser
    assert review.canonical_event_id == event_id
    assert review.canonical_event.title == "Corrected by reviewer"


def test_event_admin_links_to_its_occurrences(client) -> None:
    event = Event.objects.create(
        slug="linked-event",
        title="Linked event",
        normalized_title="linked event",
    )
    occurrence = EventOccurrence.objects.create(
        event=event,
        sequence=1,
        start_date=date(2026, 9, 1),
        time_precision="DATE_ONLY",
    )
    user_model = get_user_model()
    superuser = user_model.objects.create_superuser(
        username="event-link-admin",
        email="admin@example.com",
        password="test-password",
    )
    client.force_login(superuser)
    occurrence_url = reverse("admin:events_eventoccurrence_change", args=[occurrence.pk])
    occurrence_list_url = reverse("admin:events_eventoccurrence_changelist")
    filtered_url = f"{occurrence_list_url}?{urlencode({'event__id__exact': event.pk})}"

    event_list_response = client.get(reverse("admin:events_event_changelist"))
    event_detail_response = client.get(reverse("admin:events_event_change", args=[event.pk]))
    filtered_response = client.get(filtered_url)

    assert event_list_response.status_code == 200
    assert filtered_url.encode() in event_list_response.content
    assert b"1 occurrence" in event_list_response.content
    assert event_detail_response.status_code == 200
    assert occurrence_url.encode() in event_detail_response.content
    assert filtered_response.status_code == 200
    assert b"Linked event" in filtered_response.content
