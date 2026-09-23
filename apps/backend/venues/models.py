from common.models import TimestampedModel
from django.contrib.gis.db import models
from django.db.models import Q


class CampusArea(models.TextChoices):
    MAIN = "MAIN", "Main campus"
    NIE = "NIE", "NIE"
    NOVENA = "NOVENA", "Novena"
    OFF_CAMPUS = "OFF_CAMPUS", "Off campus"


class LocationKind(models.TextChoices):
    COMPLEX = "COMPLEX", "Complex or area"
    BUILDING = "BUILDING", "Building"
    BLOCK = "BLOCK", "Block"
    HALL = "HALL", "Residential hall"
    FACILITY = "FACILITY", "Facility"
    OUTDOOR = "OUTDOOR", "Outdoor place"


class VenueType(models.TextChoices):
    BUILDING = "BUILDING", "Building"
    LECTURE_THEATRE = "LECTURE_THEATRE", "Lecture theatre"
    SEMINAR_ROOM = "SEMINAR_ROOM", "Seminar room"
    CLASSROOM = "CLASSROOM", "Classroom"
    AUDITORIUM = "AUDITORIUM", "Auditorium"
    LABORATORY = "LABORATORY", "Laboratory"
    HALL = "HALL", "Hall"
    SPORTS_FACILITY = "SPORTS_FACILITY", "Sports facility"
    LIBRARY = "LIBRARY", "Library"
    GALLERY = "GALLERY", "Gallery"
    MEETING_ROOM = "MEETING_ROOM", "Meeting room"
    FUNCTION_SPACE = "FUNCTION_SPACE", "Function space"
    TUTORIAL_ROOM = "TUTORIAL_ROOM", "Tutorial room"
    DISCUSSION_ROOM = "DISCUSSION_ROOM", "Discussion room"
    PROJECT_ROOM = "PROJECT_ROOM", "Project room"
    COMPUTING_ROOM = "COMPUTING_ROOM", "Computing room"
    STUDIO = "STUDIO", "Studio"
    OUTDOOR = "OUTDOOR", "Outdoor"
    OTHER = "OTHER", "Other"


class AliasMatchType(models.TextChoices):
    EXACT = "EXACT", "Exact"
    NORMALIZED = "NORMALIZED", "Normalized"
    ABBREVIATION = "ABBREVIATION", "Abbreviation"
    OBSERVED = "OBSERVED", "Observed"


class MapPositioningMethod(models.TextChoices):
    MAPPED_POINT = "MAPPED_POINT", "Mapped point"
    GEOMETRY_CENTER = "GEOMETRY_CENTER", "Geometry centre"
    PARENT_ANCHOR = "PARENT_ANCHOR", "Parent anchor"
    DERIVED_CENTER = "DERIVED_CENTER", "Derived centre"
    TEMPORARY_SITE = "TEMPORARY_SITE", "Temporary site"


class Building(TimestampedModel):
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="child_locations",
    )
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, unique=True, null=True, blank=True)
    normalized_name = models.CharField(max_length=255, unique=True)
    location_kind = models.CharField(
        max_length=20,
        choices=LocationKind.choices,
        default=LocationKind.BUILDING,
    )
    map_point = models.PointField(srid=4326, geography=True, null=True, blank=True)
    address = models.TextField(blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    campus_area = models.CharField(max_length=20, choices=CampusArea.choices)
    official_map_identifier = models.CharField(max_length=255, blank=True)
    official_map_url = models.URLField(max_length=1000, blank=True)
    map_source_identifier = models.CharField(max_length=255, blank=True)
    map_source_url = models.URLField(max_length=1000, blank=True)
    map_positioning_method = models.CharField(
        max_length=30,
        choices=MapPositioningMethod.choices,
        blank=True,
    )
    map_verified_at = models.DateTimeField(null=True, blank=True)
    source_url = models.URLField(max_length=1000, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)

    def __str__(self) -> str:
        return self.name


class Venue(TimestampedModel):
    building = models.ForeignKey(
        Building,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="venues",
    )
    code = models.CharField(max_length=100, unique=True, null=True, blank=True)
    name = models.CharField(max_length=255)
    normalized_name = models.CharField(max_length=255)
    floor = models.CharField(max_length=50, blank=True)
    level_code = models.CharField(max_length=100, blank=True, db_index=True)
    room_code = models.CharField(max_length=100, blank=True, db_index=True)
    venue_type = models.CharField(max_length=30, choices=VenueType.choices)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    map_point = models.PointField(srid=4326, geography=True, null=True, blank=True)
    indoor_map_identifier = models.CharField(max_length=255, blank=True)
    source_url = models.URLField(max_length=1000, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    is_verified = models.BooleanField(default=False)
    bookable_by_staff = models.BooleanField(null=True, blank=True)
    bookable_by_student_organisations = models.BooleanField(null=True, blank=True)

    class Meta:
        ordering = ("building__name", "name")
        constraints = [
            models.UniqueConstraint(
                fields=("building", "normalized_name"),
                name="unique_venue_name_per_building",
            ),
            models.UniqueConstraint(
                fields=("normalized_name",),
                condition=Q(building__isnull=True),
                name="unique_unattached_venue_name",
            ),
        ]

    def __str__(self) -> str:
        if self.building:
            return f"{self.name} — {self.building.name}"
        return self.name


class VenueAlias(models.Model):
    venue = models.ForeignKey(Venue, on_delete=models.PROTECT, related_name="aliases")
    alias = models.CharField(max_length=255)
    normalized_alias = models.CharField(max_length=255, db_index=True)
    match_type = models.CharField(max_length=20, choices=AliasMatchType.choices)
    confidence = models.DecimalField(max_digits=4, decimal_places=3, null=True, blank=True)
    is_verified = models.BooleanField(default=False)
    source_url = models.URLField(max_length=1000, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("normalized_alias",)
        constraints = [
            models.UniqueConstraint(
                fields=("venue", "normalized_alias"),
                name="unique_alias_per_venue",
            ),
            models.CheckConstraint(
                condition=Q(confidence__isnull=True)
                | (Q(confidence__gte=0) & Q(confidence__lte=1)),
                name="venue_alias_confidence_between_zero_and_one",
            ),
            models.UniqueConstraint(
                fields=("normalized_alias",),
                condition=Q(is_verified=True),
                name="unique_verified_venue_alias",
            ),
        ]

    def __str__(self) -> str:
        return self.alias
