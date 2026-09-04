from __future__ import annotations

import math
from typing import Any

from django.contrib.gis.geos import Polygon
from django.db.models import F, OuterRef, Prefetch, Q, QuerySet, Subquery
from drf_spectacular.utils import extend_schema, extend_schema_field
from rest_framework import generics, serializers
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny

from .models import (
    AttendanceMode,
    Event,
    EventOccurrence,
    EventOrganizer,
    EventSourceLink,
    OccurrenceVenue,
    PublicationStatus,
    Registration,
)


class MapPointSerializer(serializers.Serializer):
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()


class ClassificationSerializer(serializers.Serializer):
    code = serializers.CharField()
    label = serializers.CharField()


class OrganizerSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="organizer_id")
    name = serializers.CharField(source="organizer.name")
    organization_type = serializers.CharField(
        source="organizer.organization_type",
        allow_null=True,
    )
    school_or_unit = serializers.CharField(source="organizer.school_or_unit")
    website_url = serializers.URLField(source="organizer.website_url")
    is_official = serializers.BooleanField(source="organizer.is_official")

    class Meta:
        model = EventOrganizer
        fields = (
            "id",
            "name",
            "organization_type",
            "school_or_unit",
            "website_url",
            "is_official",
            "role",
            "is_primary",
            "position",
        )


class BuildingSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    code = serializers.CharField(allow_null=True)
    name = serializers.CharField()
    campus_area = serializers.CharField()


class OccurrenceVenueSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(source="venue_id")
    name = serializers.CharField(source="venue.name")
    floor = serializers.CharField(source="venue.floor")
    room_code = serializers.CharField(source="venue.room_code")
    venue_type = serializers.CharField(source="venue.venue_type")
    building = BuildingSerializer(source="venue.building", allow_null=True)
    map_point = serializers.SerializerMethodField()

    class Meta:
        model = OccurrenceVenue
        fields = (
            "id",
            "name",
            "floor",
            "room_code",
            "venue_type",
            "building",
            "map_point",
            "is_primary",
            "position",
        )

    @extend_schema_field(MapPointSerializer(allow_null=True))
    def get_map_point(self, relation: OccurrenceVenue) -> dict[str, float] | None:
        point = relation.venue.map_point
        if point is None and relation.venue.building is not None:
            point = relation.venue.building.map_point
        if point is None:
            return None
        return {"latitude": point.y, "longitude": point.x}


class RegistrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Registration
        fields = (
            "id",
            "name",
            "registration_type",
            "url",
            "opens_date",
            "opens_time",
            "closes_date",
            "closes_time",
            "time_precision",
            "instructions",
            "status",
        )


class EventOccurrenceListSerializer(serializers.ModelSerializer):
    venues = OccurrenceVenueSerializer(source="occurrencevenue_set", many=True)

    class Meta:
        model = EventOccurrence
        fields = (
            "id",
            "label",
            "sequence",
            "start_date",
            "start_time",
            "end_date",
            "end_time",
            "time_precision",
            "is_all_day",
            "attendance_mode",
            "raw_location_text",
            "occurrence_status",
            "capacity_status",
            "venues",
        )


class EventOccurrenceDetailSerializer(EventOccurrenceListSerializer):
    registrations = RegistrationSerializer(many=True)

    class Meta(EventOccurrenceListSerializer.Meta):
        fields = EventOccurrenceListSerializer.Meta.fields + (
            "meeting_url",
            "registrations",
        )


class EventListSerializer(serializers.ModelSerializer):
    formats = ClassificationSerializer(many=True)
    topics = ClassificationSerializer(many=True)
    purposes = ClassificationSerializer(many=True)
    audiences = ClassificationSerializer(many=True)
    organizers = OrganizerSerializer(source="eventorganizer_set", many=True)
    occurrences = EventOccurrenceListSerializer(source="api_occurrences", many=True)

    class Meta:
        model = Event
        fields = (
            "id",
            "slug",
            "title",
            "image_reference",
            "verification_status",
            "last_verified_at",
            "updated_at",
            "formats",
            "topics",
            "purposes",
            "audiences",
            "organizers",
            "occurrences",
        )


class EventSourceSerializer(serializers.ModelSerializer):
    source_name = serializers.CharField(source="source_representation.source.name")
    source_type = serializers.CharField(source="source_representation.source.source_type")
    url = serializers.SerializerMethodField()

    class Meta:
        model = EventSourceLink
        fields = ("source_name", "source_type", "url", "is_primary_source")

    @extend_schema_field(serializers.URLField(allow_blank=True))
    def get_url(self, link: EventSourceLink) -> str:
        return link.source_representation.source_url or link.source_representation.source.base_url


class EventDetailSerializer(serializers.ModelSerializer):
    formats = ClassificationSerializer(many=True)
    topics = ClassificationSerializer(many=True)
    purposes = ClassificationSerializer(many=True)
    audiences = ClassificationSerializer(many=True)
    organizers = OrganizerSerializer(source="eventorganizer_set", many=True)
    occurrences = EventOccurrenceDetailSerializer(many=True)
    sources = EventSourceSerializer(source="source_links", many=True)
    registrations = RegistrationSerializer(many=True)

    class Meta:
        model = Event
        fields = (
            "id",
            "slug",
            "title",
            "description",
            "image_reference",
            "audience_notes",
            "publication_status",
            "verification_status",
            "last_verified_at",
            "created_at",
            "updated_at",
            "formats",
            "topics",
            "purposes",
            "audiences",
            "organizers",
            "occurrences",
            "registrations",
            "sources",
        )


class BoundingBoxField(serializers.CharField):
    default_error_messages = {
        "format": "Use four comma-separated numbers: west,south,east,north.",
        "range": "Longitude must be within -180..180 and latitude within -90..90.",
        "order": "The east and north bounds must be greater than west and south.",
    }

    def to_internal_value(self, data: Any) -> tuple[float, float, float, float]:
        value = super().to_internal_value(data)
        parts = [part.strip() for part in value.split(",")]
        if len(parts) != 4:
            self.fail("format")
        try:
            west, south, east, north = (float(part) for part in parts)
        except ValueError:
            self.fail("format")
        if not all(math.isfinite(item) for item in (west, south, east, north)):
            self.fail("range")
        if not (-180 <= west <= 180 and -180 <= east <= 180):
            self.fail("range")
        if not (-90 <= south <= 90 and -90 <= north <= 90):
            self.fail("range")
        if east <= west or north <= south:
            self.fail("order")
        return west, south, east, north


class EventListQuerySerializer(serializers.Serializer):
    q = serializers.CharField(
        required=False,
        allow_blank=False,
        max_length=200,
        help_text="Case-insensitive search across event text and organizer names.",
    )
    date_from = serializers.DateField(
        required=False,
        help_text="Return occurrences whose effective end date is on or after this date.",
    )
    date_to = serializers.DateField(
        required=False,
        help_text="Return occurrences whose start date is on or before this date.",
    )
    attendance_mode = serializers.ChoiceField(
        required=False,
        choices=AttendanceMode.choices,
        help_text="Return occurrences with this attendance mode.",
    )
    format = serializers.CharField(
        required=False,
        allow_blank=False,
        max_length=80,
        help_text="Return events with this format code.",
    )
    topic = serializers.CharField(
        required=False,
        allow_blank=False,
        max_length=80,
        help_text="Return events with this topic code.",
    )
    purpose = serializers.CharField(
        required=False,
        allow_blank=False,
        max_length=80,
        help_text="Return events with this purpose code.",
    )
    audience = serializers.CharField(
        required=False,
        allow_blank=False,
        max_length=80,
        help_text="Return events with this audience code.",
    )
    building = serializers.IntegerField(
        required=False,
        min_value=1,
        help_text="Return occurrences linked to a venue in this building ID.",
    )
    bbox = BoundingBoxField(
        required=False,
        help_text="WGS84 bounds formatted as west,south,east,north.",
    )
    ordering = serializers.ChoiceField(
        required=False,
        choices=("start_date", "-start_date"),
        default="start_date",
        help_text="Order by the earliest or latest matching occurrence date.",
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if attrs.get("date_from") and attrs.get("date_to"):
            if attrs["date_from"] > attrs["date_to"]:
                raise serializers.ValidationError("date_from must not be after date_to.")
        return attrs


class EventPagination(PageNumberPagination):
    page_size = 50


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


class EventListView(generics.ListAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = EventListSerializer
    pagination_class = EventPagination

    @extend_schema(parameters=[EventListQuerySerializer], tags=["events"])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self) -> QuerySet[Event]:
        query = EventListQuerySerializer(data=self.request.query_params)
        query.is_valid(raise_exception=True)
        return _event_list_queryset(query.validated_data)


def _event_list_queryset(filters: dict[str, Any]) -> QuerySet[Event]:
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


class EventDetailView(generics.RetrieveAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = EventDetailSerializer

    @extend_schema(tags=["events"])
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self) -> QuerySet[Event]:
        occurrences = _occurrence_queryset({})
        queryset = Event.objects.filter(publication_status=PublicationStatus.PUBLISHED)
        queryset = _event_relations(queryset).prefetch_related(
            _occurrence_prefetch(occurrences, detailed=True),
            "registrations",
            Prefetch(
                "source_links",
                queryset=EventSourceLink.objects.select_related("source_representation__source"),
            ),
        )
        return queryset
