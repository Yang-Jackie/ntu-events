import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.urls import reverse
from events.models import Event, EventOccurrence, EventSeries
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
        EventSeries,
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
