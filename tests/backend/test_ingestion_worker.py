from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone
from ingestion.jobs import claim_job, enqueue_sources, recover_stale_jobs
from ingestion.management.commands.run_ingestion_worker import (
    STALE_JOB_RECOVERY_INTERVAL_SECONDS,
    _recover_stale_jobs_if_due,
)
from ingestion.models import IngestionTrigger, JobStatus
from sources.models import Source, SourceType


@pytest.mark.django_db
def test_recover_stale_jobs_requeues_only_expired_running_jobs() -> None:
    stale_source = _make_source("stale")
    fresh_source = _make_source("fresh")
    stale_job = _claimed_job(stale_source, "stale-worker")
    fresh_job = _claimed_job(fresh_source, "fresh-worker")
    now = timezone.now()
    stale_job.heartbeat_at = now - timedelta(minutes=11)
    stale_job.save(update_fields=("heartbeat_at",))
    fresh_job.heartbeat_at = now - timedelta(minutes=9)
    fresh_job.save(update_fields=("heartbeat_at",))

    recovered = recover_stale_jobs(stale_after=timedelta(minutes=10))

    stale_job.refresh_from_db()
    fresh_job.refresh_from_db()
    assert recovered == 1
    assert stale_job.status == JobStatus.QUEUED
    assert stale_job.worker_id == ""
    assert stale_job.error_type == "WorkerHeartbeatExpired"
    assert fresh_job.status == JobStatus.RUNNING
    assert fresh_job.worker_id == "fresh-worker"


def test_periodic_stale_recovery_runs_again_after_the_interval() -> None:
    with (
        patch(
            "ingestion.management.commands.run_ingestion_worker.time.monotonic",
            side_effect=(100.0, 159.0, 160.0),
        ),
        patch(
            "ingestion.management.commands.run_ingestion_worker.recover_stale_jobs",
            side_effect=(2, 1),
        ) as recover,
    ):
        first, next_recovery_at = _recover_stale_jobs_if_due(0.0)
        early, unchanged_recovery_at = _recover_stale_jobs_if_due(next_recovery_at)
        second, following_recovery_at = _recover_stale_jobs_if_due(next_recovery_at)

    assert first == 2
    assert next_recovery_at == 100.0 + STALE_JOB_RECOVERY_INTERVAL_SECONDS
    assert early is None
    assert unchanged_recovery_at == next_recovery_at
    assert second == 1
    assert following_recovery_at == 160.0 + STALE_JOB_RECOVERY_INTERVAL_SECONDS
    assert recover.call_count == 2


def _make_source(suffix: str) -> Source:
    return Source.objects.create(
        name=f"Telegram channel {suffix}",
        source_type=SourceType.PUBLIC_CHANNEL,
        adapter_key="telegram_text",
        configuration={"username": f"channel_{suffix}"},
    )


def _claimed_job(source: Source, worker_id: str):
    result = enqueue_sources([source], trigger=IngestionTrigger.COMMAND)
    job = claim_job(result.jobs[0].pk, worker_id)
    assert job is not None
    return job
