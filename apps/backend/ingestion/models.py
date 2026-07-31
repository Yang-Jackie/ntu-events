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
    VALID = "VALID", "Valid"
    INVALID = "INVALID", "Invalid"
    REVIEW_REQUIRED = "REVIEW_REQUIRED", "Review required"


class ExtractionRun(models.Model):
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
    validation_errors = models.JSONField(default=list, blank=True)
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
