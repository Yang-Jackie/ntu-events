from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest
from ingestion.jobs import claim_job, enqueue_sources, recover_stale_jobs
from ingestion.models import (
    EventCandidate,
    ExtractionRun,
    ExtractionStatus,
    IngestionTrigger,
    JobStatus,
    MessageScreening,
    ModelInvocation,
)
from ingestion.pipelines.telegram.pipeline import TelegramTextPipeline
from ingestion.pipelines.telegram.processing import process_telegram_messages
from ingestion.raw_storage import LocalRawContentStorage
from sources.models import RawSourceDocument
from venues.models import Venue, VenueType

from .telegram_job_test_support import (
    FakeFetcher,
    FakeModels,
    FirstExtractionBatchFails,
    ScreeningFails,
    fixture_messages,
    make_source,
)

pytestmark = pytest.mark.django_db


def test_unchanged_messages_do_not_create_duplicate_candidates_or_model_calls(tmp_path) -> None:
    source = make_source()
    first = enqueue_sources([source], trigger=IngestionTrigger.COMMAND)
    first_job = claim_job(first.jobs[0].pk, "test-worker")
    assert first_job is not None
    first_models = FakeModels()
    messages = fixture_messages()
    TelegramTextPipeline(
        fetcher=FakeFetcher(messages),
        models=first_models,
        storage=LocalRawContentStorage(tmp_path),
    ).execute(first_job)

    second = enqueue_sources([source], trigger=IngestionTrigger.COMMAND)
    second_job = claim_job(second.jobs[0].pk, "test-worker")
    assert second_job is not None
    second_models = FakeModels()
    TelegramTextPipeline(
        fetcher=FakeFetcher(messages),
        models=second_models,
        storage=LocalRawContentStorage(tmp_path),
    ).execute(second_job)

    second_job.refresh_from_db()
    assert second_job.status == JobStatus.SUCCEEDED
    assert second_models.screening_batch_sizes == []
    assert second_models.extraction_batch_sizes == []
    assert EventCandidate.objects.count() == 12


def test_reference_catalog_changes_do_not_invalidate_cached_extraction(tmp_path) -> None:
    source = make_source()
    messages = fixture_messages()
    first = enqueue_sources([source], trigger=IngestionTrigger.COMMAND)
    first_job = claim_job(first.jobs[0].pk, "test-worker")
    assert first_job is not None
    TelegramTextPipeline(
        fetcher=FakeFetcher(messages),
        models=FakeModels(),
        storage=LocalRawContentStorage(tmp_path),
    ).execute(first_job)

    # Routine catalog maintenance must not force re-extraction of unrelated messages.
    Venue.objects.create(
        name="New Verified Venue",
        normalized_name="new verified venue",
        venue_type=VenueType.OTHER,
        is_verified=True,
    )

    second = enqueue_sources([source], trigger=IngestionTrigger.COMMAND)
    second_job = claim_job(second.jobs[0].pk, "test-worker")
    assert second_job is not None
    second_models = FakeModels()
    TelegramTextPipeline(
        fetcher=FakeFetcher(messages),
        models=second_models,
        storage=LocalRawContentStorage(tmp_path),
    ).execute(second_job)

    second_job.refresh_from_db()
    assert second_job.status == JobStatus.SUCCEEDED
    assert second_models.screening_batch_sizes == []
    assert second_models.extraction_batch_sizes == []
    assert EventCandidate.objects.count() == 12


def test_extraction_contract_version_changes_invalidate_cached_extraction(tmp_path) -> None:
    source = make_source()
    messages = fixture_messages()
    first = enqueue_sources([source], trigger=IngestionTrigger.COMMAND)
    first_job = claim_job(first.jobs[0].pk, "test-worker")
    assert first_job is not None
    TelegramTextPipeline(
        fetcher=FakeFetcher(messages),
        models=FakeModels(),
        storage=LocalRawContentStorage(tmp_path),
    ).execute(first_job)
    ExtractionRun.objects.filter(status=ExtractionStatus.SUCCEEDED).update(
        prompt_version="telegram-extraction-v4"
    )
    ModelInvocation.objects.filter(stage="EXTRACTION").update(
        prompt_version="telegram-extraction-v4",
        schema_version="telegram-extraction-v3",
    )

    second = enqueue_sources([source], trigger=IngestionTrigger.COMMAND)
    second_job = claim_job(second.jobs[0].pk, "test-worker")
    assert second_job is not None
    second_models = FakeModels()
    TelegramTextPipeline(
        fetcher=FakeFetcher(messages),
        models=second_models,
        storage=LocalRawContentStorage(tmp_path),
    ).execute(second_job)

    assert sorted(second_models.extraction_batch_sizes) == [2, 5, 5]
    assert EventCandidate.objects.count() == 24


def test_edited_message_creates_a_new_raw_document_and_candidate_revision(tmp_path) -> None:
    source = make_source()
    original = fixture_messages()[0]
    first = enqueue_sources([source], trigger=IngestionTrigger.COMMAND)
    first_job = claim_job(first.jobs[0].pk, "test-worker")
    assert first_job is not None
    first_models = FakeModels()
    TelegramTextPipeline(
        fetcher=FakeFetcher([original]),
        models=first_models,
        storage=LocalRawContentStorage(tmp_path),
    ).execute(first_job)

    edited = replace(
        original,
        text=f"{original.text}\nUpdated registration details.",
        edited_at=datetime(2026, 8, 11, 8, tzinfo=UTC),
        retrieved_at=datetime(2026, 8, 11, 9, tzinfo=UTC),
        content_hash="f" * 64,
    )
    second = enqueue_sources([source], trigger=IngestionTrigger.COMMAND)
    second_job = claim_job(second.jobs[0].pk, "test-worker")
    assert second_job is not None
    second_models = FakeModels()
    TelegramTextPipeline(
        fetcher=FakeFetcher([edited]),
        models=second_models,
        storage=LocalRawContentStorage(tmp_path),
    ).execute(second_job)

    assert first_models.screening_batch_sizes == [1]
    assert first_models.extraction_batch_sizes == [1]
    assert second_models.screening_batch_sizes == [1]
    assert second_models.extraction_batch_sizes == [1]
    assert source.representations.count() == 1
    assert RawSourceDocument.objects.count() == 2
    assert ExtractionRun.objects.count() == 2
    assert EventCandidate.objects.count() == 2


def test_model_version_changes_invalidate_cached_processing(tmp_path) -> None:
    source = make_source()
    messages = fixture_messages()
    first = enqueue_sources([source], trigger=IngestionTrigger.COMMAND)
    first_job = claim_job(first.jobs[0].pk, "test-worker")
    assert first_job is not None
    TelegramTextPipeline(
        fetcher=FakeFetcher(messages),
        models=FakeModels(),
        storage=LocalRawContentStorage(tmp_path),
    ).execute(first_job)

    second = enqueue_sources([source], trigger=IngestionTrigger.COMMAND)
    second_job = claim_job(second.jobs[0].pk, "test-worker")
    assert second_job is not None
    changed_models = FakeModels()
    changed_models.screening_model = "gpt-5-nano-v2"
    changed_models.extraction_model = "gpt-5-mini-v2"
    TelegramTextPipeline(
        fetcher=FakeFetcher(messages),
        models=changed_models,
        storage=LocalRawContentStorage(tmp_path),
    ).execute(second_job)

    assert changed_models.screening_batch_sizes == [20, 3]
    assert sorted(changed_models.extraction_batch_sizes) == [2, 5, 5]
    assert EventCandidate.objects.count() == 24


def test_media_only_fetch_advances_cursor_without_model_calls(tmp_path) -> None:
    source = make_source()
    enqueue = enqueue_sources([source], trigger=IngestionTrigger.COMMAND)
    job = claim_job(enqueue.jobs[0].pk, "test-worker")
    assert job is not None
    models = FakeModels()

    TelegramTextPipeline(
        fetcher=FakeFetcher([], latest_message_id=99),
        models=models,
        storage=LocalRawContentStorage(tmp_path),
    ).execute(job)

    job.refresh_from_db()
    source.refresh_from_db()
    assert job.status == JobStatus.SUCCEEDED
    assert source.configuration["last_message_id"] == 99
    assert models.screening_batch_sizes == []
    assert models.extraction_batch_sizes == []


def test_reclaimed_job_replaces_failed_screening_without_duplicate_work(tmp_path) -> None:
    source = make_source()
    enqueue = enqueue_sources([source], trigger=IngestionTrigger.COMMAND)
    job = claim_job(enqueue.jobs[0].pk, "interrupted-worker")
    assert job is not None
    messages = fixture_messages()[:1]
    storage = LocalRawContentStorage(tmp_path)

    first_result = process_telegram_messages(
        job=job,
        messages=messages,
        models=ScreeningFails(),
        storage=storage,
        options=TelegramTextPipeline().normalize_options({"message_limit": 1}),
    )

    assert first_result.failure_ids == {"1"}
    assert job.status == JobStatus.RUNNING
    assert MessageScreening.objects.get(job=job).decision == "FAILED"
    job.heartbeat_at = datetime.now(UTC) - timedelta(minutes=11)
    job.save(update_fields=("heartbeat_at",))
    assert recover_stale_jobs() == 1

    reclaimed = claim_job(job.pk, "replacement-worker")
    assert reclaimed is not None
    assert reclaimed.attempt_count == 2
    TelegramTextPipeline(
        fetcher=FakeFetcher(messages),
        models=FakeModels(),
        storage=storage,
    ).execute(reclaimed)

    reclaimed.refresh_from_db()
    screening = MessageScreening.objects.get(job=reclaimed)
    assert reclaimed.status == JobStatus.SUCCEEDED
    assert screening.decision == "EVENT"
    assert screening.model_invocation.attempt_number == 2
    assert MessageScreening.objects.filter(job=reclaimed).count() == 1
    assert ModelInvocation.objects.filter(job=reclaimed, stage="SCREENING").count() == 2
    assert EventCandidate.objects.count() == 1


def test_partial_job_advances_cursor_and_retries_recorded_failed_messages(tmp_path) -> None:
    source = make_source()
    messages = fixture_messages()
    first = enqueue_sources([source], trigger=IngestionTrigger.COMMAND)
    first_job = claim_job(first.jobs[0].pk, "test-worker")
    assert first_job is not None

    TelegramTextPipeline(
        fetcher=FakeFetcher(messages),
        models=FirstExtractionBatchFails(),
        storage=LocalRawContentStorage(tmp_path),
    ).execute(first_job)
    first_job.refresh_from_db()
    source.refresh_from_db()

    assert first_job.status == JobStatus.PARTIAL
    assert source.configuration["last_message_id"] == 23
    assert source.configuration["pending_message_ids"] == [1, 2, 3, 4, 5]
    assert EventCandidate.objects.count() == 7

    second = enqueue_sources([source], trigger=IngestionTrigger.COMMAND)
    second_job = claim_job(second.jobs[0].pk, "test-worker")
    assert second_job is not None
    TelegramTextPipeline(
        fetcher=FakeFetcher(messages),
        models=FakeModels(),
        storage=LocalRawContentStorage(tmp_path),
    ).execute(second_job)
    second_job.refresh_from_db()
    source.refresh_from_db()

    assert second_job.status == JobStatus.SUCCEEDED
    assert "pending_message_ids" not in source.configuration
    assert EventCandidate.objects.count() == 12
