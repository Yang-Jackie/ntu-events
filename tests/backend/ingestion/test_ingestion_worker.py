from datetime import timedelta
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from django.core.management import call_command
from django.utils import timezone
from ingestion.errors import RetryableIngestionError
from ingestion.jobs.service import (
    claim_job,
    complete_job,
    enqueue_sources,
    heartbeat,
    record_job_discovery,
    recover_stale_jobs,
)
from ingestion.jobs.worker import (
    STALE_JOB_RECOVERY_INTERVAL_SECONDS,
    WorkerRuntime,
    _recover_stale_jobs_if_due,
)
from ingestion.models import IngestionTrigger, JobStatus
from sources.models import Source, SourceType


@pytest.mark.parametrize("error", [None, RuntimeError("job failed"), KeyboardInterrupt()])
def test_polling_worker_closes_pipeline_resources_on_exit(monkeypatch, error) -> None:
    pipeline = FakePipeline("test")
    runtime = WorkerRuntime("test-worker", pipelines={pipeline.key: pipeline})
    monkeypatch.setattr("ingestion.jobs.worker.close_old_connections", Mock())
    monkeypatch.setattr("ingestion.jobs.worker.recover_stale_jobs", Mock(return_value=0))
    runtime.run_next_job = Mock(return_value=None, side_effect=error)

    if error is None:
        runtime.run(once=True)
    else:
        with pytest.raises(type(error)):
            runtime.run(once=True)

    assert pipeline.closed


def test_polling_worker_closes_resources_when_initial_recovery_fails(monkeypatch) -> None:
    pipeline = FakePipeline("test")
    runtime = WorkerRuntime("test-worker", pipelines={pipeline.key: pipeline})
    monkeypatch.setattr(
        "ingestion.jobs.worker.recover_stale_jobs",
        Mock(side_effect=RuntimeError("database failed")),
    )
    runtime.run_next_job = Mock()

    with pytest.raises(RuntimeError, match="database failed"):
        runtime.run(once=True)

    assert pipeline.closed
    runtime.run_next_job.assert_not_called()


def test_worker_command_preserves_start_and_completion_output(monkeypatch) -> None:
    output = StringIO()
    job = SimpleNamespace(pk=42, status="SUCCEEDED", refresh_from_db=Mock())
    runtime = WorkerRuntime("test-worker", pipelines={})
    runtime.run_next_job = Mock(return_value=job)
    monkeypatch.setattr(
        "ingestion.management.commands.run_ingestion_worker.WorkerRuntime", lambda _id: runtime
    )
    monkeypatch.setattr("ingestion.jobs.worker.close_old_connections", Mock())
    monkeypatch.setattr("ingestion.jobs.worker.recover_stale_jobs", Mock(return_value=2))

    call_command("run_ingestion_worker", "--once", stdout=output)

    assert output.getvalue().splitlines() == [
        "Ingestion worker test-worker started; recovered 2 stale job(s).",
        "Job 42 finished with status SUCCEEDED.",
    ]


@pytest.mark.django_db
def test_recover_stale_jobs_requeues_only_expired_running_jobs() -> None:
    stale_source = _make_source("stale")
    fresh_source = _make_source("fresh")
    missing_heartbeat_source = _make_source("missing-heartbeat")
    stale_job = _claimed_job(stale_source, "stale-worker")
    fresh_job = _claimed_job(fresh_source, "fresh-worker")
    missing_heartbeat_job = _claimed_job(missing_heartbeat_source, "missing-worker")
    now = timezone.now()
    stale_job.heartbeat_at = now - timedelta(minutes=11)
    stale_job.save(update_fields=("heartbeat_at",))
    fresh_job.heartbeat_at = now - timedelta(minutes=9)
    fresh_job.save(update_fields=("heartbeat_at",))
    missing_heartbeat_job.heartbeat_at = None
    missing_heartbeat_job.save(update_fields=("heartbeat_at",))

    recovered = recover_stale_jobs(stale_after=timedelta(minutes=10))

    stale_job.refresh_from_db()
    fresh_job.refresh_from_db()
    missing_heartbeat_job.refresh_from_db()
    assert recovered == 2
    assert stale_job.status == JobStatus.QUEUED
    assert stale_job.worker_id == ""
    assert stale_job.error_type == "WorkerHeartbeatExpired"
    assert fresh_job.status == JobStatus.RUNNING
    assert fresh_job.worker_id == "fresh-worker"
    assert missing_heartbeat_job.status == JobStatus.QUEUED

    reclaimed = claim_job(missing_heartbeat_job.pk, "replacement-worker")
    assert reclaimed is not None
    assert reclaimed.error_type == ""
    assert reclaimed.error_message == ""


def test_periodic_stale_recovery_runs_again_after_the_interval() -> None:
    with (
        patch(
            "ingestion.jobs.worker.time.monotonic",
            side_effect=(100.0, 159.0, 160.0),
        ),
        patch(
            "ingestion.jobs.worker.recover_stale_jobs",
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


@pytest.mark.django_db
@pytest.mark.parametrize("specific_job", [False, True])
def test_enqueue_and_worker_dispatch_are_pipeline_agnostic(specific_job) -> None:
    source = Source.objects.create(
        name="Structured website",
        source_type=SourceType.OFFICIAL_WEBSITE,
        adapter_key="structured_test",
    )
    pipeline = FakePipeline("structured_test")
    pipelines = {pipeline.key: pipeline}

    result = enqueue_sources(
        [source],
        trigger=IngestionTrigger.COMMAND,
        options={"page_limit": 4},
        pipelines=pipelines,
    )
    runtime = WorkerRuntime("test-worker", pipelines=pipelines)
    job = runtime.run_specific_job(result.jobs[0].pk) if specific_job else runtime.run_next_job()
    runtime.close()

    assert job is not None
    job.refresh_from_db()
    assert job.pipeline_key == "structured_test"
    assert job.options == {"page_limit": 4}
    assert job.status == JobStatus.SUCCEEDED
    assert job.worker_id == "test-worker"
    assert job.attempt_count == 1
    assert job.items_discovered == 4
    assert job.items_screened == 3
    assert job.items_relevant == job.items_extracted == 2
    assert job.candidates_created == 1
    assert job.completed_at == job.heartbeat_at
    assert pipeline.executed_job_ids == [job.pk]
    assert pipeline.closed


@pytest.mark.django_db
def test_enqueue_skips_unsupported_sources_without_validating_their_options() -> None:
    supported = Source.objects.create(
        name="Supported source",
        source_type=SourceType.OFFICIAL_WEBSITE,
        adapter_key="structured_test",
    )
    unsupported = Source.objects.create(
        name="Unsupported source",
        source_type=SourceType.OTHER,
        adapter_key="not_installed",
    )
    pipeline = FakePipeline("structured_test")

    result = enqueue_sources(
        [supported, unsupported],
        trigger=IngestionTrigger.COMMAND,
        options={"page_limit": 2},
        pipelines={pipeline.key: pipeline},
    )

    assert len(result.jobs) == 1
    assert result.jobs[0].source == supported
    assert result.skipped_sources == [unsupported]


@pytest.mark.django_db
def test_unknown_pipeline_fails_one_job_without_raising_from_runtime() -> None:
    source = _make_source("unsupported-runtime")
    pipeline = FakePipeline("telegram_text")
    result = enqueue_sources(
        [source],
        trigger=IngestionTrigger.COMMAND,
        pipelines={pipeline.key: pipeline},
    )
    queued = result.jobs[0]
    queued.pipeline_key = "removed_pipeline"
    queued.save(update_fields=("pipeline_key",))

    runtime = WorkerRuntime("test-worker", pipelines={})
    job = runtime.run_specific_job(queued.pk)

    assert job is not None
    job.refresh_from_db()
    assert job.status == JobStatus.FAILED
    assert job.error_type == "UnsupportedPipelineError"


@pytest.mark.django_db
def test_generic_retryable_error_requeues_job() -> None:
    source = _make_source("retryable")
    pipeline = FakePipeline("telegram_text", retry=True)
    result = enqueue_sources(
        [source],
        trigger=IngestionTrigger.COMMAND,
        pipelines={pipeline.key: pipeline},
    )

    runtime = WorkerRuntime("test-worker", pipelines={pipeline.key: pipeline})
    job = runtime.run_specific_job(result.jobs[0].pk)

    assert job is not None
    job.refresh_from_db()
    assert job.status == JobStatus.QUEUED
    assert job.error_type == "RetryableIngestionError"
    assert job.available_at > timezone.now()


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


class FakePipeline:
    def __init__(self, key: str, *, retry: bool = False):
        self.key = key
        self.retry = retry
        self.executed_job_ids: list[int] = []
        self.closed = False

    def normalize_options(self, options: dict | None) -> dict:
        return options or {"page_limit": 1}

    def execute(self, job) -> None:
        self.executed_job_ids.append(job.pk)
        if self.retry:
            raise RetryableIngestionError("try again", retry_after_seconds=30)
        record_job_discovery(job, items_discovered=4)
        heartbeat(job)
        complete_job(
            job,
            items_screened=3,
            items_relevant=2,
            items_extracted=2,
            candidates_created=1,
            failures_count=0,
        )

    def close(self) -> None:
        self.closed = True
