from django.core.management.base import BaseCommand
from sources.models import Source

from ingestion.jobs import enqueue_sources
from ingestion.models import IngestionTrigger
from ingestion.pipelines.catalog import PIPELINES


class Command(BaseCommand):
    help = "Queue all active supported sources for an external scheduler invocation."

    def handle(self, *args, **options) -> None:
        sources = Source.objects.filter(is_active=True, adapter_key__in=PIPELINES)
        result = enqueue_sources(sources, trigger=IngestionTrigger.SCHEDULE)
        self.stdout.write(
            f"Request {result.request.pk}: queued {len(result.jobs)} job(s), "
            f"skipped {len(result.skipped_sources)} already-active source(s)."
        )
