from datetime import date, time

import pytest
from django.contrib.gis.geos import Point
from django.db import IntegrityError, transaction
from django.utils import timezone
from events.models import (
    Event,
    EventAudience,
    EventFormat,
    EventOccurrence,
    EventProvenance,
    EventPurpose,
    EventSeries,
    EventTopic,
    OccurrenceVenue,
    Registration,
    RegistrationType,
    TimePrecision,
)
from ingestion.models import EventCandidate, ExtractionRun, ExtractionStatus
from sources.models import (
    ProcessingStatus,
    RawSourceDocument,
    Source,
    SourceRepresentation,
    SourceType,
)
from venues.models import Building, CampusArea, Venue, VenueAlias, VenueType

pytestmark = pytest.mark.django_db


def make_event(slug: str = "test-event") -> Event:
    return Event.objects.create(
        slug=slug,
        title="Test Event",
        normalized_title="test event",
    )


def make_occurrence(event: Event, sequence: int = 1) -> EventOccurrence:
    return EventOccurrence.objects.create(
        event=event,
        sequence=sequence,
        start_date=date(2026, 8, 1),
        start_time=time(10),
        end_date=date(2026, 8, 1),
        end_time=time(12),
        time_precision=TimePrecision.EXACT,
    )


def make_candidate() -> tuple[EventCandidate, SourceRepresentation]:
    now = timezone.now()
    source = Source.objects.create(
        name="Test source",
        source_type=SourceType.PUBLIC_CHANNEL,
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
        storage_key="raw/test/message-1.txt",
        content_hash="a" * 64,
        processing_status=ProcessingStatus.PROCESSED,
    )
    extraction = ExtractionRun.objects.create(
        raw_source_document=document,
        extractor_type="test",
        extractor_version="1",
        started_at=now,
        status=ExtractionStatus.SUCCEEDED,
    )
    candidate = EventCandidate.objects.create(
        extraction_run=extraction,
        source_representation=representation,
        candidate_index=0,
        schema_version="1",
        payload={"title": "Test Event"},
        title="Test Event",
    )
    return candidate, representation


def test_building_uses_postgis_point() -> None:
    building = Building.objects.create(
        name="Test Building",
        normalized_name="test building",
        campus_area=CampusArea.MAIN,
        map_point=Point(103.6831, 1.3483, srid=4326),
    )

    building.refresh_from_db()

    assert building.map_point.srid == 4326
    assert building.map_point.x == pytest.approx(103.6831)
    assert building.map_point.y == pytest.approx(1.3483)


@pytest.mark.parametrize("owner_count", [0, 2])
def test_registration_requires_exactly_one_owner(owner_count: int) -> None:
    series = EventSeries.objects.create(title="Test Series")
    event = make_event()

    values = {
        "name": "Attendee registration",
        "registration_type": RegistrationType.ATTENDEE,
    }
    if owner_count == 2:
        values.update({"series": series, "event": event})

    with pytest.raises(IntegrityError), transaction.atomic():
        Registration.objects.create(**values)


def test_registration_accepts_each_owner_scope() -> None:
    series = EventSeries.objects.create(title="Test Series")
    event = make_event()
    occurrence = make_occurrence(event)

    registrations = [
        Registration.objects.create(
            series=series,
            name="Series registration",
            registration_type=RegistrationType.ATTENDEE,
        ),
        Registration.objects.create(
            event=event,
            name="Event registration",
            registration_type=RegistrationType.ATTENDEE,
        ),
        Registration.objects.create(
            occurrence=occurrence,
            name="Occurrence registration",
            registration_type=RegistrationType.ATTENDEE,
        ),
    ]

    assert len(registrations) == 3


def test_occurrence_cannot_end_before_it_starts() -> None:
    event = make_event()

    with pytest.raises(IntegrityError), transaction.atomic():
        EventOccurrence.objects.create(
            event=event,
            sequence=1,
            start_date=date(2026, 8, 2),
            start_time=time(12),
            end_date=date(2026, 8, 2),
            end_time=time(10),
            time_precision=TimePrecision.EXACT,
        )


def test_occurrence_allows_crossing_midnight() -> None:
    event = make_event()

    occurrence = EventOccurrence.objects.create(
        event=event,
        sequence=1,
        start_date=date(2026, 8, 1),
        start_time=time(22),
        end_date=date(2026, 8, 2),
        end_time=time(1),
        time_precision=TimePrecision.EXACT,
    )

    assert occurrence.pk is not None


def test_exact_occurrence_requires_start_time() -> None:
    event = make_event()

    with pytest.raises(IntegrityError), transaction.atomic():
        EventOccurrence.objects.create(
            event=event,
            sequence=1,
            start_date=date(2026, 8, 1),
            time_precision=TimePrecision.EXACT,
        )


def test_date_only_occurrence_rejects_times() -> None:
    event = make_event()

    with pytest.raises(IntegrityError), transaction.atomic():
        EventOccurrence.objects.create(
            event=event,
            sequence=1,
            start_date=date(2026, 8, 1),
            start_time=time(10),
            time_precision=TimePrecision.DATE_ONLY,
        )


def test_occurrence_allows_only_one_primary_venue() -> None:
    event = make_event()
    occurrence = make_occurrence(event)
    first = Venue.objects.create(
        name="Venue One",
        normalized_name="venue one",
        venue_type=VenueType.OTHER,
    )
    second = Venue.objects.create(
        name="Venue Two",
        normalized_name="venue two",
        venue_type=VenueType.OTHER,
    )
    OccurrenceVenue.objects.create(occurrence=occurrence, venue=first, is_primary=True)

    with pytest.raises(IntegrityError), transaction.atomic():
        OccurrenceVenue.objects.create(
            occurrence=occurrence,
            venue=second,
            is_primary=True,
        )


def test_candidate_can_create_at_most_one_event_provenance() -> None:
    candidate, representation = make_candidate()
    first_event = make_event("first-event")
    second_event = make_event("second-event")
    EventProvenance.objects.create(
        event=first_event,
        event_candidate=candidate,
        source_representation=representation,
        is_primary_source=True,
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        EventProvenance.objects.create(
            event=second_event,
            event_candidate=candidate,
            source_representation=representation,
            is_primary_source=True,
        )


def test_candidate_confidence_is_bounded() -> None:
    candidate, _representation = make_candidate()

    with pytest.raises(IntegrityError), transaction.atomic():
        EventCandidate.objects.filter(pk=candidate.pk).update(overall_confidence=1.1)


def test_registration_close_time_cannot_precede_open_time_on_same_day() -> None:
    event = make_event()

    with pytest.raises(IntegrityError), transaction.atomic():
        Registration.objects.create(
            event=event,
            name="Invalid registration window",
            registration_type=RegistrationType.ATTENDEE,
            opens_date=date(2026, 7, 1),
            opens_time=time(12),
            closes_date=date(2026, 7, 1),
            closes_time=time(10),
        )


def test_initial_classification_vocabularies_are_seeded() -> None:
    assert EventFormat.objects.filter(code="WORKSHOP_CLASS").exists()
    assert EventTopic.objects.filter(code="COMPUTING_TECHNOLOGY").exists()
    assert EventPurpose.objects.filter(code="CAREER_RECRUITMENT").exists()
    assert EventAudience.objects.filter(code="ALL_CURRENT_STUDENTS").exists()


def test_core_locations_and_verified_aliases_are_seeded() -> None:
    hive = Building.objects.get(code="LHS")
    building_venue = Venue.objects.get(building=hive, venue_type=VenueType.BUILDING)

    assert hive.map_point is None
    assert hive.official_map_url == "https://maps.ntu.edu.sg/"
    assert VenueAlias.objects.filter(
        venue=building_venue,
        normalized_alias="learning hub south",
        is_verified=True,
    ).exists()
