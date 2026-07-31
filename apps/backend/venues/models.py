from common.models import TimestampedModel
from django.contrib.gis.db import models
from django.db.models import Q


class CampusArea(models.TextChoices):
    MAIN = "MAIN", "Main campus"
    NIE = "NIE", "NIE"
    NOVENA = "NOVENA", "Novena"
    OFF_CAMPUS = "OFF_CAMPUS", "Off campus"


class VenueType(models.TextChoices):
    BUILDING = "BUILDING", "Building"
    LECTURE_THEATRE = "LECTURE_THEATRE", "Lecture theatre"
    SEMINAR_ROOM = "SEMINAR_ROOM", "Seminar room"
    CLASSROOM = "CLASSROOM", "Classroom"
    AUDITORIUM = "AUDITORIUM", "Auditorium"
    LABORATORY = "LABORATORY", "Laboratory"
    HALL = "HALL", "Hall"
    SPORTS_FACILITY = "SPORTS_FACILITY", "Sports facility"
    OUTDOOR = "OUTDOOR", "Outdoor"
    ONLINE = "ONLINE", "Online"
    OTHER = "OTHER", "Other"


class AliasMatchType(models.TextChoices):
    EXACT = "EXACT", "Exact"
    NORMALIZED = "NORMALIZED", "Normalized"
    ABBREVIATION = "ABBREVIATION", "Abbreviation"
    OBSERVED = "OBSERVED", "Observed"


class Building(TimestampedModel):
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, unique=True, null=True, blank=True)
    normalized_name = models.CharField(max_length=255, unique=True)
    map_point = models.PointField(srid=4326, geography=True, null=True, blank=True)
    address = models.TextField(blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    campus_area = models.CharField(max_length=20, choices=CampusArea.choices)
    official_map_identifier = models.CharField(max_length=255, blank=True)
    official_map_url = models.URLField(max_length=1000, blank=True)
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
    name = models.CharField(max_length=255)
    normalized_name = models.CharField(max_length=255)
    floor = models.CharField(max_length=50, blank=True)
    room_code = models.CharField(max_length=100, blank=True, db_index=True)
    venue_type = models.CharField(max_length=30, choices=VenueType.choices)
    capacity = models.PositiveIntegerField(null=True, blank=True)
    map_point = models.PointField(srid=4326, geography=True, null=True, blank=True)
    indoor_map_identifier = models.CharField(max_length=255, blank=True)
    source_url = models.URLField(max_length=1000, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    is_verified = models.BooleanField(default=False)

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
        ]

    def __str__(self) -> str:
        return self.alias
