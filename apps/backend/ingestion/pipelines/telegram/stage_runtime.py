from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from typing import Any

from django.utils import timezone
from pydantic import BaseModel, ValidationError

from ingestion.model_outputs import ModelOutputError, ModelResult
from ingestion.models import (
    ExtractionStatus,
    IngestionJob,
    JobStatus,
    ModelInvocation,
)
from ingestion.pipelines.telegram.adapter import TelegramMessage
from ingestion.pipelines.telegram.model_client import (
    batch_input_hash,
)
from ingestion.raw_storage import RawContentStorage
from ingestion.reference_data import (
    candidate_reference_data_hash,
)


@dataclass(frozen=True)
class BatchOutcome[ParsedT: BaseModel]:
    batch_index: int
    messages: list[TelegramMessage]
    started_at: Any
    completed_at: Any
    result: ModelResult[ParsedT] | None
    error: Exception | None


def run_batches[ParsedT: BaseModel](
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
                heartbeat(job)


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


def heartbeat(job: IngestionJob) -> None:
    now = timezone.now()
    IngestionJob.objects.filter(pk=job.pk, status=JobStatus.RUNNING).update(heartbeat_at=now)
    job.heartbeat_at = now


def _should_split(error: Exception | None) -> bool:
    return isinstance(error, (ValueError, ValidationError))
