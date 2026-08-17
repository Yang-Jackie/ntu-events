import json

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from events.models import Event
from pydantic import ValidationError as PydanticValidationError

from .candidate_reviews import ReviewVersionConflict, synchronize_review
from .contracts import EventCandidatePayload
from .models import (
    CandidateReview,
    EventCandidate,
    ExtractionRun,
    IngestionJob,
    IngestionRequest,
    MessageScreening,
    ModelInvocation,
    ReviewStatus,
    ReviewSyncStatus,
)
from .reference_data import build_candidate_reference_data
from .validation import validate_candidate


class CandidateReviewAdminForm(forms.ModelForm):
    expected_version = forms.IntegerField(widget=forms.HiddenInput)

    class Meta:
        model = CandidateReview
        fields = ("effective_payload", "review_status", "allow_duplicate", "reviewer_notes")
        widgets = {"effective_payload": forms.Textarea(attrs={"rows": 32, "cols": 120})}

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["expected_version"].initial = self.instance.review_version

    def clean_effective_payload(self) -> dict:
        value = self.cleaned_data["effective_payload"]
        try:
            EventCandidatePayload.model_validate(value)
        except PydanticValidationError as exc:
            raise forms.ValidationError(
                "The payload does not match the event-candidate schema: "
                f"{exc.errors(include_url=False)}"
            ) from exc
        return value

    def clean(self) -> dict:
        cleaned_data = super().clean()
        if not self.instance.pk or "expected_version" not in cleaned_data:
            return cleaned_data
        current_version = (
            CandidateReview.objects.filter(pk=self.instance.pk)
            .values_list("review_version", flat=True)
            .first()
        )
        if current_version != cleaned_data["expected_version"]:
            raise ValidationError(
                "This review changed after the page was loaded. Reload and retry."
            )

        raw_payload = cleaned_data.get("effective_payload")
        if raw_payload is None:
            return cleaned_data
        payload = EventCandidatePayload.model_validate(raw_payload)
        if (
            "effective_payload" in self.changed_data
            and cleaned_data.get("review_status") == ReviewStatus.NOT_REQUIRED
        ):
            cleaned_data["review_status"] = ReviewStatus.NEEDS_REVIEW
        if cleaned_data.get("review_status") != ReviewStatus.APPROVED:
            return cleaned_data

        validation = validate_candidate(payload, build_candidate_reference_data())
        blockers = [issue for issue in validation.issues if issue.get("blocks_canonicalization")]
        if blockers:
            codes = ", ".join(str(issue["code"]) for issue in blockers)
            raise ValidationError(f"Resolve blocking validation issues before approval: {codes}.")
        if not cleaned_data.get("allow_duplicate") and payload.title:
            normalized_title = " ".join(payload.title.split()).casefold()
            duplicates = Event.objects.filter(normalized_title=normalized_title)
            if self.instance.canonical_event_id:
                duplicates = duplicates.exclude(pk=self.instance.canonical_event_id)
            if duplicates.exists():
                raise ValidationError(
                    "An exact-title event already exists. Confirm 'Allow separate duplicate' "
                    "to approve this as a separate event."
                )
        return cleaned_data


def _payload_summary(payload: object) -> str:
    payload = payload if isinstance(payload, dict) else {}
    lines = [f"Title: {payload.get('title') or 'Unknown'}"]
    description = payload.get("description")
    if description:
        lines.append(f"Description: {description}")
    occurrences = payload.get("occurrences")
    if isinstance(occurrences, list):
        for index, occurrence in enumerate(occurrences, start=1):
            if not isinstance(occurrence, dict):
                continue
            date = occurrence.get("start_date") or "date unknown"
            start_time = occurrence.get("start_time") or "time unknown"
            mode = occurrence.get("attendance_mode") or "mode unknown"
            location = occurrence.get("raw_location") or "no physical location"
            lines.append(f"Occurrence {index}: {date} {start_time}; {mode}; {location}")
    registrations = payload.get("registrations")
    if isinstance(registrations, list) and registrations:
        lines.append(f"Registrations: {len(registrations)}")
    ambiguities = payload.get("ambiguities")
    if isinstance(ambiguities, list) and ambiguities:
        lines.append(f"Ambiguities: {len(ambiguities)}")
    return format_html('<pre style="white-space: pre-wrap">{}</pre>', "\n".join(lines))


class IngestionJobInline(admin.TabularInline):
    model = IngestionJob
    extra = 0
    fields = ("source", "status", "items_discovered", "items_relevant", "candidates_created")
    readonly_fields = fields
    can_delete = False


@admin.register(IngestionRequest)
class IngestionRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "trigger", "status_display", "requested_by", "created_at")
    list_filter = ("trigger",)
    readonly_fields = ("trigger", "requested_by", "created_at", "status_display")
    inlines = (IngestionJobInline,)

    @admin.display(description="Status")
    def status_display(self, obj: IngestionRequest) -> str:
        return obj.status


@admin.register(IngestionJob)
class IngestionJobAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source",
        "status",
        "attempt_count",
        "items_discovered",
        "items_relevant",
        "candidates_created",
        "created_at",
    )
    list_filter = ("status", "pipeline_key", "source")
    search_fields = ("source__name", "worker_id", "error_type", "error_message")
    readonly_fields = (
        "request",
        "source",
        "pipeline_key",
        "status",
        "options",
        "available_at",
        "claimed_at",
        "heartbeat_at",
        "completed_at",
        "worker_id",
        "attempt_count",
        "items_discovered",
        "items_screened",
        "items_relevant",
        "items_extracted",
        "candidates_created",
        "failures_count",
        "error_type",
        "error_message",
        "created_at",
    )


@admin.register(ModelInvocation)
class ModelInvocationAdmin(admin.ModelAdmin):
    list_display = ("job", "stage", "batch_index", "model_name", "status", "started_at")
    list_filter = ("stage", "status", "model_name")
    search_fields = ("response_identifier", "input_hash", "error_message")
    readonly_fields = [field.name for field in ModelInvocation._meta.fields]


@admin.register(MessageScreening)
class MessageScreeningAdmin(admin.ModelAdmin):
    list_display = ("source_representation", "decision", "confidence", "job", "created_at")
    list_filter = ("decision", "job__source")
    search_fields = ("source_representation__external_identifier", "reason", "content_hash")
    readonly_fields = [field.name for field in MessageScreening._meta.fields]


@admin.register(ExtractionRun)
class ExtractionRunAdmin(admin.ModelAdmin):
    list_display = (
        "raw_source_document",
        "extractor_type",
        "extractor_version",
        "model_name",
        "status",
        "started_at",
    )
    list_filter = ("status", "extractor_type", "model_name")
    search_fields = (
        "raw_source_document__storage_key",
        "response_identifier",
        "error_message",
    )


@admin.register(EventCandidate)
class EventCandidateAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "source_representation",
        "schema_version",
        "overall_confidence",
        "validation_status",
        "review_state",
        "issue_count",
        "created_at",
    )
    list_filter = ("validation_status", "schema_version")
    search_fields = (
        "title",
        "source_representation__external_identifier",
    )
    readonly_fields = (
        "candidate_summary",
        "validation_issue_summary",
        "raw_payload",
        "extraction_run",
        "source_representation",
        "candidate_index",
        "schema_version",
        "title",
        "overall_confidence",
        "validation_status",
        "review_link",
        "created_at",
    )
    fieldsets = (
        (
            "Candidate",
            {
                "fields": (
                    "candidate_summary",
                    "title",
                    "overall_confidence",
                    "validation_status",
                    "review_link",
                )
            },
        ),
        ("Validation issues", {"fields": ("validation_issue_summary",)}),
        (
            "Provenance",
            {
                "fields": (
                    "source_representation",
                    "extraction_run",
                    "candidate_index",
                    "schema_version",
                    "created_at",
                )
            },
        ),
        ("Raw payload", {"classes": ("collapse",), "fields": ("raw_payload",)}),
    )

    @admin.display(description="Issues", ordering="validation_status")
    def issue_count(self, obj: EventCandidate) -> int:
        return len(obj.validation_issues)

    @admin.display(description="Review", ordering="review__review_status")
    def review_state(self, obj: EventCandidate) -> str:
        try:
            return obj.review.get_review_status_display()
        except CandidateReview.DoesNotExist:
            return "Missing"

    @admin.display(description="Mutable review")
    def review_link(self, obj: EventCandidate) -> str:
        try:
            review = obj.review
        except CandidateReview.DoesNotExist:
            return "No review record"
        return format_html(
            '<a href="{}">Review and synchronize this candidate</a>',
            reverse("admin:ingestion_candidatereview_change", args=[review.pk]),
        )

    @admin.display(description="Candidate overview")
    def candidate_summary(self, obj: EventCandidate) -> str:
        return _payload_summary(obj.payload)

    @admin.display(description="Validation issues")
    def validation_issue_summary(self, obj: EventCandidate) -> str:
        if not obj.validation_issues:
            return "No validation issues"
        lines = []
        for issue in obj.validation_issues:
            if not isinstance(issue, dict):
                lines.append(str(issue))
                continue
            blocking = "blocking" if issue.get("blocks_canonicalization") else "review"
            lines.append(
                f"[{issue.get('severity', 'WARNING')}/{blocking}] "
                f"{issue.get('code', 'UNKNOWN')} at {issue.get('path', '')}: "
                f"{issue.get('message', '')}"
            )
        return format_html('<pre style="white-space: pre-wrap">{}</pre>', "\n".join(lines))

    @admin.display(description="Original extracted payload")
    def raw_payload(self, obj: EventCandidate) -> str:
        rendered = json.dumps(obj.payload, ensure_ascii=False, indent=2, sort_keys=True)
        return format_html('<pre style="white-space: pre-wrap">{}</pre>', rendered)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(CandidateReview)
class CandidateReviewAdmin(admin.ModelAdmin):
    form = CandidateReviewAdminForm
    list_display = (
        "event_candidate",
        "review_status",
        "sync_status",
        "canonical_event",
        "has_manual_edits",
        "version_state",
        "updated_at",
    )
    list_filter = (
        "review_status",
        "sync_status",
        "promotion_method",
        "has_manual_edits",
        "allow_duplicate",
    )
    search_fields = (
        "event_candidate__title",
        "canonical_event__title",
        "reviewer_notes",
    )
    readonly_fields = (
        "event_candidate",
        "canonical_event",
        "review_summary",
        "validation_issue_summary",
        "sync_status",
        "promotion_method",
        "has_manual_edits",
        "review_version",
        "synced_version",
        "reviewed_by",
        "reviewed_at",
        "last_synced_at",
        "sync_error",
        "created_at",
        "updated_at",
    )
    fieldsets = (
        (
            "Review decision",
            {
                "fields": (
                    "event_candidate",
                    "canonical_event",
                    "review_summary",
                    "effective_payload",
                    "review_status",
                    "allow_duplicate",
                    "reviewer_notes",
                    "expected_version",
                )
            },
        ),
        ("Current validation", {"fields": ("validation_issue_summary",)}),
        (
            "Synchronization",
            {
                "fields": (
                    "sync_status",
                    "promotion_method",
                    "has_manual_edits",
                    "review_version",
                    "synced_version",
                    "sync_error",
                    "last_synced_at",
                )
            },
        ),
        (
            "Review metadata",
            {
                "classes": ("collapse",),
                "fields": ("reviewed_by", "reviewed_at", "created_at", "updated_at"),
            },
        ),
    )

    @admin.display(description="Version")
    def version_state(self, obj: CandidateReview) -> str:
        return f"{obj.synced_version}/{obj.review_version}"

    @admin.display(description="Effective candidate overview")
    def review_summary(self, obj: CandidateReview) -> str:
        return _payload_summary(obj.effective_payload)

    @admin.display(description="Validation issues")
    def validation_issue_summary(self, obj: CandidateReview) -> str:
        if not obj.validation_issues:
            return "No validation issues"
        lines = []
        for issue in obj.validation_issues:
            blocking = "blocking" if issue.get("blocks_canonicalization") else "review"
            lines.append(
                f"[{issue.get('severity', 'WARNING')}/{blocking}] "
                f"{issue.get('code', 'UNKNOWN')} at {issue.get('path', '')}: "
                f"{issue.get('message', '')}"
            )
        return format_html('<pre style="white-space: pre-wrap">{}</pre>', "\n".join(lines))

    def save_model(self, request, obj: CandidateReview, form, change: bool) -> None:
        synchronization_fields = {"effective_payload", "review_status", "allow_duplicate"}
        should_synchronize = bool(synchronization_fields.intersection(form.changed_data))
        if should_synchronize:
            obj.review_version += 1
            obj.sync_status = ReviewSyncStatus.PENDING
            obj.sync_error = ""
            obj.has_manual_edits = True
            if obj.review_status in (ReviewStatus.APPROVED, ReviewStatus.REJECTED):
                obj.reviewed_by = request.user
                obj.reviewed_at = timezone.now()
            else:
                obj.reviewed_by = None
                obj.reviewed_at = None
        super().save_model(request, obj, form, change)
        if not should_synchronize:
            return
        try:
            result = synchronize_review(obj.pk, expected_version=obj.review_version)
        except ReviewVersionConflict as exc:
            self.message_user(request, str(exc), level=messages.ERROR)
            return
        if result.sync_status == ReviewSyncStatus.SYNCED:
            self.message_user(request, "Review synchronized to the canonical event.")
        elif result.sync_status == ReviewSyncStatus.BLOCKED:
            self.message_user(request, result.message, level=messages.WARNING)
        else:
            self.message_user(
                request,
                f"The review was saved but synchronization failed: {result.message}",
                level=messages.ERROR,
            )

    def has_add_permission(self, request) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
