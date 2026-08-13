from __future__ import annotations

import os
import socket
from collections.abc import Mapping
from uuid import uuid4

from ingestion.errors import RetryableIngestionError, UnsupportedPipelineError
from ingestion.jobs import claim_job, claim_next_job, mark_job_failed, mark_job_for_retry
from ingestion.models import IngestionJob
from ingestion.pipelines.base import IngestionPipeline

MAX_JOB_ATTEMPTS = 3


class WorkerRuntime:
    def __init__(
        self,
        worker_id: str | None = None,
        pipelines: Mapping[str, IngestionPipeline] | None = None,
    ):
        if pipelines is None:
            from ingestion.pipelines.catalog import PIPELINES

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

    def close(self) -> None:
        for pipeline in self.pipelines.values():
            pipeline.close()


def make_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"
