from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta

from django.contrib.auth.models import AbstractBaseUser
from django.db import IntegrityError, transaction
from django.utils import timezone
from sources.models import Source

from ingestion.models import (
    IngestionJob,
    IngestionRequest,
    IngestionTrigger,
    JobStatus,
)

TELEGRAM_PIPELINE_KEY = "telegram_text"
DEFAULT_JOB_OPTIONS = {
    "message_limit": 100,
    "overlap": 20,
    "screening_batch_size": 20,
    "extraction_batch_size": 5,
    "openai_concurrency": 10,
}


@dataclass(frozen=True)
class EnqueueResult:
    request: IngestionRequest
    jobs: list[IngestionJob]
    skipped_sources: list[Source]


def enqueue_sources(
    sources: Iterable[Source],
    *,
    trigger: str,
    requested_by: AbstractBaseUser | None = None,
    options: dict | None = None,
) -> EnqueueResult:
    selected = list(dict.fromkeys(sources))
    request = IngestionRequest.objects.create(trigger=trigger, requested_by=requested_by)
    jobs: list[IngestionJob] = []
    skipped: list[Source] = []
    job_options = {**DEFAULT_JOB_OPTIONS, **(options or {})}
    for source in selected:
        if not source.is_active or source.adapter_key != TELEGRAM_PIPELINE_KEY:
            skipped.append(source)
            continue
        try:
            with transaction.atomic():
                job = IngestionJob.objects.create(
                    request=request,
                    source=source,
                    pipeline_key=TELEGRAM_PIPELINE_KEY,
                    options=job_options,
                    available_at=timezone.now(),
                )
        except IntegrityError:
            skipped.append(source)
        else:
            jobs.append(job)
    return EnqueueResult(request=request, jobs=jobs, skipped_sources=skipped)


def claim_next_job(worker_id: str) -> IngestionJob | None:
    now = timezone.now()
    with transaction.atomic():
        job = (
            IngestionJob.objects.select_for_update(skip_locked=True)
            .select_related("source", "request")
            .filter(status=JobStatus.QUEUED, available_at__lte=now)
            .order_by("available_at", "created_at")
            .first()
        )
        if job is None:
            return None
        job.status = JobStatus.RUNNING
        job.claimed_at = now
        job.heartbeat_at = now
        job.worker_id = worker_id
        job.attempt_count += 1
        job.error_type = ""
        job.error_message = ""
        job.save(
            update_fields=(
                "status",
                "claimed_at",
                "heartbeat_at",
                "worker_id",
                "attempt_count",
                "error_type",
                "error_message",
            )
        )
        return job


def claim_job(job_id: int, worker_id: str) -> IngestionJob | None:
    now = timezone.now()
    with transaction.atomic():
        job = (
            IngestionJob.objects.select_for_update()
            .select_related("source", "request")
            .filter(pk=job_id, status=JobStatus.QUEUED, available_at__lte=now)
            .first()
        )
        if job is None:
            return None
        job.status = JobStatus.RUNNING
        job.claimed_at = now
        job.heartbeat_at = now
        job.worker_id = worker_id
        job.attempt_count += 1
        job.save(
            update_fields=(
                "status",
                "claimed_at",
                "heartbeat_at",
                "worker_id",
                "attempt_count",
            )
        )
        return job


def recover_stale_jobs(*, stale_after: timedelta = timedelta(minutes=10)) -> int:
    threshold = timezone.now() - stale_after
    return IngestionJob.objects.filter(
        status=JobStatus.RUNNING,
        heartbeat_at__lt=threshold,
    ).update(
        status=JobStatus.QUEUED,
        available_at=timezone.now(),
        worker_id="",
        error_type="WorkerHeartbeatExpired",
        error_message="Recovered after the previous worker stopped updating its heartbeat.",
    )


def default_trigger(value: str) -> str:
    if value not in IngestionTrigger.values:
        raise ValueError(f"Unsupported ingestion trigger: {value}")
    return value
