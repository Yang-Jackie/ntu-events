from common.models import TimestampedModel
from django.db import models
from django.db.models import F, Q


class SourceType(models.TextChoices):
    OFFICIAL_WEBSITE = "OFFICIAL_WEBSITE", "Official website"
    FACULTY_WEBSITE = "FACULTY_WEBSITE", "Faculty website"
    STUDENT_ORGANIZATION_WEBSITE = (
        "STUDENT_ORGANIZATION_WEBSITE",
        "Student organization website",
    )
    PUBLIC_SOCIAL_ACCOUNT = "PUBLIC_SOCIAL_ACCOUNT", "Public social account"
    PUBLIC_CHANNEL = "PUBLIC_CHANNEL", "Public channel"
    MANUAL = "MANUAL", "Manual"
    OTHER = "OTHER", "Other"


class RunStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    RUNNING = "RUNNING", "Running"
    SUCCEEDED = "SUCCEEDED", "Succeeded"
    FAILED = "FAILED", "Failed"
    PARTIAL = "PARTIAL", "Partial"


class ProcessingStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    PROCESSING = "PROCESSING", "Processing"
    PROCESSED = "PROCESSED", "Processed"
    FAILED = "FAILED", "Failed"
    SKIPPED = "SKIPPED", "Skipped"


class Source(TimestampedModel):
    name = models.CharField(max_length=255)
    source_type = models.CharField(max_length=40, choices=SourceType.choices)
    base_url = models.URLField(max_length=1000, blank=True)
    organization = models.ForeignKey(
        "organizers.Organizer",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sources",
    )
    is_active = models.BooleanField(default=True)
    crawl_frequency = models.CharField(max_length=100, blank=True)
    last_successful_crawl_at = models.DateTimeField(null=True, blank=True)
    last_failed_crawl_at = models.DateTimeField(null=True, blank=True)
    source_reliability = models.DecimalField(
        max_digits=4,
        decimal_places=3,
        null=True,
        blank=True,
    )
    adapter_key = models.CharField(max_length=100)
    configuration = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.CheckConstraint(
                condition=Q(source_reliability__isnull=True)
                | (Q(source_reliability__gte=0) & Q(source_reliability__lte=1)),
                name="source_reliability_between_zero_and_one",
            )
        ]

    def __str__(self) -> str:
        return self.name


class CrawlRun(models.Model):
    ingestion_job = models.ForeignKey(
        "ingestion.IngestionJob",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="crawl_runs",
    )
    source = models.ForeignKey(Source, on_delete=models.PROTECT, related_name="crawl_runs")
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=RunStatus.choices)
    http_status = models.PositiveSmallIntegerField(null=True, blank=True)
    items_discovered = models.PositiveIntegerField(default=0)
    items_processed = models.PositiveIntegerField(default=0)
    error_type = models.CharField(max_length=100, blank=True)
    error_message = models.TextField(blank=True)
    retry_count = models.PositiveSmallIntegerField(default=0)
    content_hash = models.CharField(max_length=128, blank=True, db_index=True)
    worker_version = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ("-started_at",)
        constraints = [
            models.CheckConstraint(
                condition=Q(completed_at__isnull=True) | Q(completed_at__gte=F("started_at")),
                name="crawl_completed_not_before_started",
            )
        ]

    def __str__(self) -> str:
        return f"{self.source} — {self.started_at:%Y-%m-%d %H:%M}"


class SourceRepresentation(models.Model):
    source = models.ForeignKey(
        Source,
        on_delete=models.PROTECT,
        related_name="representations",
    )
    external_identifier = models.CharField(max_length=512)
    source_url = models.URLField(max_length=2000, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    content_type = models.CharField(max_length=100, blank=True)
    first_seen_at = models.DateTimeField()
    last_seen_at = models.DateTimeField()
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("source_id", "external_identifier")
        constraints = [
            models.UniqueConstraint(
                fields=("source", "external_identifier"),
                name="unique_source_external_identifier",
            ),
            models.CheckConstraint(
                condition=Q(last_seen_at__gte=F("first_seen_at")),
                name="representation_last_seen_not_before_first",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.source}: {self.external_identifier}"


class RawSourceDocument(models.Model):
    source_representation = models.ForeignKey(
        SourceRepresentation,
        on_delete=models.PROTECT,
        related_name="raw_documents",
    )
    crawl_run = models.ForeignKey(
        CrawlRun,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="raw_documents",
    )
    fetched_at = models.DateTimeField()
    storage_key = models.CharField(max_length=1000, unique=True)
    content_hash = models.CharField(max_length=128, db_index=True)
    language = models.CharField(max_length=20, blank=True)
    processing_status = models.CharField(
        max_length=20,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.PENDING,
    )
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ("-fetched_at",)

    def __str__(self) -> str:
        return self.storage_key
