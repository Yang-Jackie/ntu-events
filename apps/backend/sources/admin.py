from django.contrib import admin, messages
from ingestion.jobs import enqueue_sources
from ingestion.models import IngestionTrigger

from .models import CrawlRun, RawSourceDocument, Source, SourceRepresentation


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ("name", "source_type", "adapter_key", "is_active", "updated_at")
    list_filter = ("source_type", "is_active")
    search_fields = ("name", "base_url", "adapter_key")
    actions = ("ingest_selected_sources",)

    @admin.action(description="Ingest selected Telegram sources")
    def ingest_selected_sources(self, request, queryset) -> None:
        result = enqueue_sources(
            queryset,
            trigger=IngestionTrigger.ADMIN,
            requested_by=request.user,
        )
        self.message_user(
            request,
            f"Queued {len(result.jobs)} job(s); skipped {len(result.skipped_sources)} "
            "inactive, incompatible, or already-active source(s).",
            level=messages.SUCCESS if result.jobs else messages.WARNING,
        )


@admin.register(CrawlRun)
class CrawlRunAdmin(admin.ModelAdmin):
    list_display = ("source", "started_at", "status", "items_discovered", "items_processed")
    list_filter = ("status", "source")
    search_fields = ("error_type", "error_message", "content_hash")
    readonly_fields = ("started_at",)


@admin.register(SourceRepresentation)
class SourceRepresentationAdmin(admin.ModelAdmin):
    list_display = ("source", "external_identifier", "published_at", "last_seen_at")
    list_filter = ("source", "content_type")
    search_fields = ("external_identifier", "source_url")


@admin.register(RawSourceDocument)
class RawSourceDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "source_representation",
        "fetched_at",
        "processing_status",
        "content_hash",
    )
    list_filter = ("processing_status", "language")
    search_fields = ("storage_key", "content_hash")
