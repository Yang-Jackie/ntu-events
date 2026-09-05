from django.contrib import admin, messages

from . import admin_presenters
from .admin_forms import CanonicalizationPlanAdminForm, EventCandidateAdminForm
from .candidates import CandidateVersionConflict, update_event_candidate
from .canonicalization import update_canonicalization_plan
from .models import (
    CandidateMatch,
    CandidateStatus,
    CanonicalizationPlan,
    EventCandidate,
    ExtractionRun,
    IngestionJob,
    IngestionRequest,
    MessageScreening,
    ModelInvocation,
)


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
    form = EventCandidateAdminForm
    list_display = (
        "title",
        "source_representation",
        "schema_version",
        "overall_confidence",
        "status",
        "has_manual_edits",
        "issue_count",
        "created_at",
    )
    list_filter = ("status", "has_manual_edits", "schema_version")
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
        "status",
        "has_manual_edits",
        "edit_version",
        "edited_by",
        "edited_at",
        "processed_at",
        "created_at",
        "updated_at",
    )
    fieldsets = (
        (
            "Candidate",
            {
                "fields": (
                    "candidate_summary",
                    "title",
                    "overall_confidence",
                    "status",
                    "effective_payload",
                    "reviewer_notes",
                    "expected_version",
                )
            },
        ),
        ("Validation issues", {"fields": ("validation_issue_summary",)}),
        (
            "Candidate lifecycle",
            {
                "fields": (
                    "has_manual_edits",
                    "edit_version",
                    "edited_by",
                    "edited_at",
                    "processed_at",
                    "updated_at",
                )
            },
        ),
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

    @admin.display(description="Issues", ordering="status")
    def issue_count(self, obj: EventCandidate) -> int:
        return len(obj.validation_issues)

    @admin.display(description="Candidate overview")
    def candidate_summary(self, obj: EventCandidate) -> str:
        return admin_presenters.payload_summary(obj.effective_payload)

    @admin.display(description="Validation issues")
    def validation_issue_summary(self, obj: EventCandidate) -> str:
        return admin_presenters.validation_issue_summary(obj)

    @admin.display(description="Original extracted payload")
    def raw_payload(self, obj: EventCandidate) -> str:
        return admin_presenters.raw_payload(obj)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return obj is None or obj.status == CandidateStatus.BLOCKED

    def has_delete_permission(self, request, obj=None) -> bool:
        return False

    def save_model(self, request, obj: EventCandidate, form, change: bool) -> None:
        try:
            updated = update_event_candidate(
                obj.pk,
                expected_version=form.cleaned_data["expected_version"],
                effective_payload=form.cleaned_data["effective_payload"],
                reviewer_notes=form.cleaned_data["reviewer_notes"],
                edited_by_id=request.user.pk,
            )
        except CandidateVersionConflict as exc:
            self.message_user(request, str(exc), level=messages.ERROR)
            return
        for field in EventCandidate._meta.concrete_fields:
            setattr(obj, field.attname, getattr(updated, field.attname))
        if updated.status == CandidateStatus.READY:
            self.message_user(request, "Candidate repaired and READY for future processing.")
        else:
            self.message_user(
                request,
                "Candidate remains BLOCKED by validation issues.",
                level=messages.WARNING,
            )


@admin.register(CandidateMatch)
class CandidateMatchAdmin(admin.ModelAdmin):
    list_display = (
        "event_candidate",
        "rank",
        "event",
        "match_percentage",
        "created_at",
    )
    search_fields = ("event_candidate__title", "event__title")
    readonly_fields = [field.name for field in CandidateMatch._meta.fields]

    @admin.display(description="Match")
    def match_percentage(self, obj) -> str:
        return f"{float(obj.score) * 100:.2f}%"

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


@admin.register(CanonicalizationPlan)
class CanonicalizationPlanAdmin(admin.ModelAdmin):
    form = CanonicalizationPlanAdminForm
    list_display = ("event_candidate", "action", "status", "target_event", "updated_at")
    list_filter = ("action", "status", "has_manual_edits")
    search_fields = ("event_candidate__title", "target_event__title", "application_error")
    readonly_fields = (
        "event_candidate",
        "action",
        "status",
        "target_event",
        "model_invocation",
        "match_snapshot",
        "generated_proposal",
        "validation_issues",
        "domain_flags",
        "grounding_flags",
        "has_manual_edits",
        "plan_version",
        "applied_version",
        "applied_snapshot",
        "application_error",
        "applied_at",
        "created_at",
        "updated_at",
    )

    def save_model(self, request, obj, form, change) -> None:
        try:
            updated = update_canonicalization_plan(
                obj.pk,
                expected_version=form.cleaned_data["expected_version"],
                effective_proposal=form.cleaned_data["effective_proposal"],
            )
        except CandidateVersionConflict as exc:
            self.message_user(request, str(exc), level=messages.ERROR)
            return
        for field in CanonicalizationPlan._meta.concrete_fields:
            setattr(obj, field.attname, getattr(updated, field.attname))
        self.message_user(request, f"Plan status: {updated.status}.")

    def has_add_permission(self, request) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
