from __future__ import annotations

from functools import partial

from django.db import transaction
from sources.models import ProcessingStatus

from ingestion.candidates import create_extracted_candidate
from ingestion.contracts import (
    EXTRACTION_SCHEMA_VERSION,
    EventCandidatePayload,
    ExtractionBatch,
)
from ingestion.models import (
    ExtractionRun,
    ExtractionStatus,
    IngestionJob,
    ModelInvocation,
    ModelInvocationStage,
)
from ingestion.pipelines.telegram.documents import MessageWork
from ingestion.pipelines.telegram.model_client import (
    EXTRACTION_PROMPT_VERSION,
    OpenAITelegramModels,
)
from ingestion.pipelines.telegram.stage_runtime import BatchOutcome, heartbeat, run_batches
from ingestion.raw_storage import RawContentStorage
from ingestion.reference_data import (
    build_candidate_reference_data,
)

TELEGRAM_EXTRACTOR_TYPE = "telegram-llm"
TELEGRAM_EXTRACTOR_VERSION = "telegram-m4a-v3"


def extract_messages(
    *,
    job: IngestionJob,
    relevant: list[MessageWork],
    models: OpenAITelegramModels,
    storage: RawContentStorage,
    concurrency: int,
    batch_size: int,
) -> tuple[set[str], int, int]:
    if not relevant:
        return set(), 0, 0

    reference_data = build_candidate_reference_data()
    pending: list[MessageWork] = []
    for item in relevant:
        if item.raw_document is None:
            raise RuntimeError("Relevant messages must have a preserved raw document")
        # Deliberately not gated on the reference catalog: venue and classification
        # identity (PKs, unique codes) is stable, so routine catalog edits such as
        # verifying a venue must not invalidate prior extractions. Bump
        # TELEGRAM_EXTRACTOR_VERSION when a reprocessing pass is actually wanted.
        already_extracted = ExtractionRun.objects.filter(
            raw_source_document=item.raw_document,
            extractor_type=TELEGRAM_EXTRACTOR_TYPE,
            extractor_version=TELEGRAM_EXTRACTOR_VERSION,
            model_name=models.extraction_model,
            prompt_version=EXTRACTION_PROMPT_VERSION,
            model_invocation__schema_version=EXTRACTION_SCHEMA_VERSION,
            status=ExtractionStatus.SUCCEEDED,
        ).exists()
        if not already_extracted:
            pending.append(item)
    if not pending:
        return set(), 0, 0
    by_identity = {item.message.identity: item for item in pending}
    failure_ids: set[str] = set()
    candidates_created = 0
    items_extracted = 0

    def success(outcome: BatchOutcome[ExtractionBatch], invocation: ModelInvocation) -> None:
        nonlocal candidates_created, items_extracted
        model_result = outcome.result
        if model_result is None:
            raise RuntimeError("Successful extraction outcome is missing its model result")
        raw_output_key = invocation.raw_output_storage_key
        for result in model_result.parsed.results:
            item = by_identity[result.message_identity]
            raw_document = item.raw_document
            if raw_document is None:
                raise RuntimeError("Relevant messages must have a preserved raw document")
            with transaction.atomic():
                extraction = ExtractionRun.objects.create(
                    model_invocation=invocation,
                    raw_source_document=raw_document,
                    extractor_type=TELEGRAM_EXTRACTOR_TYPE,
                    extractor_version=TELEGRAM_EXTRACTOR_VERSION,
                    model_name=models.extraction_model,
                    prompt_version=EXTRACTION_PROMPT_VERSION,
                    started_at=outcome.started_at,
                    completed_at=outcome.completed_at,
                    status=ExtractionStatus.SUCCEEDED,
                    input_storage_key=raw_document.storage_key,
                    raw_output_storage_key=raw_output_key,
                    response_identifier=invocation.response_identifier,
                    token_usage=invocation.token_usage,
                )
                for index, candidate in enumerate(result.events):
                    candidate = _trusted_source_url(candidate, item.message.source_url)
                    create_extracted_candidate(
                        extraction_run=extraction,
                        source_representation=item.representation,
                        candidate_index=index,
                        payload=candidate,
                        reference_data=reference_data,
                    )
                    candidates_created += 1
                raw_document.processing_status = ProcessingStatus.PROCESSED
                raw_document.save(update_fields=("processing_status",))
            items_extracted += 1

    def failed(outcome: BatchOutcome[ExtractionBatch], invocation: ModelInvocation) -> None:
        for message in outcome.messages:
            item = by_identity[message.identity]
            raw_document = item.raw_document
            if raw_document is None:
                raise RuntimeError("Relevant messages must have a preserved raw document")
            ExtractionRun.objects.create(
                model_invocation=invocation,
                raw_source_document=raw_document,
                extractor_type=TELEGRAM_EXTRACTOR_TYPE,
                extractor_version=TELEGRAM_EXTRACTOR_VERSION,
                model_name=models.extraction_model,
                prompt_version=EXTRACTION_PROMPT_VERSION,
                started_at=outcome.started_at,
                completed_at=outcome.completed_at,
                status=ExtractionStatus.FAILED,
                input_storage_key=raw_document.storage_key,
                raw_output_storage_key=invocation.raw_output_storage_key,
                response_identifier=invocation.response_identifier,
                token_usage=invocation.token_usage,
                error_message=str(outcome.error),
            )
            raw_document.processing_status = ProcessingStatus.FAILED
            raw_document.save(update_fields=("processing_status",))
            failure_ids.add(message.identity)

    run_batches(
        job=job,
        messages=[item.message for item in pending],
        batch_size=batch_size,
        concurrency=concurrency,
        stage=ModelInvocationStage.EXTRACTION,
        model_name=models.extraction_model,
        prompt_version=EXTRACTION_PROMPT_VERSION,
        schema_version=EXTRACTION_SCHEMA_VERSION,
        call=partial(models.extract, reference_data=reference_data),
        storage=storage,
        reference_data=reference_data,
        on_success=success,
        on_final_failure=failed,
    )
    heartbeat(job)
    return failure_ids, candidates_created, items_extracted


def _trusted_source_url(candidate: EventCandidatePayload, source_url: str) -> EventCandidatePayload:
    payload = candidate.model_dump(mode="json")
    payload["source_url"] = source_url
    return EventCandidatePayload.model_validate(payload)
