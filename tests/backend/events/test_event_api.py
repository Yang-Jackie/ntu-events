from datetime import date, time

import pytest
from django.contrib.gis.geos import Point
from django.utils import timezone
from events.models import (
    AttendanceMode,
    Event,
    EventOccurrence,
    EventOrganizer,
    EventSourceLink,
    EventTopic,
    OccurrenceStatus,
    OccurrenceVenue,
    PublicationStatus,
    Registration,
    RegistrationStatus,
    RegistrationType,
    TimePrecision,
    VerificationStatus,
)
from organizers.models import Organizer
from rest_framework.test import APIClient
from sources.models import Source, SourceRepresentation, SourceType
from venues.models import Building, CampusArea, Venue, VenueType

pytestmark = pytest.mark.django_db


def make_event(
    slug: str,
    *,
    title: str | None = None,
    publication_status: str = PublicationStatus.PUBLISHED,
) -> Event:
    return Event.objects.create(
        slug=slug,
        title=title or slug.replace("-", " ").title(),
        normalized_title=slug.replace("-", " "),
        publication_status=publication_status,
        verification_status=VerificationStatus.UNVERIFIED,
    )


def add_occurrence(
    event: Event,
    *,
    sequence: int,
    start_date: date,
    attendance_mode: str = AttendanceMode.IN_PERSON,
) -> EventOccurrence:
    return EventOccurrence.objects.create(
        event=event,
        sequence=sequence,
        start_date=start_date,
        start_time=time(10),
        end_date=start_date,
        end_time=time(12),
        time_precision=TimePrecision.EXACT,
        attendance_mode=attendance_mode,
        occurrence_status=OccurrenceStatus.SCHEDULED,
    )


def test_event_api_exposes_only_published_events() -> None:
    published = make_event("published-event")
    draft = make_event("draft-event", publication_status=PublicationStatus.DRAFT)
    client = APIClient()

    response = client.get("/api/v1/events/")

    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert [item["id"] for item in response.json()["results"]] == [published.pk]
    assert client.get(f"/api/v1/events/{published.pk}/").status_code == 200
    assert client.get(f"/api/v1/events/{draft.pk}/").status_code == 404


def test_event_detail_contains_discovery_data_and_public_source_links() -> None:
    event = make_event("complete-event", title="Complete event")
    event.description = "A complete event description."
    event.audience_notes = "Open to NTU students."
    event.save()
    topic = EventTopic.objects.create(code="TECH", label="Technology")
    event.topics.add(topic)
    organizer = Organizer.objects.create(
        name="NTU Computing Club",
        normalized_name="ntu computing club",
        organization_type="NTU_STUDENT_ORGANISATION",
        website_url="https://example.com/club",
        is_official=True,
    )
    EventOrganizer.objects.create(
        event=event,
        organizer=organizer,
        role="Host",
        is_primary=True,
        position=0,
    )
    building = Building.objects.create(
        name="API Test Arc",
        code="API-ARC",
        normalized_name="api test arc",
        campus_area=CampusArea.MAIN,
        map_point=Point(103.682, 1.346, srid=4326),
    )
    venue = Venue.objects.create(
        building=building,
        name="Tutorial Room 1",
        normalized_name="tutorial room 1",
        floor="1",
        room_code="TR1",
        venue_type=VenueType.CLASSROOM,
    )
    occurrence = add_occurrence(
        event,
        sequence=1,
        start_date=date(2026, 9, 10),
        attendance_mode=AttendanceMode.HYBRID,
    )
    occurrence.raw_location_text = "The Arc TR1"
    occurrence.meeting_url = "https://meet.example.com/event"
    occurrence.save()
    OccurrenceVenue.objects.create(
        occurrence=occurrence,
        venue=venue,
        is_primary=True,
        position=0,
    )
    Registration.objects.create(
        event=event,
        name="Event registration",
        registration_type=RegistrationType.ATTENDEE,
        url="https://example.com/register",
        time_precision=TimePrecision.DATE_ONLY,
        status=RegistrationStatus.OPEN,
    )
    Registration.objects.create(
        occurrence=occurrence,
        name="Session registration",
        registration_type=RegistrationType.ATTENDEE,
        time_precision=TimePrecision.UNKNOWN,
    )
    source = Source.objects.create(
        name="Public channel",
        source_type=SourceType.PUBLIC_CHANNEL,
        base_url="https://t.me/public_channel",
        adapter_key="telegram_text",
    )
    representation = SourceRepresentation.objects.create(
        source=source,
        external_identifier="42",
        source_url="https://t.me/public_channel/42",
        first_seen_at=timezone.now(),
        last_seen_at=timezone.now(),
    )
    EventSourceLink.objects.create(
        event=event,
        source_representation=representation,
        is_primary_source=True,
    )

    response = APIClient().get(f"/api/v1/events/{event.pk}/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["description"] == "A complete event description."
    assert payload["topics"] == [{"code": "TECH", "label": "Technology"}]
    assert payload["organizers"][0]["name"] == "NTU Computing Club"
    assert payload["registrations"][0]["url"] == "https://example.com/register"
    assert payload["sources"] == [
        {
            "source_name": "Public channel",
            "source_type": "PUBLIC_CHANNEL",
            "url": "https://t.me/public_channel/42",
            "is_primary_source": True,
        }
    ]
    occurrence_payload = payload["occurrences"][0]
    assert occurrence_payload["meeting_url"] == "https://meet.example.com/event"
    assert occurrence_payload["registrations"][0]["name"] == "Session registration"
    assert occurrence_payload["venues"][0]["building"]["code"] == "API-ARC"
    assert occurrence_payload["venues"][0]["map_point"] == {
        "latitude": 1.346,
        "longitude": 103.682,
    }


def test_event_list_filters_matching_occurrences_and_preserves_online_only_default() -> None:
    located = make_event("located-event")
    topic = EventTopic.objects.create(code="CAMPUS", label="Campus life")
    located.topics.add(topic)
    organizer = Organizer.objects.create(
        name="API Test Society",
        normalized_name="api test society",
    )
    EventOrganizer.objects.create(event=located, organizer=organizer, is_primary=True)
    early = add_occurrence(located, sequence=1, start_date=date(2026, 9, 10))
    late = add_occurrence(located, sequence=2, start_date=date(2026, 9, 20))
    building = Building.objects.create(
        name="API Test North Spine",
        code="API-NS",
        normalized_name="api test north spine",
        campus_area=CampusArea.MAIN,
        map_point=Point(103.681, 1.345, srid=4326),
    )
    venue = Venue.objects.create(
        building=building,
        name="North Spine",
        normalized_name="north spine",
        venue_type=VenueType.BUILDING,
    )
    OccurrenceVenue.objects.create(occurrence=early, venue=venue, is_primary=True)
    OccurrenceVenue.objects.create(occurrence=late, venue=venue, is_primary=True)
    online = make_event("online-event")
    add_occurrence(
        online,
        sequence=1,
        start_date=date(2026, 9, 15),
        attendance_mode=AttendanceMode.ONLINE,
    )
    client = APIClient()

    unfiltered = client.get("/api/v1/events/")
    date_filtered = client.get("/api/v1/events/", {"date_from": "2026-09-15"})
    spatial = client.get("/api/v1/events/", {"bbox": "103.67,1.33,103.69,1.36"})
    by_building = client.get("/api/v1/events/", {"building": building.pk})
    by_topic = client.get("/api/v1/events/", {"topic": "CAMPUS"})
    by_organizer = client.get("/api/v1/events/", {"q": "Test Society"})
    online_only = client.get("/api/v1/events/", {"attendance_mode": "ONLINE"})

    assert unfiltered.status_code == 200
    assert {item["id"] for item in unfiltered.json()["results"]} == {located.pk, online.pk}
    located_payload = next(
        item for item in date_filtered.json()["results"] if item["id"] == located.pk
    )
    assert [item["id"] for item in located_payload["occurrences"]] == [late.pk]
    assert [item["id"] for item in spatial.json()["results"]] == [located.pk]
    assert [item["id"] for item in by_building.json()["results"]] == [located.pk]
    assert [item["id"] for item in by_topic.json()["results"]] == [located.pk]
    assert [item["id"] for item in by_organizer.json()["results"]] == [located.pk]
    assert [item["id"] for item in online_only.json()["results"]] == [online.pk]
    assert spatial.json()["results"][0]["occurrences"][0]["venues"][0]["map_point"] == {
        "latitude": 1.345,
        "longitude": 103.681,
    }


def test_event_list_validates_filters_orders_results_and_paginates() -> None:
    first = make_event("first-event")
    add_occurrence(first, sequence=1, start_date=date(2026, 9, 10))
    second = make_event("second-event")
    add_occurrence(second, sequence=1, start_date=date(2026, 9, 20))
    Event.objects.bulk_create(
        [
            Event(
                slug=f"undated-{index:02}",
                title=f"Undated {index:02}",
                normalized_title=f"undated {index:02}",
                publication_status=PublicationStatus.PUBLISHED,
            )
            for index in range(49)
        ]
    )
    client = APIClient()

    descending = client.get("/api/v1/events/", {"ordering": "-start_date"})
    invalid_dates = client.get(
        "/api/v1/events/",
        {"date_from": "2026-09-20", "date_to": "2026-09-10"},
    )
    invalid_bbox = client.get("/api/v1/events/", {"bbox": "not-a-box"})
    non_finite_bbox = client.get("/api/v1/events/", {"bbox": "nan,1,2,3"})

    assert descending.status_code == 200
    assert descending.json()["count"] == 51
    assert len(descending.json()["results"]) == 50
    assert descending.json()["next"] is not None
    assert [item["id"] for item in descending.json()["results"][:2]] == [second.pk, first.pk]
    assert invalid_dates.status_code == 400
    assert invalid_bbox.status_code == 400
    assert non_finite_bbox.status_code == 400
