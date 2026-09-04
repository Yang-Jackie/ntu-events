import pytest
from ingestion.jobs import claim_job, enqueue_sources
from ingestion.models import EventCandidate, ExtractionRun, IngestionTrigger, ModelInvocation
from ingestion.pipelines.telegram.pipeline import TelegramTextPipeline
from ingestion.raw_storage import LocalRawContentStorage

from .telegram_job_test_support import (
    BusinessIssueModels,
    FakeFetcher,
    StructuralOutputFails,
    fixture_messages,
    make_source,
)

pytestmark = pytest.mark.django_db


def test_business_validation_issue_keeps_candidate_for_review(tmp_path) -> None:
    source = make_source()
    enqueue = enqueue_sources([source], trigger=IngestionTrigger.COMMAND)
    job = claim_job(enqueue.jobs[0].pk, "test-worker")
    assert job is not None

    TelegramTextPipeline(
        fetcher=FakeFetcher(fixture_messages()[:1]),
        models=BusinessIssueModels(),
        storage=LocalRawContentStorage(tmp_path),
    ).execute(job)

    candidate = EventCandidate.objects.get()
    assert candidate.status == "BLOCKED"
    assert not hasattr(candidate, "canonicalization_plan")
    assert any(
        issue["code"] == "OCCURRENCE_END_BEFORE_START" for issue in candidate.validation_issues
    )


def test_structural_output_failure_creates_no_candidate_but_retains_diagnostics(tmp_path) -> None:
    source = make_source()
    enqueue = enqueue_sources([source], trigger=IngestionTrigger.COMMAND)
    job = claim_job(enqueue.jobs[0].pk, "test-worker")
    assert job is not None

    TelegramTextPipeline(
        fetcher=FakeFetcher(fixture_messages()[:1]),
        models=StructuralOutputFails(),
        storage=LocalRawContentStorage(tmp_path),
    ).execute(job)

    invocation = ModelInvocation.objects.get(stage="EXTRACTION")
    extraction = ExtractionRun.objects.get()
    assert EventCandidate.objects.count() == 0
    assert invocation.status == "FAILED"
    assert invocation.response_identifier == "response-incomplete"
    assert (tmp_path / invocation.raw_output_storage_key).read_bytes() == b'{"status":"incomplete"}'
    assert extraction.raw_output_storage_key == invocation.raw_output_storage_key
