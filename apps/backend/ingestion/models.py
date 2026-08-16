from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import F, Q


class ExtractionStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    RUNNING = "RUNNING", "Running"
    SUCCEEDED = "SUCCEEDED", "Succeeded"
    FAILED = "FAILED", "Failed"


class ValidationStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    READY = "READY", "Ready"
    REVIEW_REQUIRED = "REVIEW_REQUIRED", "Review required"


class IngestionTrigger(models.TextChoices):
    ADMIN = "ADMIN", "Admin"
    COMMAND = "COMMAND", "Command"
    SCHEDULE = "SCHEDULE", "Schedule"


class JobStatus(models.TextChoices):
    QUEUED = "QUEUED", "Queued"
    RUNNING = "RUNNING", "Running"
    SUCCEEDED = "SUCCEEDED", "Succeeded"
    PARTIAL = "PARTIAL", "Partial"
    FAILED = "FAILED", "Failed"


class ModelInvocationStage(models.TextChoices):
    SCREENING = "SCREENING", "Screening"
    EXTRACTION = "EXTRACTION", "Extraction"


class ScreeningDecision(models.TextChoices):
    EVENT = "EVENT", "Event"
    UNCERTAIN = "UNCERTAIN", "Uncertain"
    NOT_EVENT = "NOT_EVENT", "Not event"
    FAILED = "FAILED", "Failed"


class IngestionRequest(models.Model):
    trigger = models.CharField(max_length=20, choices=IngestionTrigger.choices)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ingestion_requests",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    @property
    def status(self) -> str:
        statuses = set(self.jobs.values_list("status", flat=True))
        if not statuses:
            return JobStatus.SUCCEEDED
        if statuses == {JobStatus.QUEUED}:
            return JobStatus.QUEUED
        if JobStatus.RUNNING in statuses or JobStatus.QUEUED in statuses:
            return JobStatus.RUNNING
        if statuses == {JobStatus.SUCCEEDED}:
            return JobStatus.SUCCEEDED
        if statuses == {JobStatus.FAILED}:
            return JobStatus.FAILED
        return JobStatus.PARTIAL

    def __str__(self) -> str:
        return f"{self.get_trigger_display()} request {self.pk or 'unsaved'}"


class IngestionJob(models.Model):
    request = models.ForeignKey(
        IngestionRequest,
        on_delete=models.PROTECT,
        related_name="jobs",
    )
    source = models.ForeignKey(
        "sources.Source",
        on_delete=models.PROTECT,
        related_name="ingestion_jobs",
    )
    pipeline_key = models.CharField(max_length=100)
    status = models.CharField(
        max_length=20,
        choices=JobStatus.choices,
        default=JobStatus.QUEUED,
        db_index=True,
    )
    options = models.JSONField(default=dict, blank=True)
    available_at = models.DateTimeField(db_index=True)
    claimed_at = models.DateTimeField(null=True, blank=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    worker_id = models.CharField(max_length=255, blank=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    items_discovered = models.PositiveIntegerField(default=0)
    items_screened = models.PositiveIntegerField(default=0)
    items_relevant = models.PositiveIntegerField(default=0)
    items_extracted = models.PositiveIntegerField(default=0)
    candidates_created = models.PositiveIntegerField(default=0)
    failures_count = models.PositiveIntegerField(default=0)
    error_type = models.CharField(max_length=100, blank=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("source",),
                condition=Q(status__in=(JobStatus.QUEUED, JobStatus.RUNNING)),
                name="one_active_ingestion_job_per_source",
            ),
            models.CheckConstraint(
                condition=Q(completed_at__isnull=True) | Q(completed_at__gte=F("claimed_at")),
                name="ingestion_job_completed_not_before_claimed",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.source} — {self.get_status_display()}"


class ModelInvocation(models.Model):
    job = models.ForeignKey(
        IngestionJob,
        on_delete=models.PROTECT,
        related_name="model_invocations",
    )
    stage = models.CharField(max_length=20, choices=ModelInvocationStage.choices)
    provider = models.CharField(max_length=50, default="openai")
    model_name = models.CharField(max_length=100)
    prompt_version = models.CharField(max_length=100)
    schema_version = models.CharField(max_length=100)
    batch_index = models.PositiveIntegerField()
    attempt_number = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(max_length=20, choices=ExtractionStatus.choices)
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    response_identifier = models.CharField(max_length=255, blank=True)
    input_hash = models.CharField(max_length=128, db_index=True)
    reference_data_hash = models.CharField(max_length=64, blank=True, db_index=True)
    reference_data_snapshot = models.JSONField(default=dict, blank=True)
    raw_output_storage_key = models.CharField(max_length=1000, blank=True)
    token_usage = models.JSONField(default=dict, blank=True)
    error_type = models.CharField(max_length=100, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ("job_id", "stage", "batch_index", "attempt_number")
        constraints = [
            models.UniqueConstraint(
                fields=("job", "stage", "batch_index", "attempt_number"),
                name="unique_model_invocation_attempt",
            ),
            models.CheckConstraint(
                condition=Q(completed_at__isnull=True) | Q(completed_at__gte=F("started_at")),
                name="model_invocation_completed_not_before_started",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.stage} batch {self.batch_index} — {self.model_name}"


class MessageScreening(models.Model):
    job = models.ForeignKey(IngestionJob, on_delete=models.PROTECT, related_name="screenings")
    model_invocation = models.ForeignKey(
        ModelInvocation,
        on_delete=models.PROTECT,
        related_name="screenings",
    )
    source_representation = models.ForeignKey(
        "sources.SourceRepresentation",
        on_delete=models.PROTECT,
        related_name="screenings",
    )
    raw_source_document = models.ForeignKey(
        "sources.RawSourceDocument",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="screenings",
    )
    content_hash = models.CharField(max_length=128, db_index=True)
    decision = models.CharField(max_length=20, choices=ScreeningDecision.choices)
    reason = models.CharField(max_length=500, blank=True)
    confidence = models.DecimalField(
        max_digits=4,
        decimal_places=3,
        null=True,
        blank=True,
        validators=(MinValueValidator(0), MaxValueValidator(1)),
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("job_id", "source_representation_id")
        constraints = [
            models.UniqueConstraint(
                fields=("job", "source_representation"),
                name="unique_message_screening_per_job",
            ),
            models.CheckConstraint(
                condition=Q(confidence__isnull=True)
                | (Q(confidence__gte=0) & Q(confidence__lte=1)),
                name="screening_confidence_between_zero_and_one",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.source_representation} — {self.get_decision_display()}"


class ExtractionRun(models.Model):
    model_invocation = models.ForeignKey(
        ModelInvocation,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="extraction_runs",
    )
    raw_source_document = models.ForeignKey(
        "sources.RawSourceDocument",
        on_delete=models.PROTECT,
        related_name="extraction_runs",
    )
    extractor_type = models.CharField(max_length=100)
    extractor_version = models.CharField(max_length=100)
    model_name = models.CharField(max_length=100, blank=True)
    prompt_version = models.CharField(max_length=100, blank=True)
    started_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=ExtractionStatus.choices)
    input_storage_key = models.CharField(max_length=1000, blank=True)
    raw_output_storage_key = models.CharField(max_length=1000, blank=True)
    response_identifier = models.CharField(max_length=255, blank=True)
    token_usage = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ("-started_at",)
        constraints = [
            models.CheckConstraint(
                condition=Q(completed_at__isnull=True) | Q(completed_at__gte=F("started_at")),
                name="extraction_completed_not_before_started",
            )
        ]

    def __str__(self) -> str:
        return f"{self.extractor_type} — {self.started_at:%Y-%m-%d %H:%M}"


class EventCandidate(models.Model):
    extraction_run = models.ForeignKey(
        ExtractionRun,
        on_delete=models.PROTECT,
        related_name="candidates",
    )
    source_representation = models.ForeignKey(
        "sources.SourceRepresentation",
        on_delete=models.PROTECT,
        related_name="event_candidates",
    )
    candidate_index = models.PositiveSmallIntegerField()
    schema_version = models.CharField(max_length=50)
    payload = models.JSONField()
    title = models.CharField(max_length=500, blank=True)
    overall_confidence = models.DecimalField(
        max_digits=4,
        decimal_places=3,
        null=True,
        blank=True,
        validators=(MinValueValidator(0), MaxValueValidator(1)),
    )
    validation_status = models.CharField(
        max_length=30,
        choices=ValidationStatus.choices,
        default=ValidationStatus.PENDING,
    )
    validation_issues = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("extraction_run_id", "candidate_index")
        constraints = [
            models.UniqueConstraint(
                fields=("extraction_run", "candidate_index"),
                name="unique_candidate_index_per_extraction",
            ),
            models.CheckConstraint(
                condition=Q(overall_confidence__isnull=True)
                | (Q(overall_confidence__gte=0) & Q(overall_confidence__lte=1)),
                name="candidate_confidence_between_zero_and_one",
            ),
        ]

    def __str__(self) -> str:
        return self.title or f"Candidate {self.pk or 'unsaved'}"

    def save(self, *args, **kwargs) -> None:
        if self.pk is not None:
            raise ValidationError("Event candidates are immutable; create a review record instead")
        super().save(*args, **kwargs)
