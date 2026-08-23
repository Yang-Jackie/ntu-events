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


class CandidateStatus(models.TextChoices):
    BLOCKED = "BLOCKED", "Blocked"
    READY = "READY", "Ready"
    PROCESSED = "PROCESSED", "Processed"


class ObservationType(models.TextChoices):
    EVENT_ANNOUNCEMENT = "EVENT_ANNOUNCEMENT", "Event announcement"
    EVENT_FOLLOW_UP = "EVENT_FOLLOW_UP", "Event follow-up"
    UNKNOWN = "UNKNOWN", "Unknown"


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
    CANONICALIZATION = "CANONICALIZATION", "Canonicalization"


class CanonicalizationAction(models.TextChoices):
    ADD = "ADD", "Add"
    UPDATE = "UPDATE", "Update"
    LINK_ONLY = "LINK_ONLY", "Link only"


class CanonicalizationPlanStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    READY = "READY", "Ready"
    REVIEW_REQUIRED = "REVIEW_REQUIRED", "Review required"
    REJECTED = "REJECTED", "Rejected"
    APPLIED = "APPLIED", "Applied"
    STALE = "STALE", "Stale"
    FAILED = "FAILED", "Failed"


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
    observation_type = models.CharField(
        max_length=30,
        choices=ObservationType.choices,
        default=ObservationType.UNKNOWN,
    )
    extracted_payload = models.JSONField()
    effective_payload = models.JSONField()
    title = models.CharField(max_length=500, blank=True)
    overall_confidence = models.DecimalField(
        max_digits=4,
        decimal_places=3,
        null=True,
        blank=True,
        validators=(MinValueValidator(0), MaxValueValidator(1)),
    )
    status = models.CharField(
        max_length=30,
        choices=CandidateStatus.choices,
        default=CandidateStatus.BLOCKED,
        db_index=True,
    )
    validation_issues = models.JSONField(default=list, blank=True)
    has_manual_edits = models.BooleanField(default=False)
    edit_version = models.PositiveIntegerField(default=1)
    reviewer_notes = models.TextField(blank=True)
    edited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="edited_event_candidates",
    )
    edited_at = models.DateTimeField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

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
            models.CheckConstraint(
                condition=Q(edit_version__gte=1),
                name="event_candidate_edit_version_positive",
            ),
        ]

    def __str__(self) -> str:
        return self.title or f"Candidate {self.pk or 'unsaved'}"

    def save(self, *args, **kwargs) -> None:
        if self.pk is not None:
            original = type(self).objects.get(pk=self.pk)
            immutable_fields = (
                "extraction_run_id",
                "source_representation_id",
                "candidate_index",
                "schema_version",
                "observation_type",
                "extracted_payload",
                "title",
                "overall_confidence",
                "created_at",
            )
            changed = [
                field
                for field in immutable_fields
                if getattr(self, field) != getattr(original, field)
            ]
            if changed:
                raise ValidationError(
                    f"Extracted EventCandidate fields are immutable: {', '.join(changed)}"
                )
            repair_fields = (
                "effective_payload",
                "has_manual_edits",
                "edit_version",
                "reviewer_notes",
                "edited_by_id",
                "edited_at",
            )
            repaired = [
                field for field in repair_fields if getattr(self, field) != getattr(original, field)
            ]
            if repaired and original.status != CandidateStatus.BLOCKED:
                raise ValidationError(
                    "Only BLOCKED EventCandidates may be repaired; edit the canonical Event "
                    "after processing."
                )
        super().save(*args, **kwargs)


class CandidateMatch(models.Model):
    event_candidate = models.ForeignKey(
        EventCandidate,
        on_delete=models.CASCADE,
        related_name="matches",
    )
    event = models.ForeignKey(
        "events.Event",
        on_delete=models.CASCADE,
        related_name="candidate_matches",
    )
    rank = models.PositiveSmallIntegerField()
    score = models.DecimalField(
        max_digits=5,
        decimal_places=4,
        validators=(MinValueValidator(0), MaxValueValidator(1)),
    )
    signals = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("event_candidate_id", "rank")
        constraints = [
            models.UniqueConstraint(
                fields=("event_candidate", "event"),
                name="unique_candidate_match_per_event",
            ),
            models.UniqueConstraint(
                fields=("event_candidate", "rank"),
                name="unique_candidate_match_rank",
            ),
            models.CheckConstraint(
                condition=Q(score__gte=0) & Q(score__lte=1),
                name="candidate_match_score_between_zero_and_one",
            ),
        ]


class CanonicalizationPlan(models.Model):
    event_candidate = models.OneToOneField(
        EventCandidate,
        on_delete=models.PROTECT,
        related_name="canonicalization_plan",
    )
    plan_version = models.PositiveIntegerField(default=1)
    applied_version = models.PositiveIntegerField(default=0)
    action = models.CharField(
        max_length=20,
        choices=CanonicalizationAction.choices,
        blank=True,
    )
    status = models.CharField(
        max_length=30,
        choices=CanonicalizationPlanStatus.choices,
        default=CanonicalizationPlanStatus.PENDING,
        db_index=True,
    )
    target_event = models.ForeignKey(
        "events.Event",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="canonicalization_plans",
    )
    target_event_updated_at = models.DateTimeField(null=True, blank=True)
    target_snapshot_hash = models.CharField(max_length=64, blank=True)
    model_invocation = models.ForeignKey(
        ModelInvocation,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="canonicalization_plans",
    )
    match_snapshot = models.JSONField(default=list)
    generated_proposal = models.JSONField(default=dict)
    effective_proposal = models.JSONField(default=dict)
    validation_issues = models.JSONField(default=list)
    domain_flags = models.JSONField(default=list)
    grounding_flags = models.JSONField(default=list)
    has_manual_edits = models.BooleanField(default=False)
    applied_snapshot = models.JSONField(default=dict)
    application_error = models.TextField(blank=True)
    applied_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at", "-pk")
        constraints = [
            models.CheckConstraint(
                condition=Q(plan_version__gte=1),
                name="canonicalization_plan_version_positive",
            ),
            models.CheckConstraint(
                condition=Q(applied_version__lte=F("plan_version")),
                name="canonicalization_plan_applied_version_not_ahead",
            ),
        ]

    def __str__(self) -> str:
        return f"Plan for {self.event_candidate}"
