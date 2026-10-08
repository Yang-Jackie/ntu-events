from __future__ import annotations

import os
import socket
import time
from collections.abc import Callable, Mapping
from uuid import uuid4

from django.db import close_old_connections

from ingestion.errors import RetryableIngestionError, UnsupportedPipelineError
from ingestion.jobs.service import (
    claim_job,
    claim_next_job,
    mark_job_failed,
    mark_job_for_retry,
    recover_stale_jobs,
)
from ingestion.models import IngestionJob
from ingestion.observability import log_context, log_event, logged_phase
from ingestion.pipelines.base import IngestionPipeline

MAX_JOB_ATTEMPTS = 3


STALE_JOB_RECOVERY_INTERVAL_SECONDS = 60.0


def _recover_stale_jobs_if_due(next_recovery_at: float) -> tuple[int | None, float]:
    now = time.monotonic()
    if now < next_recovery_at:
        return None, next_recovery_at
    recovered = recover_stale_jobs()
    return recovered, now + STALE_JOB_RECOVERY_INTERVAL_SECONDS


class WorkerRuntime:
    def __init__(
        self,
        worker_id: str | None = None,
        pipelines: Mapping[str, IngestionPipeline] | None = None,
    ):
        if pipelines is None:
            from ingestion.pipelines.registry import PIPELINES

            pipelines = PIPELINES
        self.worker_id = worker_id or make_worker_id()
        self.pipelines = pipelines

    def run_next_job(self) -> IngestionJob | None:
        job = claim_next_job(self.worker_id)
        if job is None:
            return None
        self.run_claimed_job(job)
        return job

    def run_specific_job(self, job_id: int) -> IngestionJob | None:
        job = claim_job(job_id, self.worker_id)
        if job is None:
            return None
        self.run_claimed_job(job)
        return job

    def run_claimed_job(self, job: IngestionJob) -> None:
        try:
            with (
                log_context(job_id=job.pk, source_id=job.source_id, job_attempt=job.attempt_count),
                logged_phase("ingestion.job"),
            ):
                pipeline = self.pipelines.get(job.pipeline_key)
                if pipeline is None:
                    raise UnsupportedPipelineError(job.pipeline_key)
                pipeline.execute(job)
        except RetryableIngestionError as exc:
            if job.attempt_count < MAX_JOB_ATTEMPTS:
                mark_job_for_retry(
                    job,
                    exc,
                    retry_after_seconds=exc.retry_after_seconds,
                )
            else:
                mark_job_failed(job, exc)
        except Exception as exc:
            mark_job_failed(job, exc)
        log_event(
            "ingestion.job_finished",
            job_id=job.pk,
            status=job.status,
            failures_count=job.failures_count,
            error_type=job.error_type or None,
        )

    def run(
        self,
        *,
        once: bool = False,
        poll_interval: float = 2.0,
        on_started: Callable[[str, int], None] | None = None,
        on_recovered: Callable[[int], None] | None = None,
        on_finished: Callable[[IngestionJob], None] | None = None,
    ) -> None:
        """Poll jobs and periodically recover stale claims, closing resources on exit."""
        if not 0.1 <= poll_interval <= 60:
            raise ValueError("--poll-interval must be between 0.1 and 60 seconds")
        try:
            recovered, next_recovery_at = _recover_stale_jobs_if_due(0.0)
            if on_started is not None:
                on_started(self.worker_id, recovered)
            while True:
                close_old_connections()
                recovered, next_recovery_at = _recover_stale_jobs_if_due(next_recovery_at)
                if recovered and on_recovered is not None:
                    on_recovered(recovered)
                job = self.run_next_job()
                if job is not None:
                    job.refresh_from_db()
                    if on_finished is not None:
                        on_finished(job)
                if once:
                    return
                if job is None:
                    time.sleep(poll_interval)
        finally:
            self.close()

    def close(self) -> None:
        for pipeline in self.pipelines.values():
            pipeline.close()


def make_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"
