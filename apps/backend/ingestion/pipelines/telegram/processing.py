from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from functools import partial
from typing import Any

from django.db import transaction
from django.utils import timezone
from pydantic import BaseModel, ValidationError
from sources.models import ProcessingStatus, RawSourceDocument, SourceRepresentation

from ingestion.candidate_reviews import create_review_and_sync
from ingestion.contracts import (
    CANDIDATE_SCHEMA_VERSION,
    EXTRACTION_SCHEMA_VERSION,
    SCREENING_SCHEMA_VERSION,
    EventCandidatePayload,
    ExtractionBatch,
    ScreeningBatch,
    ScreeningLabel,
)
from ingestion.models import (
    EventCandidate,
    ExtractionRun,
    ExtractionStatus,
    IngestionJob,
    JobStatus,
    MessageScreening,
    ModelInvocation,
    ModelInvocationStage,
    ScreeningDecision,
)
from ingestion.pipelines.telegram.adapter import TelegramMessage
from ingestion.pipelines.telegram.extraction import (
    EXTRACTION_PROMPT_VERSION,
    SCREENING_PROMPT_VERSION,
    ModelOutputError,
    ModelResult,
    OpenAITelegramModels,
    batch_input_hash,
)
from ingestion.raw_storage import RawContentStorage
from ingestion.reference_data import (
    build_candidate_reference_data,
    candidate_reference_data_hash,
)
from ingestion.validation import validate_candidate

TELEGRAM_EXTRACTOR_TYPE = "telegram-llm"
TELEGRAM_EXTRACTOR_VERSION = "telegram-m4-v2"


@dataclass
class MessageWork:
    message: TelegramMessage
    representation: SourceRepresentation
    raw_document: RawSourceDocument | None = None


@dataclass(frozen=True)
class BatchOutcome[ParsedT: BaseModel]:
    batch_index: int
    messages: list[TelegramMessage]
    started_at: Any
    completed_at: Any
    result: ModelResult[ParsedT] | None
    error: Exception | None


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
    work = [_upsert_representation(job, message) for message in messages]
    relevant, screening_failure_ids = _screen_messages(
        job=job,
        work=work,
        models=models,
        storage=storage,
        concurrency=options["openai_concurrency"],
        batch_size=options["screening_batch_size"],
    )
    extraction_failure_ids, candidates_created, items_extracted = _extract_messages(
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


def _screen_messages(
    *,
    job: IngestionJob,
    work: list[MessageWork],
    models: OpenAITelegramModels,
    storage: RawContentStorage,
    concurrency: int,
    batch_size: int,
) -> tuple[list[MessageWork], set[str]]:
    relevant: dict[int, MessageWork] = {}
    pending: list[MessageWork] = []
    for item in work:
        cached = (
            MessageScreening.objects.filter(
                source_representation=item.representation,
                content_hash=item.message.content_hash,
                model_invocation__model_name=models.screening_model,
                model_invocation__prompt_version=SCREENING_PROMPT_VERSION,
                model_invocation__schema_version=SCREENING_SCHEMA_VERSION,
            )
            .exclude(decision=ScreeningDecision.FAILED)
            .order_by("-created_at")
            .first()
        )
        if cached is None:
            pending.append(item)
            continue
        if cached.decision in (ScreeningDecision.EVENT, ScreeningDecision.UNCERTAIN):
            item.raw_document = cached.raw_source_document or _ensure_raw_document(
                item, job, storage
            )
            relevant[item.representation.pk] = item

    by_identity = {item.message.identity: item for item in pending}
    failure_ids: set[str] = set()

    def success(outcome: BatchOutcome[ScreeningBatch], invocation: ModelInvocation) -> None:
        model_result = outcome.result
        if model_result is None:
            raise RuntimeError("Successful screening outcome is missing its model result")
        for result in model_result.parsed.results:
            item = by_identity[result.message_identity]
            raw_document = None
            if result.decision in (ScreeningLabel.EVENT, ScreeningLabel.UNCERTAIN):
                raw_document = _ensure_raw_document(item, job, storage)
                item.raw_document = raw_document
                relevant[item.representation.pk] = item
            MessageScreening.objects.create(
                job=job,
                model_invocation=invocation,
                source_representation=item.representation,
                raw_source_document=raw_document,
                content_hash=item.message.content_hash,
                decision=result.decision.value,
                reason=result.reason,
                confidence=result.confidence,
            )

    def failed(outcome: BatchOutcome[ScreeningBatch], invocation: ModelInvocation) -> None:
        for message in outcome.messages:
            item = by_identity[message.identity]
            raw_document = _ensure_raw_document(item, job, storage)
            MessageScreening.objects.create(
                job=job,
                model_invocation=invocation,
                source_representation=item.representation,
                raw_source_document=raw_document,
                content_hash=item.message.content_hash,
                decision=ScreeningDecision.FAILED,
                reason=str(outcome.error)[:500],
            )
            failure_ids.add(message.identity)

    _run_batches(
        job=job,
        messages=[item.message for item in pending],
        batch_size=batch_size,
        concurrency=concurrency,
        stage=ModelInvocationStage.SCREENING,
        model_name=models.screening_model,
        prompt_version=SCREENING_PROMPT_VERSION,
        schema_version=SCREENING_SCHEMA_VERSION,
        call=models.screen,
        storage=storage,
        on_success=success,
        on_final_failure=failed,
    )
    _heartbeat(job)
    return list(relevant.values()), failure_ids


def _extract_messages(
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
    reference_data_hash = candidate_reference_data_hash(reference_data)
    pending: list[MessageWork] = []
    for item in relevant:
        if item.raw_document is None:
            raise RuntimeError("Relevant messages must have a preserved raw document")
        already_extracted = ExtractionRun.objects.filter(
            raw_source_document=item.raw_document,
            extractor_type=TELEGRAM_EXTRACTOR_TYPE,
            extractor_version=TELEGRAM_EXTRACTOR_VERSION,
            model_name=models.extraction_model,
            prompt_version=EXTRACTION_PROMPT_VERSION,
            model_invocation__schema_version=EXTRACTION_SCHEMA_VERSION,
            model_invocation__reference_data_hash=reference_data_hash,
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
                    validation = validate_candidate(candidate, reference_data)
                    event_candidate = EventCandidate.objects.create(
                        extraction_run=extraction,
                        source_representation=item.representation,
                        candidate_index=index,
                        schema_version=CANDIDATE_SCHEMA_VERSION,
                        payload=candidate.model_dump(mode="json"),
                        title=candidate.title or "",
                        overall_confidence=candidate.overall_confidence,
                        validation_status=validation.status,
                        validation_issues=validation.issues,
                    )
                    create_review_and_sync(event_candidate, reference_data=reference_data)
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

    _run_batches(
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
    _heartbeat(job)
    return failure_ids, candidates_created, items_extracted


def _run_batches[ParsedT: BaseModel](
    *,
    job: IngestionJob,
    messages: list[TelegramMessage],
    batch_size: int,
    concurrency: int,
    stage: str,
    model_name: str,
    prompt_version: str,
    schema_version: str,
    call: Callable[[list[TelegramMessage]], ModelResult[ParsedT]],
    storage: RawContentStorage,
    reference_data: dict[str, Any] | None = None,
    on_success: Callable[[BatchOutcome[ParsedT], ModelInvocation], None],
    on_final_failure: Callable[[BatchOutcome[ParsedT], ModelInvocation], None],
) -> None:
    initial = [
        messages[index : index + batch_size] for index in range(0, len(messages), batch_size)
    ]
    if not initial:
        return
    next_index = 0
    futures: dict[Future, tuple[int, list[TelegramMessage], Any]] = {}
    with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="openai-ingestion") as pool:
        for batch in initial:
            started_at = timezone.now()
            futures[pool.submit(call, batch)] = (next_index, batch, started_at)
            next_index += 1
        while futures:
            completed, _pending = wait(futures, return_when="FIRST_COMPLETED")
            for future in completed:
                batch_index, batch, started_at = futures.pop(future)
                completed_at = timezone.now()
                try:
                    result = future.result()
                    error = None
                except Exception as exc:  # provider, parsing, or identity mismatch
                    result = None
                    error = exc
                outcome = BatchOutcome(
                    batch_index=batch_index,
                    messages=batch,
                    started_at=started_at,
                    completed_at=completed_at,
                    result=result,
                    error=error,
                )
                invocation = _record_invocation(
                    job=job,
                    outcome=outcome,
                    stage=stage,
                    model_name=model_name,
                    prompt_version=prompt_version,
                    schema_version=schema_version,
                    storage=storage,
                    reference_data=reference_data,
                )
                if result is not None:
                    on_success(outcome, invocation)
                elif len(batch) > 1 and _should_split(error):
                    midpoint = len(batch) // 2
                    for split in (batch[:midpoint], batch[midpoint:]):
                        split_started = timezone.now()
                        futures[pool.submit(call, split)] = (next_index, split, split_started)
                        next_index += 1
                else:
                    on_final_failure(outcome, invocation)
                _heartbeat(job)


def _record_invocation(
    *,
    job: IngestionJob,
    outcome: BatchOutcome,
    stage: str,
    model_name: str,
    prompt_version: str,
    schema_version: str,
    storage: RawContentStorage,
    reference_data: dict[str, Any] | None,
) -> ModelInvocation:
    raw_output_key = ""
    response_identifier = ""
    token_usage: dict = {}
    if outcome.result is not None:
        raw_output_key = storage.save(outcome.result.raw_response, suffix=".json").storage_key
        response_identifier = outcome.result.response_identifier
        token_usage = outcome.result.token_usage
    elif isinstance(outcome.error, ModelOutputError):
        raw_output_key = storage.save(outcome.error.raw_response, suffix=".json").storage_key
        response_identifier = outcome.error.response_identifier
        token_usage = outcome.error.token_usage
    reference_data_snapshot = reference_data or {}
    reference_hash = (
        candidate_reference_data_hash(reference_data_snapshot) if reference_data_snapshot else ""
    )
    return ModelInvocation.objects.create(
        job=job,
        stage=stage,
        model_name=model_name,
        prompt_version=prompt_version,
        schema_version=schema_version,
        batch_index=outcome.batch_index,
        attempt_number=job.attempt_count,
        status=(ExtractionStatus.SUCCEEDED if outcome.result else ExtractionStatus.FAILED),
        started_at=outcome.started_at,
        completed_at=outcome.completed_at,
        response_identifier=response_identifier,
        input_hash=batch_input_hash(
            outcome.messages,
            model=model_name,
            prompt_version=prompt_version,
            schema_version=schema_version,
            reference_data_hash=reference_hash,
        ),
        reference_data_hash=reference_hash,
        reference_data_snapshot=reference_data_snapshot,
        raw_output_storage_key=raw_output_key,
        token_usage=token_usage,
        error_type=(type(outcome.error).__name__ if outcome.error else ""),
        error_message=(str(outcome.error) if outcome.error else ""),
    )


def _upsert_representation(job: IngestionJob, message: TelegramMessage) -> MessageWork:
    representation, _created = SourceRepresentation.objects.get_or_create(
        source=job.source,
        external_identifier=message.identity,
        defaults={
            "source_url": message.source_url,
            "published_at": message.published_at,
            "content_type": "application/vnd.telegram.message+json",
            "first_seen_at": message.retrieved_at,
            "last_seen_at": message.retrieved_at,
            "metadata": _message_metadata(message),
        },
    )
    if not _created:
        representation.source_url = message.source_url
        representation.published_at = message.published_at
        representation.last_seen_at = message.retrieved_at
        representation.metadata = _message_metadata(message)
        representation.save(
            update_fields=("source_url", "published_at", "last_seen_at", "metadata")
        )
    return MessageWork(message=message, representation=representation)


def _ensure_raw_document(
    item: MessageWork,
    job: IngestionJob,
    storage: RawContentStorage,
) -> RawSourceDocument:
    existing = RawSourceDocument.objects.filter(
        source_representation=item.representation,
        metadata__message_content_hash=item.message.content_hash,
    ).first()
    if existing:
        return existing
    stored = storage.save(item.message.raw_bytes(), suffix=".json")
    return RawSourceDocument.objects.create(
        source_representation=item.representation,
        ingestion_job=job,
        fetched_at=item.message.retrieved_at,
        storage_key=stored.storage_key,
        content_hash=stored.content_hash,
        language="en",
        processing_status=ProcessingStatus.PENDING,
        metadata={
            "source_kind": "telegram_message",
            "message_content_hash": item.message.content_hash,
        },
    )


def _trusted_source_url(candidate: EventCandidatePayload, source_url: str) -> EventCandidatePayload:
    payload = candidate.model_dump(mode="json")
    payload["source_url"] = source_url
    return EventCandidatePayload.model_validate(payload)


def _message_metadata(message: TelegramMessage) -> dict[str, Any]:
    return {
        "channel_id": message.channel_id,
        "channel_username": message.channel_username,
        "edited_at": message.edited_at.isoformat() if message.edited_at else None,
        "reply_to_message_id": message.reply_to_message_id,
        "forwarded_from": message.forwarded_from,
        "content_hash": message.content_hash,
    }


def _heartbeat(job: IngestionJob) -> None:
    now = timezone.now()
    IngestionJob.objects.filter(pk=job.pk, status=JobStatus.RUNNING).update(heartbeat_at=now)
    job.heartbeat_at = now


def _should_split(error: Exception | None) -> bool:
    return isinstance(error, (ValueError, ValidationError))
