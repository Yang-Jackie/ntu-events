from __future__ import annotations

from dataclasses import dataclass

from ingestion.models import (
    IngestionJob,
)
from ingestion.pipelines.telegram.adapter import TelegramMessage
from ingestion.pipelines.telegram.documents import upsert_representation
from ingestion.pipelines.telegram.extraction import extract_messages
from ingestion.pipelines.telegram.model_client import (
    OpenAITelegramModels,
)
from ingestion.pipelines.telegram.screening import screen_messages
from ingestion.raw_storage import RawContentStorage


@dataclass(frozen=True)
class ProcessingResult:
    items_screened: int
    items_relevant: int
    items_extracted: int
    candidates_created: int
    failure_ids: set[str]


def process_telegram_messages(
    *,
    job: IngestionJob,
    messages: list[TelegramMessage],
    models: OpenAITelegramModels,
    storage: RawContentStorage,
    options: dict[str, int],
) -> ProcessingResult:
    work = [upsert_representation(job, message) for message in messages]
    relevant, screening_failure_ids = screen_messages(
        job=job,
        work=work,
        models=models,
        storage=storage,
        concurrency=options["openai_concurrency"],
        batch_size=options["screening_batch_size"],
    )
    extraction_failure_ids, candidates_created, items_extracted = extract_messages(
        job=job,
        relevant=relevant,
        models=models,
        storage=storage,
        concurrency=options["openai_concurrency"],
        batch_size=options["extraction_batch_size"],
    )
    return ProcessingResult(
        items_screened=len(work),
        items_relevant=len(relevant),
        items_extracted=items_extracted,
        candidates_created=candidates_created,
        failure_ids=screening_failure_ids | extraction_failure_ids,
    )
