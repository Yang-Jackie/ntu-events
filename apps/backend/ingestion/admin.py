from django.contrib import admin

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
        "created_at",
    )
    list_filter = ("validation_status", "schema_version")
    search_fields = (
        "title",
        "source_representation__external_identifier",
    )
    readonly_fields = ("created_at",)
