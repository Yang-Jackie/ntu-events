from common.models import TimestampedModel
from django.db import models
from django.db.models import F, Q


class PublicationStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    PENDING_REVIEW = "PENDING_REVIEW", "Pending review"
    PUBLISHED = "PUBLISHED", "Published"
    WITHHELD = "WITHHELD", "Withheld"
    ARCHIVED = "ARCHIVED", "Archived"


class VerificationStatus(models.TextChoices):
    UNVERIFIED = "UNVERIFIED", "Unverified"
    AUTOMATICALLY_VERIFIED = "AUTOMATICALLY_VERIFIED", "Automatically verified"
    MANUALLY_VERIFIED = "MANUALLY_VERIFIED", "Manually verified"
    CONFLICTING = "CONFLICTING", "Conflicting"


class OccurrenceStatus(models.TextChoices):
    SCHEDULED = "SCHEDULED", "Scheduled"
    POSTPONED = "POSTPONED", "Postponed"
    CANCELLED = "CANCELLED", "Cancelled"
    COMPLETED = "COMPLETED", "Completed"


class CapacityStatus(models.TextChoices):
    UNKNOWN = "UNKNOWN", "Unknown"
    AVAILABLE = "AVAILABLE", "Available"
    LIMITED = "LIMITED", "Limited"
    FULL = "FULL", "Full"
    WAITLIST = "WAITLIST", "Waitlist"


class TimePrecision(models.TextChoices):
    EXACT = "EXACT", "Exact"
    APPROXIMATE = "APPROXIMATE", "Approximate"
    DATE_ONLY = "DATE_ONLY", "Date only"
    UNKNOWN = "UNKNOWN", "Unknown"


class RegistrationType(models.TextChoices):
    ATTENDEE = "ATTENDEE", "Attendee"
    VOLUNTEER = "VOLUNTEER", "Volunteer"
    COMPETITOR = "COMPETITOR", "Competitor"
    PRESENTER = "PRESENTER", "Presenter"
    OTHER = "OTHER", "Other"


class RegistrationStatus(models.TextChoices):
    UNKNOWN = "UNKNOWN", "Unknown"
    NOT_OPEN = "NOT_OPEN", "Not open"
    OPEN = "OPEN", "Open"
    CLOSED = "CLOSED", "Closed"
    FULL = "FULL", "Full"
    CANCELLED = "CANCELLED", "Cancelled"


class ClassificationValue(TimestampedModel):
    code = models.CharField(max_length=80, unique=True)
    label = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        abstract = True
        ordering = ("sort_order", "label")

    def __str__(self) -> str:
        return self.label


class EventFormat(ClassificationValue):
    pass


class EventTopic(ClassificationValue):
    pass


class EventPurpose(ClassificationValue):
    pass


class EventAudience(ClassificationValue):
    pass


class EventSeries(TimestampedModel):
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "event series"
        ordering = ("title",)

    def __str__(self) -> str:
        return self.title


class Event(TimestampedModel):
    slug = models.SlugField(max_length=255, unique=True)
    title = models.CharField(max_length=500)
    normalized_title = models.CharField(max_length=500, db_index=True)
    description = models.TextField(blank=True)
    series = models.ForeignKey(
        EventSeries,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )
    publication_status = models.CharField(
        max_length=30,
        choices=PublicationStatus.choices,
        default=PublicationStatus.DRAFT,
    )
    verification_status = models.CharField(
        max_length=30,
        choices=VerificationStatus.choices,
        default=VerificationStatus.UNVERIFIED,
    )
    image_reference = models.CharField(max_length=1000, blank=True)
    audience_notes = models.TextField(blank=True)
    last_verified_at = models.DateTimeField(null=True, blank=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    organizers = models.ManyToManyField(
        "organizers.Organizer",
        through="EventOrganizer",
        related_name="events",
        blank=True,
    )
    formats = models.ManyToManyField(EventFormat, related_name="events", blank=True)
    topics = models.ManyToManyField(EventTopic, related_name="events", blank=True)
    purposes = models.ManyToManyField(EventPurpose, related_name="events", blank=True)
    audiences = models.ManyToManyField(EventAudience, related_name="events", blank=True)

    class Meta:
        ordering = ("title",)

    def __str__(self) -> str:
        return self.title


class EventOrganizer(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE)
    organizer = models.ForeignKey("organizers.Organizer", on_delete=models.PROTECT)
    role = models.CharField(max_length=100, blank=True)
    is_primary = models.BooleanField(default=False)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("position", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("event", "organizer"),
                name="unique_organizer_per_event",
            ),
            models.UniqueConstraint(
                fields=("event",),
                condition=Q(is_primary=True),
                name="one_primary_organizer_per_event",
            ),
        ]


class EventOccurrence(TimestampedModel):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="occurrences")
    label = models.CharField(max_length=255, blank=True)
    sequence = models.PositiveSmallIntegerField()
    start_date = models.DateField()
    start_time = models.TimeField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    time_precision = models.CharField(max_length=20, choices=TimePrecision.choices)
    is_all_day = models.BooleanField(default=False)
    raw_location_text = models.TextField(blank=True)
    occurrence_status = models.CharField(
        max_length=20,
        choices=OccurrenceStatus.choices,
        default=OccurrenceStatus.SCHEDULED,
    )
    capacity_status = models.CharField(
        max_length=20,
        choices=CapacityStatus.choices,
        default=CapacityStatus.UNKNOWN,
    )
    venues = models.ManyToManyField(
        "venues.Venue",
        through="OccurrenceVenue",
        related_name="occurrences",
        blank=True,
    )

    class Meta:
        ordering = ("start_date", "start_time", "sequence")
        constraints = [
            models.UniqueConstraint(
                fields=("event", "sequence"),
                name="unique_occurrence_sequence_per_event",
            ),
            models.CheckConstraint(
                condition=Q(end_date__isnull=True) | Q(end_date__gte=F("start_date")),
                name="occurrence_end_date_not_before_start",
            ),
            models.CheckConstraint(
                condition=Q(end_time__isnull=True) | Q(end_date__isnull=False),
                name="occurrence_end_time_requires_end_date",
            ),
            models.CheckConstraint(
                condition=Q(end_time__isnull=True) | Q(start_time__isnull=False),
                name="occurrence_end_time_requires_start_time",
            ),
            models.CheckConstraint(
                condition=Q(is_all_day=False)
                | (Q(start_time__isnull=True) & Q(end_time__isnull=True)),
                name="all_day_occurrence_has_no_times",
            ),
            models.CheckConstraint(
                condition=Q(end_date__isnull=True)
                | Q(end_date__gt=F("start_date"))
                | Q(end_time__isnull=True)
                | Q(start_time__isnull=True)
                | Q(end_time__gte=F("start_time")),
                name="same_day_occurrence_end_time_not_before_start",
            ),
        ]

    def __str__(self) -> str:
        return self.label or f"{self.event} — {self.start_date}"


class OccurrenceVenue(models.Model):
    occurrence = models.ForeignKey(EventOccurrence, on_delete=models.CASCADE)
    venue = models.ForeignKey("venues.Venue", on_delete=models.PROTECT)
    is_primary = models.BooleanField(default=False)
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ("position", "pk")
        constraints = [
            models.UniqueConstraint(
                fields=("occurrence", "venue"),
                name="unique_venue_per_occurrence",
            ),
            models.UniqueConstraint(
                fields=("occurrence",),
                condition=Q(is_primary=True),
                name="one_primary_venue_per_occurrence",
            ),
        ]


class Registration(TimestampedModel):
    series = models.ForeignKey(
        EventSeries,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="registrations",
    )
    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="registrations",
    )
    occurrence = models.ForeignKey(
        EventOccurrence,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="registrations",
    )
    name = models.CharField(max_length=255)
    registration_type = models.CharField(max_length=20, choices=RegistrationType.choices)
    url = models.URLField(max_length=2000, blank=True)
    opens_date = models.DateField(null=True, blank=True)
    opens_time = models.TimeField(null=True, blank=True)
    closes_date = models.DateField(null=True, blank=True)
    closes_time = models.TimeField(null=True, blank=True)
    time_precision = models.CharField(
        max_length=20,
        choices=TimePrecision.choices,
        default=TimePrecision.UNKNOWN,
    )
    instructions = models.TextField(blank=True)
    status = models.CharField(
        max_length=20,
        choices=RegistrationStatus.choices,
        default=RegistrationStatus.UNKNOWN,
    )

    class Meta:
        ordering = ("name",)
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(series__isnull=False, event__isnull=True, occurrence__isnull=True)
                    | Q(series__isnull=True, event__isnull=False, occurrence__isnull=True)
                    | Q(series__isnull=True, event__isnull=True, occurrence__isnull=False)
                ),
                name="registration_has_exactly_one_owner",
            ),
            models.CheckConstraint(
                condition=Q(opens_time__isnull=True) | Q(opens_date__isnull=False),
                name="registration_open_time_requires_date",
            ),
            models.CheckConstraint(
                condition=Q(closes_time__isnull=True) | Q(closes_date__isnull=False),
                name="registration_close_time_requires_date",
            ),
            models.CheckConstraint(
                condition=Q(closes_date__isnull=True)
                | Q(opens_date__isnull=True)
                | Q(closes_date__gte=F("opens_date")),
                name="registration_close_date_not_before_open",
            ),
            models.CheckConstraint(
                condition=Q(closes_date__isnull=True)
                | Q(opens_date__isnull=True)
                | Q(closes_date__gt=F("opens_date"))
                | Q(closes_time__isnull=True)
                | Q(opens_time__isnull=True)
                | Q(closes_time__gte=F("opens_time")),
                name="same_day_registration_close_not_before_open",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class EventProvenance(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="provenance")
    event_candidate = models.OneToOneField(
        "ingestion.EventCandidate",
        on_delete=models.PROTECT,
        related_name="canonical_provenance",
    )
    source_representation = models.ForeignKey(
        "sources.SourceRepresentation",
        on_delete=models.PROTECT,
        related_name="event_provenance",
    )
    is_primary_source = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("event", "source_representation"),
                name="unique_representation_per_event",
            ),
            models.UniqueConstraint(
                fields=("event",),
                condition=Q(is_primary_source=True),
                name="one_primary_source_per_event",
            ),
        ]
