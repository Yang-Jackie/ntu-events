from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser

from ingestion.jobs.worker import WorkerRuntime, make_worker_id


class Command(BaseCommand):
    help = "Poll PostgreSQL and execute queued ingestion jobs."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--once", action="store_true", help="Claim at most one job, then exit.")
        parser.add_argument("--poll-interval", type=float, default=2.0)

    def handle(self, *args, **options) -> None:
        runtime = WorkerRuntime(make_worker_id())
        try:
            runtime.run(
                once=options["once"],
                poll_interval=options["poll_interval"],
                on_started=lambda worker_id, recovered: self.stdout.write(
                    f"Ingestion worker {worker_id} started; recovered {recovered} stale job(s)."
                ),
                on_recovered=lambda recovered: self.stdout.write(
                    f"Recovered {recovered} stale ingestion job(s)."
                ),
                on_finished=lambda job: self.stdout.write(
                    f"Job {job.pk} finished with status {job.status}."
                ),
            )
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Worker stopped; no new job will be claimed."))
