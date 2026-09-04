from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from events.models import Event
from ingestion.jobs import claim_job, enqueue_sources
from ingestion.models import (
    CandidateStatus,
    EventCandidate,
    IngestionRequest,
    IngestionTrigger,
    JobStatus,
    MessageScreening,
    ModelInvocation,
)
from ingestion.pipelines.telegram.pipeline import TelegramTextPipeline
from ingestion.raw_storage import LocalRawContentStorage
from sources.models import RawSourceDocument, Source, SourceType

from .telegram_job_test_support import FakeFetcher, FakeModels, fixture_messages, make_source

pytestmark = pytest.mark.django_db


def test_one_request_creates_one_job_per_source_and_skips_active_duplicates() -> None:
    first = make_source()
    second = Source.objects.create(
        name="Second channel",
        source_type=SourceType.PUBLIC_CHANNEL,
        adapter_key="telegram_text",
        configuration={"channel_id": 67890, "username": "second"},
    )

    result = enqueue_sources([first, second], trigger=IngestionTrigger.COMMAND)
    duplicate = enqueue_sources([first], trigger=IngestionTrigger.ADMIN)

    assert len(result.jobs) == 2
    assert {job.source_id for job in result.jobs} == {first.pk, second.pk}
    assert duplicate.jobs == []
    assert duplicate.skipped_sources == [first]


def test_empty_request_is_complete_instead_of_permanently_queued() -> None:
    incompatible = Source.objects.create(
        name="Website",
        source_type=SourceType.OFFICIAL_WEBSITE,
        adapter_key="website",
    )

    result = enqueue_sources([incompatible], trigger=IngestionTrigger.ADMIN)

    assert result.jobs == []
    assert result.request.status == JobStatus.SUCCEEDED


def test_enqueue_rejects_an_unknown_trigger() -> None:
    with pytest.raises(ValueError, match="Unsupported ingestion trigger"):
        enqueue_sources([make_source()], trigger="UNKNOWN")


@pytest.mark.parametrize(
    "options",
    [
        {"message_limit": 0},
        {"openai_concurrency": 11},
        {"message_limit": 1.5},
        {"unknown": 1},
    ],
)
def test_enqueue_rejects_invalid_options_before_creating_a_request(options: dict) -> None:
    with pytest.raises(ValueError):
        enqueue_sources(
            [make_source()],
            trigger=IngestionTrigger.COMMAND,
            options=options,
        )

    assert IngestionRequest.objects.count() == 0


def test_telegram_pipeline_is_lightweight_until_execution() -> None:
    pipeline = TelegramTextPipeline()

    options = pipeline.normalize_options({"message_limit": 25})

    assert options["message_limit"] == 25
    assert options["screening_batch_size"] == 20
    assert pipeline._fetcher is None
    assert pipeline._models is None
    assert pipeline._storage is None


def test_telegram_pipeline_closes_only_initialized_model_resources() -> None:
    models = SimpleNamespace(close=Mock())
    pipeline = TelegramTextPipeline(models=models)

    pipeline.close()

    models.close.assert_called_once_with()
    assert pipeline._models is None


def test_telegram_job_uses_fixed_batches_and_preserves_only_relevant_content(tmp_path) -> None:
    source = make_source()
    enqueue = enqueue_sources([source], trigger=IngestionTrigger.COMMAND)
    job = claim_job(enqueue.jobs[0].pk, "test-worker")
    assert job is not None
    models = FakeModels()

    TelegramTextPipeline(
        fetcher=FakeFetcher(fixture_messages()),
        models=models,
        storage=LocalRawContentStorage(tmp_path),
    ).execute(job)
    job.refresh_from_db()
    source.refresh_from_db()

    assert job.status == JobStatus.SUCCEEDED
    assert models.screening_batch_sizes == [20, 3]
    assert sorted(models.extraction_batch_sizes) == [2, 5, 5]
    assert MessageScreening.objects.count() == 23
    assert RawSourceDocument.objects.count() == 12
    assert set(RawSourceDocument.objects.values_list("ingestion_job_id", flat=True)) == {job.pk}
    assert EventCandidate.objects.count() == 12
    assert set(EventCandidate.objects.values_list("status", flat=True)) == {CandidateStatus.READY}
    assert Event.objects.count() == 0
    assert ModelInvocation.objects.filter(stage="SCREENING").count() == 2
    assert ModelInvocation.objects.filter(stage="EXTRACTION").count() == 3
    assert ModelInvocation.objects.filter(stage="CANONICALIZATION").count() == 0
    extraction_invocation = ModelInvocation.objects.filter(stage="EXTRACTION").first()
    assert extraction_invocation is not None
    assert extraction_invocation.reference_data_snapshot["venues"]
    assert extraction_invocation.reference_data_hash
    assert source.configuration["last_message_id"] == 23
