from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from events.models import (
    Event,
    EventOccurrence,
    EventOrganizer,
    EventSourceLink,
    OccurrenceVenue,
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
        representation = link.source_representation
        return representation.source_url or representation.source.base_url


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
