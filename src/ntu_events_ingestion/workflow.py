from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from .extractor import EventExtractor, extraction_cache_key
from .models import ExtractionRecord, FailureRecord, RawTelegramMessage
from .storage import read_json, write_json


async def process_messages(
    messages: list[RawTelegramMessage],
    extractor: EventExtractor,
    run_dir: Path,
    cache_path: Path,
    *,
    max_calls: int = 200,
    max_concurrency: int = 10,
    force: bool = False,
    progress: Callable[[str], None] = print,
) -> tuple[list[ExtractionRecord], list[FailureRecord], int]:
    cache = {
        key: ExtractionRecord.model_validate(value)
        for key, value in read_json(cache_path, {}).items()
    }
    ordered_results: list[ExtractionRecord | FailureRecord | None] = [None] * len(messages)
    pending: list[tuple[int, RawTelegramMessage, str]] = []
    calls = 0
    for index, message in enumerate(messages):
        key = extraction_cache_key(message, extractor.model)
        if not force and key in cache:
            progress(f"cache  {message.identity}")
            ordered_results[index] = cache[key]
            continue
        if calls >= max_calls:
            ordered_results[index] = FailureRecord(
                source_message_identity=message.identity,
                stage="extract",
                error_type="CallLimitReached",
                error_message=f"Run limit of {max_calls} OpenAI calls reached",
                occurred_at=datetime.now(UTC),
            )
            continue
        pending.append((index, message, key))
        calls += 1

    semaphore = asyncio.Semaphore(max_concurrency)

    async def extract_one(
        index: int, message: RawTelegramMessage, key: str
    ) -> tuple[int, str, ExtractionRecord | FailureRecord]:
        async with semaphore:
            try:
                progress(f"model  {message.identity}")
                return index, key, await extractor.extract(message)
            except Exception as exc:
                return (
                    index,
                    key,
                    FailureRecord(
                        source_message_identity=message.identity,
                        stage="extract",
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                        occurred_at=datetime.now(UTC),
                    ),
                )

    completed = await asyncio.gather(
        *(extract_one(index, message, key) for index, message, key in pending)
    )
    for index, key, result in completed:
        ordered_results[index] = result
        if isinstance(result, ExtractionRecord):
            cache[key] = result

    records = [result for result in ordered_results if isinstance(result, ExtractionRecord)]
    failures = [result for result in ordered_results if isinstance(result, FailureRecord)]
    write_json(
        cache_path,
        {key: value.model_dump(mode="json") for key, value in cache.items()},
    )
    write_json(run_dir / "extraction_results.json", records)
    write_json(
        run_dir / "event_candidates.json",
        [
            {
                "source_message_identity": record.source_message_identity,
                **event.model_dump(mode="json"),
            }
            for record in records
            for event in record.result.events
        ],
    )
    write_json(run_dir / "failures.json", failures)
    return records, failures, calls
