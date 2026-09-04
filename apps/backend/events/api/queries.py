from __future__ import annotations

from typing import Any

from django.contrib.gis.geos import Polygon
from django.db.models import F, OuterRef, Prefetch, Q, QuerySet, Subquery

from events.models import (
    Event,
    EventOccurrence,
    EventOrganizer,
    EventSourceLink,
    OccurrenceVenue,
    PublicationStatus,
)


def _occurrence_queryset(filters: dict[str, Any]) -> QuerySet[EventOccurrence]:
    queryset = EventOccurrence.objects.all()
    if date_from := filters.get("date_from"):
        queryset = queryset.filter(
            Q(end_date__gte=date_from) | Q(end_date__isnull=True, start_date__gte=date_from)
        )
    if date_to := filters.get("date_to"):
        queryset = queryset.filter(start_date__lte=date_to)
    if attendance_mode := filters.get("attendance_mode"):
        queryset = queryset.filter(attendance_mode=attendance_mode)
    if building_id := filters.get("building"):
        queryset = queryset.filter(venues__building_id=building_id)
    if bbox := filters.get("bbox"):
        bounds = Polygon.from_bbox(bbox)
        bounds.srid = 4326
        queryset = queryset.filter(
            Q(venues__map_point__within=bounds)
            | Q(venues__map_point__isnull=True, venues__building__map_point__within=bounds)
        )
    return queryset.distinct()


def _occurrence_prefetch(queryset: QuerySet[EventOccurrence], *, detailed: bool) -> Prefetch:
    queryset = queryset.prefetch_related(
        Prefetch(
            "occurrencevenue_set",
            queryset=OccurrenceVenue.objects.select_related("venue__building"),
        )
    ).order_by("start_date", "start_time", "sequence", "pk")
    if detailed:
        queryset = queryset.prefetch_related("registrations")
    return Prefetch(
        "occurrences", queryset=queryset, to_attr=None if detailed else "api_occurrences"
    )


def _event_relations(queryset: QuerySet[Event]) -> QuerySet[Event]:
    return queryset.prefetch_related(
        "formats",
        "topics",
        "purposes",
        "audiences",
        Prefetch(
            "eventorganizer_set",
            queryset=EventOrganizer.objects.select_related("organizer"),
        ),
    )


def event_list_queryset(filters: dict[str, Any]) -> QuerySet[Event]:
    matching_occurrences = _occurrence_queryset(filters)

    queryset = Event.objects.filter(publication_status=PublicationStatus.PUBLISHED)
    if search := filters.get("q"):
        queryset = queryset.filter(
            Q(title__icontains=search)
            | Q(description__icontains=search)
            | Q(audience_notes__icontains=search)
            | Q(eventorganizer__organizer__name__icontains=search)
        )
    for parameter, relation in (
        ("format", "formats"),
        ("topic", "topics"),
        ("purpose", "purposes"),
        ("audience", "audiences"),
    ):
        if code := filters.get(parameter):
            queryset = queryset.filter(**{f"{relation}__code": code})

    occurrence_filters = ("date_from", "date_to", "attendance_mode", "building", "bbox")
    if any(parameter in filters for parameter in occurrence_filters):
        queryset = queryset.filter(occurrences__pk__in=matching_occurrences.values("pk"))

    descending = filters["ordering"] == "-start_date"
    ordered_occurrences = matching_occurrences.filter(event_id=OuterRef("pk")).order_by(
        "-start_date" if descending else "start_date",
        "-start_time" if descending else "start_time",
        "-sequence" if descending else "sequence",
        "-pk" if descending else "pk",
    )
    queryset = queryset.annotate(
        api_order_date=Subquery(ordered_occurrences.values("start_date")[:1]),
        api_order_time=Subquery(ordered_occurrences.values("start_time")[:1]),
    )
    direction = "desc" if descending else "asc"
    queryset = queryset.order_by(
        getattr(F("api_order_date"), direction)(nulls_last=True),
        getattr(F("api_order_time"), direction)(nulls_last=True),
        "title",
        "pk",
    ).distinct()
    queryset = _event_relations(queryset)
    return queryset.prefetch_related(_occurrence_prefetch(matching_occurrences, detailed=False))


def event_detail_queryset() -> QuerySet[Event]:
    occurrences = _occurrence_queryset({})
    queryset = Event.objects.filter(publication_status=PublicationStatus.PUBLISHED)
    return _event_relations(queryset).prefetch_related(
        _occurrence_prefetch(occurrences, detailed=True),
        "registrations",
        Prefetch(
            "source_links",
            queryset=EventSourceLink.objects.select_related("source_representation__source"),
        ),
    )
