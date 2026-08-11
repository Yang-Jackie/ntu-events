from __future__ import annotations

import os
import socket
from uuid import uuid4

from ingestion.adapters.telegram import TelegramRetryableError
from ingestion.jobs import claim_job, claim_next_job
from ingestion.models import IngestionJob
from ingestion.telegram_workflow import (
    configured_models,
    execute_telegram_job,
    mark_job_failed,
    mark_job_for_retry,
)

MAX_JOB_ATTEMPTS = 3


class WorkerRuntime:
    def __init__(self, worker_id: str | None = None):
        self.worker_id = worker_id or make_worker_id()
        self.models = None

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
            if self.models is None:
                self.models = configured_models()
            execute_telegram_job(job, models=self.models)
        except TelegramRetryableError as exc:
            if job.attempt_count < MAX_JOB_ATTEMPTS:
                mark_job_for_retry(job, exc)
            else:
                mark_job_failed(job, exc)
        except Exception as exc:
            mark_job_failed(job, exc)

    def close(self) -> None:
        if self.models is not None:
            self.models.close()
            self.models = None


def make_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid4().hex[:8]}"


def run_next_job(worker_id: str) -> IngestionJob | None:
    runtime = WorkerRuntime(worker_id)
    try:
        return runtime.run_next_job()
    finally:
        runtime.close()


def run_specific_job(job_id: int, worker_id: str) -> IngestionJob | None:
    runtime = WorkerRuntime(worker_id)
    try:
        return runtime.run_specific_job(job_id)
    finally:
        runtime.close()


def run_claimed_job(job: IngestionJob) -> None:
    runtime = WorkerRuntime(job.worker_id or make_worker_id())
    try:
        runtime.run_claimed_job(job)
    finally:
        runtime.close()
