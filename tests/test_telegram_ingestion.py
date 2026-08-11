import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ntu_events_ingestion.extractor import OpenAIEventExtractor, extraction_cache_key
from ntu_events_ingestion.models import (
    ExtractedEvent,
    ExtractionRecord,
    MessageExtraction,
    RawTelegramMessage,
)
from ntu_events_ingestion.storage import read_json
from ntu_events_ingestion.telegram_source import content_hash, parse_selection
from ntu_events_ingestion.workflow import process_messages


def raw_message(message_id: int = 7) -> RawTelegramMessage:
    text = f"Workshop {message_id} tomorrow at 2pm in LT19A."
    return RawTelegramMessage(
        channel_id=123,
        channel_username="club",
        channel_title="Club",
        message_id=message_id,
        message_url=f"https://t.me/club/{message_id}",
        published_at=datetime(2026, 7, 25, tzinfo=UTC),
        text=text,
        content_hash=content_hash(text),
        retrieved_at=datetime.now(UTC),
        retrieval_version="test",
    )


class FakeExtractor:
    model = "cheap-test-model"

    def __init__(self) -> None:
        self.calls = 0

    async def extract(self, message: RawTelegramMessage) -> ExtractionRecord:
        self.calls += 1
        return ExtractionRecord(
            source_message_identity=message.identity,
            source_content_hash=message.content_hash,
            model=self.model,
            prompt_version="telegram-event-v1",
            schema_version="event-candidate-research-v1",
            processed_at=datetime.now(UTC),
            result=MessageExtraction(
                is_event_related=True,
                events=[
                    ExtractedEvent(
                        title="Workshop",
                        raw_location="LT19A",
                        confidence=0.8,
                        evidence=["Workshop tomorrow at 2pm in LT19A."],
                    )
                ],
            ),
            cache_key=extraction_cache_key(message, self.model),
        )


class ConcurrentFakeExtractor(FakeExtractor):
    def __init__(self) -> None:
        super().__init__()
        self.active = 0
        self.maximum_active = 0

    async def extract(self, message: RawTelegramMessage) -> ExtractionRecord:
        self.active += 1
        self.maximum_active = max(self.maximum_active, self.active)
        try:
            await asyncio.sleep(0.01)
            return await super().extract(message)
        finally:
            self.active -= 1


def test_multi_channel_selection_is_ordered_and_deduplicated() -> None:
    assert parse_selection("3, 1,3", 4) == [2, 0]
    with pytest.raises(ValueError):
        parse_selection("5", 4)


def test_candidate_contract_rejects_inconsistent_event_flag() -> None:
    with pytest.raises(ValueError):
        MessageExtraction(is_event_related=True)


@pytest.mark.asyncio
async def test_research_extractor_uses_responses_text_verbosity() -> None:
    parse = AsyncMock(
        return_value=SimpleNamespace(
            output_parsed=MessageExtraction(
                is_event_related=False,
                rejection_reason="not an event",
            ),
            id="response-1",
            usage=None,
        )
    )
    extractor = object.__new__(OpenAIEventExtractor)
    extractor.model = "gpt-5-nano"
    extractor.client = SimpleNamespace(responses=SimpleNamespace(parse=parse))

    message = raw_message().model_copy(
        update={"published_at": datetime(2026, 8, 10, 18, tzinfo=UTC)}
    )
    await extractor.extract(message)

    assert parse.call_args.kwargs["text"] == {"verbosity": "low"}
    assert "verbosity" not in parse.call_args.kwargs
    prompt = json.loads(parse.call_args.kwargs["input"][1]["content"])
    assert prompt["published_at"] == "2026-08-11T02:00:00+08:00"


@pytest.mark.asyncio
async def test_workflow_writes_json_and_reuses_cache(tmp_path: Path) -> None:
    message = raw_message()
    extractor = FakeExtractor()
    cache = tmp_path / "cache.json"
    records, failures, calls = await process_messages(
        [message], extractor, tmp_path / "run-one", cache
    )
    assert len(records) == 1
    assert failures == []
    assert calls == 1
    assert read_json(tmp_path / "run-one" / "event_candidates.json", [])[0]["title"] == "Workshop"

    _, _, calls = await process_messages([message], extractor, tmp_path / "run-two", cache)
    assert calls == 0
    assert extractor.calls == 1


@pytest.mark.asyncio
async def test_workflow_bounds_concurrency_and_preserves_order(tmp_path: Path) -> None:
    messages = [raw_message(message_id) for message_id in range(1, 13)]
    extractor = ConcurrentFakeExtractor()
    records, failures, calls = await process_messages(
        messages,
        extractor,
        tmp_path / "concurrent-run",
        tmp_path / "cache.json",
        max_calls=200,
        max_concurrency=3,
    )
    assert failures == []
    assert calls == 12
    assert extractor.maximum_active == 3
    assert [record.source_message_identity for record in records] == [
        message.identity for message in messages
    ]
