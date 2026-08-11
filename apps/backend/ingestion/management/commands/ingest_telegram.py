from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError, CommandParser
from sources.models import Source

from ingestion.jobs import enqueue_sources
from ingestion.models import IngestionTrigger, JobStatus
from ingestion.worker import WorkerRuntime, make_worker_id


class Command(BaseCommand):
    help = "Queue Telegram ingestion for selected sources."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--source", action="append", type=int, dest="source_ids")
        parser.add_argument("--all-active", action="store_true")
        parser.add_argument("--inline", action="store_true")
        parser.add_argument("--messages", type=int, default=100)
        parser.add_argument("--overlap", type=int, default=20)

    def handle(self, *args, **options) -> None:
        source_ids = options["source_ids"] or []
        if bool(source_ids) == bool(options["all_active"]):
            raise CommandError("Choose either one or more --source values, or --all-active")
        sources = Source.objects.filter(adapter_key="telegram_text")
        if options["all_active"]:
            sources = sources.filter(is_active=True)
        else:
            sources = sources.filter(pk__in=source_ids)
            missing = sorted(set(source_ids) - set(sources.values_list("pk", flat=True)))
            if missing:
                raise CommandError(f"Unknown Telegram source IDs: {missing}")

        try:
            result = enqueue_sources(
                sources,
                trigger=IngestionTrigger.COMMAND,
                options={
                    "message_limit": options["messages"],
                    "overlap": options["overlap"],
                },
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            f"Request {result.request.pk}: queued {len(result.jobs)} job(s), "
            f"skipped {len(result.skipped_sources)} source(s)."
        )
        if not result.jobs:
            return
        if options["inline"]:
            runtime = WorkerRuntime(make_worker_id())
            try:
                for queued in result.jobs:
                    job = runtime.run_specific_job(queued.pk)
                    if job is None:
                        continue
                    job.refresh_from_db()
                    style = (
                        self.style.SUCCESS
                        if job.status == JobStatus.SUCCEEDED
                        else self.style.WARNING
                    )
                    self.stdout.write(style(f"Job {job.pk}: {job.status}"))
            finally:
                runtime.close()
