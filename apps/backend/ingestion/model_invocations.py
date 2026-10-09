"""Persist model attempt evidence without owning execution or retry policy."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ingestion.model_outputs import ModelOutputError, ModelResult
from ingestion.models import ExtractionStatus, IngestionJob, ModelInvocation
from ingestion.raw_storage import RawContentStorage


def record_model_invocation(
    *,
    job: IngestionJob,
    stage: str,
    model_name: str,
    prompt_version: str,
    schema_version: str,
    batch_index: int,
    attempt_number: int,
    started_at: datetime,
    completed_at: datetime,
    input_hash: str,
    storage: RawContentStorage,
    result: ModelResult | None,
    error: Exception | None,
    reference_data_hash: str = "",
    reference_data_snapshot: dict[str, Any] | None = None,
) -> ModelInvocation:
    artifact = result if result is not None else error
    raw_output_key = ""
    response_identifier = ""
    token_usage: dict[str, Any] = {}
    if isinstance(artifact, (ModelResult, ModelOutputError)):
        raw_output_key = storage.save(artifact.raw_response, suffix=".json").storage_key
        response_identifier = artifact.response_identifier
        token_usage = artifact.token_usage

    return ModelInvocation.objects.create(
        job=job,
        stage=stage,
        model_name=model_name,
        prompt_version=prompt_version,
        schema_version=schema_version,
        batch_index=batch_index,
        attempt_number=attempt_number,
        status=ExtractionStatus.SUCCEEDED if result is not None else ExtractionStatus.FAILED,
        started_at=started_at,
        completed_at=completed_at,
        response_identifier=response_identifier,
        input_hash=input_hash,
        reference_data_hash=reference_data_hash,
        reference_data_snapshot=reference_data_snapshot or {},
        raw_output_storage_key=raw_output_key,
        token_usage=token_usage,
        error_type=type(error).__name__ if error is not None else "",
        error_message=str(error) if error is not None else "",
    )
