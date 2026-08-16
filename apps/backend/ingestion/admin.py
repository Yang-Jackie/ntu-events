import json

from django.contrib import admin
from django.utils.html import format_html

from .models import (
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
    list_display = (
        "title",
        "source_representation",
        "schema_version",
        "overall_confidence",
        "validation_status",
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

    @admin.display(description="Candidate overview")
    def candidate_summary(self, obj: EventCandidate) -> str:
        payload = obj.payload if isinstance(obj.payload, dict) else {}
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
