from __future__ import annotations

import time

from django.core.management.base import BaseCommand, CommandParser
from django.db import close_old_connections

from ingestion.jobs import recover_stale_jobs
from ingestion.worker import WorkerRuntime, make_worker_id

STALE_JOB_RECOVERY_INTERVAL_SECONDS = 60.0


def _recover_stale_jobs_if_due(next_recovery_at: float) -> tuple[int | None, float]:
    now = time.monotonic()
    if now < next_recovery_at:
        return None, next_recovery_at
    recovered = recover_stale_jobs()
    return recovered, now + STALE_JOB_RECOVERY_INTERVAL_SECONDS


class Command(BaseCommand):
    help = "Poll PostgreSQL and execute queued ingestion jobs."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--once", action="store_true", help="Claim at most one job, then exit.")
        parser.add_argument("--poll-interval", type=float, default=2.0)

    def handle(self, *args, **options) -> None:
        interval = options["poll_interval"]
        if not 0.1 <= interval <= 60:
            raise ValueError("--poll-interval must be between 0.1 and 60 seconds")
        worker_id = make_worker_id()
        runtime = WorkerRuntime(worker_id)
        recovered, next_recovery_at = _recover_stale_jobs_if_due(0.0)
        self.stdout.write(
            f"Ingestion worker {worker_id} started; recovered {recovered} stale job(s)."
        )
        try:
            while True:
                close_old_connections()
                recovered, next_recovery_at = _recover_stale_jobs_if_due(next_recovery_at)
                if recovered:
                    self.stdout.write(f"Recovered {recovered} stale ingestion job(s).")
                job = runtime.run_next_job()
                if job is not None:
                    job.refresh_from_db()
                    self.stdout.write(f"Job {job.pk} finished with status {job.status}.")
                if options["once"]:
                    return
                if job is None:
                    time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Worker stopped; no new job will be claimed."))
        finally:
            runtime.close()
