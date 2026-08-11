from __future__ import annotations

import json
from datetime import UTC, date, datetime, time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from ingestion.adapters.telegram import (
    TelegramFetcher,
    TelegramFetchResult,
    TelegramMessage,
    TelegramRetryableError,
)
from ingestion.contracts import (
    CandidateOccurrence,
    EventCandidatePayload,
    ExtractedMessage,
    ExtractionBatch,
    ScreeningBatch,
    ScreeningItem,
    ScreeningLabel,
    TimePrecision,
)
from ingestion.jobs import claim_job, enqueue_sources
from ingestion.models import (
    EventCandidate,
    IngestionRequest,
    IngestionTrigger,
    JobStatus,
    MessageScreening,
    ModelInvocation,
)
from ingestion.openai_models import ModelResult
from ingestion.raw_storage import LocalRawContentStorage
from ingestion.telegram_workflow import execute_telegram_job
from sources.models import RawSourceDocument, Source, SourceType
from telethon.errors import ServerError, TimedOutError

pytestmark = pytest.mark.django_db

FIXTURE_PATH = Path(__file__).parents[2] / "fixtures" / "sources" / "telegram" / "messages.json"


class FakeFetcher:
    def __init__(
        self,
        messages: list[TelegramMessage],
        *,
        latest_message_id: int | None = None,
    ):
        self.messages = messages
        self.latest_message_id = (
            latest_message_id
            if latest_message_id is not None
            else max((message.message_id for message in messages), default=None)
        )

    async def fetch(self, **_kwargs) -> TelegramFetchResult:
        return TelegramFetchResult(
            messages=self.messages,
            latest_message_id=self.latest_message_id,
        )


class FakeModels:
    screening_model = "gpt-5-nano"
    extraction_model = "gpt-5-mini"

    def __init__(self):
        self.screening_batch_sizes: list[int] = []
        self.extraction_batch_sizes: list[int] = []
        self.response_count = 0

    def screen(self, messages: list[TelegramMessage]) -> ModelResult[ScreeningBatch]:
        self.screening_batch_sizes.append(len(messages))
        return self._result(
            ScreeningBatch(
                results=[
                    ScreeningItem(
                        message_identity=message.identity,
                        decision=(
                            ScreeningLabel.EVENT
                            if message.message_id <= 12
                            else ScreeningLabel.NOT_EVENT
                        ),
                        reason="event details" if message.message_id <= 12 else "not an event",
                        confidence=0.95,
                    )
                    for message in messages
                ]
            )
        )

    def extract(self, messages: list[TelegramMessage]) -> ModelResult[ExtractionBatch]:
        self.extraction_batch_sizes.append(len(messages))
        return self._result(
            ExtractionBatch(
                results=[
                    ExtractedMessage(
                        message_identity=message.identity,
                        events=[
                            EventCandidatePayload(
                                title=f"Test event {message.message_id}",
                                occurrences=[
                                    CandidateOccurrence(
                                        start_date=date(2026, 8, 18),
                                        start_time=time(14),
                                        end_date=date(2026, 8, 18),
                                        end_time=time(16),
                                        time_precision=TimePrecision.EXACT,
                                        raw_location="The Arc",
                                    )
                                ],
                                source_url=message.source_url,
                                overall_confidence=0.9,
                            )
                        ],
                    )
                    for message in messages
                ]
            )
        )

    def _result(self, parsed):
        self.response_count += 1
        return ModelResult(
            parsed=parsed,
            response_identifier=f"response-{self.response_count}",
            token_usage={"input_tokens": 100, "output_tokens": 20},
            raw_response=b"{}",
        )


class FirstExtractionBatchFails(FakeModels):
    def extract(self, messages: list[TelegramMessage]) -> ModelResult[ExtractionBatch]:
        if messages[0].message_id == 1:
            self.extraction_batch_sizes.append(len(messages))
            raise RuntimeError("temporary provider failure")
        return super().extract(messages)


def make_source() -> Source:
    return Source.objects.create(
        name="Test Telegram channel",
        source_type=SourceType.PUBLIC_CHANNEL,
        base_url="https://t.me/test_channel",
        adapter_key="telegram_text",
        configuration={"channel_id": 12345, "username": "test_channel"},
    )


def fixture_messages() -> list[TelegramMessage]:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    retrieved_at = datetime(2026, 8, 10, 12, tzinfo=UTC)
    return [
        TelegramMessage(
            message_id=item["id"],
            channel_id=12345,
            channel_title="Test Telegram channel",
            channel_username="test_channel",
            source_url=f"https://t.me/test_channel/{item['id']}",
            published_at=datetime(2026, 8, 10, item["id"] % 12, tzinfo=UTC),
            edited_at=None,
            text=item["text"],
            reply_to_message_id=None,
            forwarded_from=None,
            retrieved_at=retrieved_at,
            content_hash=f"{item['id']:064x}",
        )
        for item in fixture["messages"]
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        ServerError(request=None, message="server unavailable"),
        TimedOutError(request=None, message="request timed out"),
    ],
)
async def test_transient_telegram_rpc_errors_are_retryable(tmp_path, error: Exception) -> None:
    client = SimpleNamespace(
        connect=AsyncMock(),
        is_user_authorized=AsyncMock(return_value=True),
        get_entity=AsyncMock(side_effect=error),
        disconnect=AsyncMock(),
    )
    fetcher = TelegramFetcher(api_id=1, api_hash="hash", session_path=tmp_path / "session")

    with (
        patch("ingestion.adapters.telegram.TelegramClient", return_value=client),
        pytest.raises(TelegramRetryableError),
    ):
        await fetcher.fetch(
            source_configuration={"username": "test_channel"},
            message_limit=100,
            overlap=20,
        )

    client.disconnect.assert_awaited_once()


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


def test_telegram_job_uses_fixed_batches_and_preserves_only_relevant_content(tmp_path) -> None:
    source = make_source()
    enqueue = enqueue_sources([source], trigger=IngestionTrigger.COMMAND)
    job = claim_job(enqueue.jobs[0].pk, "test-worker")
    assert job is not None
    models = FakeModels()

    execute_telegram_job(
        job,
        fetcher=FakeFetcher(fixture_messages()),
        models=models,
        storage=LocalRawContentStorage(tmp_path),
    )
    job.refresh_from_db()
    source.refresh_from_db()

    assert job.status == JobStatus.SUCCEEDED
    assert models.screening_batch_sizes == [20, 3]
    assert sorted(models.extraction_batch_sizes) == [2, 5, 5]
    assert MessageScreening.objects.count() == 23
    assert RawSourceDocument.objects.count() == 12
    assert EventCandidate.objects.count() == 12
    assert ModelInvocation.objects.count() == 5
    assert source.configuration["last_message_id"] == 23


def test_unchanged_messages_do_not_create_duplicate_candidates_or_model_calls(tmp_path) -> None:
    source = make_source()
    first = enqueue_sources([source], trigger=IngestionTrigger.COMMAND)
    first_job = claim_job(first.jobs[0].pk, "test-worker")
    assert first_job is not None
    first_models = FakeModels()
    messages = fixture_messages()
    execute_telegram_job(
        first_job,
        fetcher=FakeFetcher(messages),
        models=first_models,
        storage=LocalRawContentStorage(tmp_path),
    )

    second = enqueue_sources([source], trigger=IngestionTrigger.COMMAND)
    second_job = claim_job(second.jobs[0].pk, "test-worker")
    assert second_job is not None
    second_models = FakeModels()
    execute_telegram_job(
        second_job,
        fetcher=FakeFetcher(messages),
        models=second_models,
        storage=LocalRawContentStorage(tmp_path),
    )

    second_job.refresh_from_db()
    assert second_job.status == JobStatus.SUCCEEDED
    assert second_models.screening_batch_sizes == []
    assert second_models.extraction_batch_sizes == []
    assert EventCandidate.objects.count() == 12


def test_model_version_changes_invalidate_cached_processing(tmp_path) -> None:
    source = make_source()
    messages = fixture_messages()
    first = enqueue_sources([source], trigger=IngestionTrigger.COMMAND)
    first_job = claim_job(first.jobs[0].pk, "test-worker")
    assert first_job is not None
    execute_telegram_job(
        first_job,
        fetcher=FakeFetcher(messages),
        models=FakeModels(),
        storage=LocalRawContentStorage(tmp_path),
    )

    second = enqueue_sources([source], trigger=IngestionTrigger.COMMAND)
    second_job = claim_job(second.jobs[0].pk, "test-worker")
    assert second_job is not None
    changed_models = FakeModels()
    changed_models.screening_model = "gpt-5-nano-v2"
    changed_models.extraction_model = "gpt-5-mini-v2"
    execute_telegram_job(
        second_job,
        fetcher=FakeFetcher(messages),
        models=changed_models,
        storage=LocalRawContentStorage(tmp_path),
    )

    assert changed_models.screening_batch_sizes == [20, 3]
    assert sorted(changed_models.extraction_batch_sizes) == [2, 5, 5]
    assert EventCandidate.objects.count() == 24


def test_media_only_fetch_advances_cursor_without_model_calls(tmp_path) -> None:
    source = make_source()
    enqueue = enqueue_sources([source], trigger=IngestionTrigger.COMMAND)
    job = claim_job(enqueue.jobs[0].pk, "test-worker")
    assert job is not None
    models = FakeModels()

    execute_telegram_job(
        job,
        fetcher=FakeFetcher([], latest_message_id=99),
        models=models,
        storage=LocalRawContentStorage(tmp_path),
    )

    job.refresh_from_db()
    source.refresh_from_db()
    assert job.status == JobStatus.SUCCEEDED
    assert source.configuration["last_message_id"] == 99
    assert models.screening_batch_sizes == []
    assert models.extraction_batch_sizes == []


def test_partial_job_advances_cursor_and_retries_recorded_failed_messages(tmp_path) -> None:
    source = make_source()
    messages = fixture_messages()
    first = enqueue_sources([source], trigger=IngestionTrigger.COMMAND)
    first_job = claim_job(first.jobs[0].pk, "test-worker")
    assert first_job is not None

    execute_telegram_job(
        first_job,
        fetcher=FakeFetcher(messages),
        models=FirstExtractionBatchFails(),
        storage=LocalRawContentStorage(tmp_path),
    )
    first_job.refresh_from_db()
    source.refresh_from_db()

    assert first_job.status == JobStatus.PARTIAL
    assert source.configuration["last_message_id"] == 23
    assert source.configuration["pending_message_ids"] == [1, 2, 3, 4, 5]
    assert EventCandidate.objects.count() == 7

    second = enqueue_sources([source], trigger=IngestionTrigger.COMMAND)
    second_job = claim_job(second.jobs[0].pk, "test-worker")
    assert second_job is not None
    execute_telegram_job(
        second_job,
        fetcher=FakeFetcher(messages),
        models=FakeModels(),
        storage=LocalRawContentStorage(tmp_path),
    )
    second_job.refresh_from_db()
    source.refresh_from_db()

    assert second_job.status == JobStatus.SUCCEEDED
    assert "pending_message_ids" not in source.configuration
    assert EventCandidate.objects.count() == 12
