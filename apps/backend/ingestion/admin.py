from django.contrib import admin

from .models import EventCandidate, ExtractionRun


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
