import json
import logging
from unittest.mock import Mock

import httpx
import pytest
from events.models import Event
from ingestion.candidates.service import update_event_candidate
from ingestion.canonicalization.worker import CanonicalizationWorkerRuntime
from ingestion.contracts import (
    CanonicalOccurrenceChange,
    CanonicalRegistrationValue,
    ObjectOperation,
    OccurrenceField,
)
from ingestion.jobs.service import claim_job, enqueue_sources
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
from openai import APITimeoutError

from tests.backend.ingestion.canonicalization.canonicalization_test_support import (
    update_description_proposal,
)

from .telegram_job_test_support import (
    BusinessIssueModels,
    ConcurrentEventEditModels,
    FakeFetcher,
    FakeModels,
    fixture_messages,
    make_source,
)

pytestmark = pytest.mark.django_db


def test_malformed_object_proposal_is_rejected_and_worker_advances(tmp_path):
    source = make_source()
    enqueue = enqueue_sources([source], trigger=IngestionTrigger.COMMAND)
    job = claim_job(enqueue.jobs[0].pk, "ingestion-worker")
    models = FakeModels()
    storage = LocalRawContentStorage(tmp_path)
    TelegramTextPipeline(
        fetcher=FakeFetcher(fixture_messages()[:3]), models=models, storage=storage
    ).execute(job)
    runtime = CanonicalizationWorkerRuntime(decision_provider=models, storage=storage)
    first = runtime.run_next_candidate()
    event = first.canonicalization_plan.target_event
    proposal = update_description_proposal(event.pk, "Should never be applied")
    proposal.occurrence_changes = [
        CanonicalOccurrenceChange(
            operation=ObjectOperation.UPDATE,
            id=event.occurrences.get().pk,
            changed_fields=[OccurrenceField.SEQUENCE],
            value=None,
        )
    ]
    original_decide = models.decide
    models.decide = Mock(return_value=models._result(proposal))
    rejected = runtime.run_next_candidate()
    rejected.refresh_from_db()
    assert rejected.canonicalization_plan.status == "REJECTED"
    assert rejected.status == CandidateStatus.PROCESSED
    assert rejected.canonicalization_plan.model_invocation.status == "SUCCEEDED"
    models.decide = original_decide
    following = runtime.run_next_candidate()
    assert following.canonicalization_plan.status == "APPLIED"
    assert runtime.run_next_candidate() is None


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


def test_structured_output_validation_failure_is_retried_and_can_recover(tmp_path) -> None:
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
    original_decide = models.decide
    call_count = 0

    def flaky_decide(context):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            _raise_invalid_canonical_time()
        return original_decide(context)

    models.decide = Mock(side_effect=flaky_decide)

    assert runtime.run_next_candidate() is not None

    candidate.refresh_from_db()
    assert candidate.status == CandidateStatus.PROCESSED
    invocations = list(
        ModelInvocation.objects.filter(stage="CANONICALIZATION", batch_index=candidate.pk).order_by(
            "attempt_number"
        )
    )
    assert [item.attempt_number for item in invocations] == [1, 2, 3]
    assert [item.status for item in invocations] == ["FAILED", "FAILED", "SUCCEEDED"]
    assert [item.error_type for item in invocations] == ["ValidationError", "ValidationError", ""]


def test_canonicalization_timeout_creates_review_plan_and_advances_queue(
    tmp_path, monkeypatch, caplog
) -> None:
    monkeypatch.setattr(logging.getLogger("ingestion"), "propagate", True)
    caplog.set_level(logging.INFO, logger="ingestion")
    source = make_source()
    enqueue = enqueue_sources([source], trigger=IngestionTrigger.COMMAND)
    job = claim_job(enqueue.jobs[0].pk, "ingestion-worker")
    assert job is not None
    models = FakeModels()
    storage = LocalRawContentStorage(tmp_path)
    TelegramTextPipeline(
        fetcher=FakeFetcher(fixture_messages()[:3]), models=models, storage=storage
    ).execute(job)
    runtime = CanonicalizationWorkerRuntime(decision_provider=models, storage=storage)
    assert runtime.run_next_candidate() is not None  # First candidate needs no model.
    candidate = EventCandidate.objects.get(
        extraction_run__raw_source_document__source_representation__external_identifier="2"
    )
    original_payload = candidate.effective_payload
    original_issues = candidate.validation_issues
    original_decide = models.decide
    models.decide = Mock(
        side_effect=APITimeoutError(request=httpx.Request("POST", "https://api.openai.com"))
    )
    events_before = Event.objects.count()

    assert runtime.run_next_candidate().pk == candidate.pk

    candidate.refresh_from_db()
    plan = candidate.canonicalization_plan
    assert candidate.status == CandidateStatus.PROCESSED
    assert candidate.effective_payload == original_payload
    assert candidate.validation_issues == original_issues
    assert plan.status == "REVIEW_REQUIRED"
    assert plan.generated_proposal == {}
    assert "timed out" in plan.application_error
    assert plan.model_invocation.error_type == "APITimeoutError"
    assert plan.model_invocation.status == "FAILED"
    assert (
        ModelInvocation.objects.filter(stage="CANONICALIZATION", batch_index=candidate.pk).count()
        == 1
    )
    models.decide.assert_called_once()  # SDK retry budget is inside the provider, not this loop.
    assert Event.objects.count() == events_before

    models.decide = original_decide
    next_candidate = runtime.run_next_candidate()
    assert next_candidate is not None
    assert next_candidate.pk != candidate.pk
    assert runtime.run_next_candidate() is None
    assert candidate.canonicalization_plan.pk == plan.pk
    job.refresh_from_db()
    assert job.status == JobStatus.SUCCEEDED
    events = [json.loads(record.message) for record in caplog.records if record.name == "ingestion"]
    names = {item["event"] for item in events}
    assert {
        "canonicalization.matching.started",
        "canonicalization.context.finished",
        "canonicalization.model_attempt.failed",
        "canonicalization.proposal_validation.finished",
        "canonicalization.application.finished",
        "canonicalization.plan_finished",
        "canonicalization.timeout_review",
    } <= names
    timeout_log = next(
        item for item in events if item["event"] == "canonicalization.timeout_review"
    )
    assert timeout_log["candidate_id"] == candidate.pk
    assert timeout_log["plan_id"] == plan.pk
    assert timeout_log["continuing"] is True


def test_exhausted_structured_output_retries_create_review_required_plan(tmp_path) -> None:
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
    models.decide = Mock(side_effect=lambda _context: _raise_invalid_canonical_time())

    assert runtime.run_next_candidate() is not None

    candidate.refresh_from_db()
    assert candidate.status == CandidateStatus.PROCESSED
    assert candidate.canonicalization_plan.status == "REVIEW_REQUIRED"
    assert "Canonicalization model failed" in candidate.canonicalization_plan.application_error
    invocations = list(
        ModelInvocation.objects.filter(stage="CANONICALIZATION", batch_index=candidate.pk).order_by(
            "attempt_number"
        )
    )
    assert len(invocations) == 3
    assert [item.attempt_number for item in invocations] == [1, 2, 3]
    assert {item.status for item in invocations} == {"FAILED"}
    assert {item.error_type for item in invocations} == {"ValidationError"}


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


def _raise_invalid_canonical_time() -> None:
    CanonicalRegistrationValue.model_validate(
        {
            "name": "Registration",
            "scope": "EVENT",
            "occurrence_id": None,
            "occurrence_client_ref": None,
            "url": None,
            "opens_date": None,
            "opens_time": None,
            "closes_date": "2026-08-18",
            "closes_time": "23:59:00Z",
            "instructions": None,
        }
    )
