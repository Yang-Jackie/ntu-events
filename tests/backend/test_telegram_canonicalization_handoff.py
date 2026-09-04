from unittest.mock import Mock

import pytest
from events.models import Event
from ingestion.candidates import update_event_candidate
from ingestion.canonicalization.worker import CanonicalizationWorkerRuntime
from ingestion.jobs import claim_job, enqueue_sources
from ingestion.models import (
    CandidateStatus,
    EventCandidate,
    IngestionJob,
    IngestionTrigger,
    JobStatus,
    ModelInvocation,
)
from ingestion.pipelines.telegram.pipeline import TelegramTextPipeline
from ingestion.raw_storage import LocalRawContentStorage
from ingestion.reference_data import build_candidate_reference_data

from .telegram_job_test_support import (
    BusinessIssueModels,
    ConcurrentEventEditModels,
    FakeFetcher,
    FakeModels,
    fixture_messages,
    make_source,
)

pytestmark = pytest.mark.django_db


def test_canonicalization_worker_processes_ready_candidates_after_ingestion(tmp_path) -> None:
    source = make_source()
    enqueue = enqueue_sources([source], trigger=IngestionTrigger.COMMAND)
    job = claim_job(enqueue.jobs[0].pk, "ingestion-worker")
    assert job is not None
    models = FakeModels()
    storage = LocalRawContentStorage(tmp_path)

    TelegramTextPipeline(
        fetcher=FakeFetcher(fixture_messages()),
        models=models,
        storage=storage,
    ).execute(job)
    job.refresh_from_db()
    assert job.status == JobStatus.SUCCEEDED
    assert EventCandidate.objects.filter(status=CandidateStatus.READY).count() == 12
    IngestionJob.objects.filter(pk=job.pk).update(attempt_count=7)

    runtime = CanonicalizationWorkerRuntime(decision_provider=models, storage=storage)
    processed = 0
    while runtime.run_next_candidate() is not None:
        processed += 1

    job.refresh_from_db()
    assert processed == 12
    assert EventCandidate.objects.filter(status=CandidateStatus.PROCESSED).count() == 12
    assert ModelInvocation.objects.filter(stage="CANONICALIZATION").count() == 11
    assert {
        invocation.attempt_number
        for invocation in ModelInvocation.objects.filter(stage="CANONICALIZATION")
    } == {1}
    assert models.canonicalization_contexts
    assert models.canonicalization_contexts[0]["raw_document"]["text"]
    assert job.status == JobStatus.SUCCEEDED


def test_unexpected_canonicalization_failure_leaves_candidate_ready(tmp_path) -> None:
    source = make_source()
    enqueue = enqueue_sources([source], trigger=IngestionTrigger.COMMAND)
    job = claim_job(enqueue.jobs[0].pk, "ingestion-worker")
    assert job is not None
    models = FakeModels()
    storage = LocalRawContentStorage(tmp_path)
    TelegramTextPipeline(
        fetcher=FakeFetcher(fixture_messages()[:2]),
        models=models,
        storage=storage,
    ).execute(job)
    runtime = CanonicalizationWorkerRuntime(decision_provider=models, storage=storage)
    assert runtime.run_next_candidate() is not None
    candidate = EventCandidate.objects.get(
        candidate_index=0,
        extraction_run__raw_source_document__source_representation__external_identifier="2",
    )
    original_issues = [
        {
            "code": "SOURCE_AMBIGUITY",
            "path": "ambiguities",
            "message": "Preserve this candidate issue.",
            "severity": "WARNING",
            "blocks_canonicalization": False,
        }
    ]
    EventCandidate.objects.filter(pk=candidate.pk).update(validation_issues=original_issues)
    models.decide = Mock(side_effect=RuntimeError("unexpected canonicalization failure"))

    with pytest.raises(RuntimeError, match="unexpected canonicalization failure"):
        runtime.run_next_candidate()

    candidate.refresh_from_db()
    assert candidate.status == CandidateStatus.READY
    assert candidate.validation_issues == original_issues
    assert not hasattr(candidate, "canonicalization_plan")
    invocation = ModelInvocation.objects.get(stage="CANONICALIZATION")
    assert invocation.status == "FAILED"
    assert invocation.error_type == "RuntimeError"


def test_pre_invocation_canonicalization_failure_propagates_and_leaves_candidate_ready(
    tmp_path,
) -> None:
    source = make_source()
    enqueue = enqueue_sources([source], trigger=IngestionTrigger.COMMAND)
    job = claim_job(enqueue.jobs[0].pk, "ingestion-worker")
    assert job is not None
    models = FakeModels()
    storage = LocalRawContentStorage(tmp_path)
    TelegramTextPipeline(
        fetcher=FakeFetcher(fixture_messages()[:2]),
        models=models,
        storage=storage,
    ).execute(job)
    runtime = CanonicalizationWorkerRuntime(decision_provider=models, storage=storage)
    assert runtime.run_next_candidate() is not None
    candidate = EventCandidate.objects.get(
        candidate_index=0,
        extraction_run__raw_source_document__source_representation__external_identifier="2",
    )
    broken_storage = Mock()
    broken_storage.load.side_effect = OSError("raw evidence unavailable")
    runtime = CanonicalizationWorkerRuntime(
        decision_provider=models,
        storage=broken_storage,
    )

    with pytest.raises(OSError, match="raw evidence unavailable"):
        runtime.run_next_candidate()

    candidate.refresh_from_db()
    assert candidate.status == CandidateStatus.READY
    assert not hasattr(candidate, "canonicalization_plan")
    assert ModelInvocation.objects.filter(stage="CANONICALIZATION").count() == 0


def test_worker_plan_uses_the_event_snapshot_seen_by_the_model(tmp_path) -> None:
    source = make_source()
    enqueue = enqueue_sources([source], trigger=IngestionTrigger.COMMAND)
    job = claim_job(enqueue.jobs[0].pk, "ingestion-worker")
    assert job is not None
    models = ConcurrentEventEditModels()
    storage = LocalRawContentStorage(tmp_path)
    TelegramTextPipeline(
        fetcher=FakeFetcher(fixture_messages()[:2]),
        models=models,
        storage=storage,
    ).execute(job)
    runtime = CanonicalizationWorkerRuntime(decision_provider=models, storage=storage)

    assert runtime.run_next_candidate() is not None
    assert runtime.run_next_candidate() is not None

    second = EventCandidate.objects.get(
        extraction_run__raw_source_document__source_representation__external_identifier="2"
    )
    plan = second.canonicalization_plan
    assert second.status == CandidateStatus.PROCESSED
    assert plan.status == "STALE"
    assert plan.application_error == "The target Event changed after this plan was generated."
    assert plan.target_event.description == "Owner edit made while the model was deciding."


def test_repaired_ready_candidate_is_eligible_for_the_worker(tmp_path) -> None:
    source = make_source()
    enqueue = enqueue_sources([source], trigger=IngestionTrigger.COMMAND)
    job = claim_job(enqueue.jobs[0].pk, "ingestion-worker")
    assert job is not None
    models = BusinessIssueModels()
    storage = LocalRawContentStorage(tmp_path)
    TelegramTextPipeline(
        fetcher=FakeFetcher(fixture_messages()[:1]),
        models=models,
        storage=storage,
    ).execute(job)
    candidate = EventCandidate.objects.get()
    assert candidate.status == CandidateStatus.BLOCKED

    repaired = (
        FakeModels()
        .extract(
            fixture_messages()[:1],
            reference_data=build_candidate_reference_data(),
        )
        .parsed.results[0]
        .events[0]
    )
    update_event_candidate(
        candidate.pk,
        expected_version=candidate.edit_version,
        effective_payload=repaired.model_dump(mode="json"),
        reviewer_notes="Approved repair",
        edited_by_id=None,
    )

    runtime = CanonicalizationWorkerRuntime(decision_provider=models, storage=storage)
    assert runtime.run_next_candidate() is not None
    candidate.refresh_from_db()
    assert candidate.status == CandidateStatus.PROCESSED
    assert Event.objects.count() == 1
