from __future__ import annotations

from ingestion.contracts import (
    SCREENING_SCHEMA_VERSION,
    ScreeningBatch,
    ScreeningLabel,
)
from ingestion.models import (
    IngestionJob,
    MessageScreening,
    ModelInvocation,
    ModelInvocationStage,
    ScreeningDecision,
)
from ingestion.pipelines.telegram.documents import MessageWork, ensure_raw_document
from ingestion.pipelines.telegram.model_client import (
    SCREENING_PROMPT_VERSION,
    OpenAITelegramModels,
)
from ingestion.pipelines.telegram.stage_runtime import BatchOutcome, heartbeat, run_batches
from ingestion.raw_storage import RawContentStorage


def screen_messages(
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
            item.raw_document = cached.raw_source_document or ensure_raw_document(
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
                raw_document = ensure_raw_document(item, job, storage)
                item.raw_document = raw_document
                relevant[item.representation.pk] = item
            MessageScreening.objects.update_or_create(
                job=job,
                source_representation=item.representation,
                defaults={
                    "model_invocation": invocation,
                    "raw_source_document": raw_document,
                    "content_hash": item.message.content_hash,
                    "decision": result.decision.value,
                    "reason": result.reason,
                    "confidence": result.confidence,
                },
            )

    def failed(outcome: BatchOutcome[ScreeningBatch], invocation: ModelInvocation) -> None:
        for message in outcome.messages:
            item = by_identity[message.identity]
            raw_document = ensure_raw_document(item, job, storage)
            MessageScreening.objects.update_or_create(
                job=job,
                source_representation=item.representation,
                defaults={
                    "model_invocation": invocation,
                    "raw_source_document": raw_document,
                    "content_hash": item.message.content_hash,
                    "decision": ScreeningDecision.FAILED,
                    "reason": str(outcome.error)[:500],
                    "confidence": None,
                },
            )
            failure_ids.add(message.identity)

    run_batches(
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
    heartbeat(job)
    return list(relevant.values()), failure_ids
