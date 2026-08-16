import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from events.models import Event, EventOccurrence
from ingestion.models import (
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
