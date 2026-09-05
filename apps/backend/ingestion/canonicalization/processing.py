from __future__ import annotations

import hashlib
import json
from typing import Any

from django.db.models import Max
from django.utils import timezone

from ingestion.canonicalization.context import build_canonicalization_context, match_record
from ingestion.canonicalization.decision_provider import (
    CANONICALIZATION_PROMPT_VERSION,
    CanonicalizationDecisionProvider,
)
from ingestion.canonicalization.matching import find_candidate_matches
from ingestion.canonicalization.planning import canonicalize_candidate
from ingestion.canonicalization.snapshots import event_snapshot_payload_hash
from ingestion.contracts import CANONICALIZATION_SCHEMA_VERSION, EventCandidatePayload
from ingestion.model_outputs import ModelOutputError
from ingestion.models import (
    CandidateStatus,
    CanonicalizationPlan,
    CanonicalizationPlanStatus,
    EventCandidate,
    ExtractionStatus,
    IngestionJob,
    ModelInvocation,
    ModelInvocationStage,
)
from ingestion.raw_storage import RawContentStorage
from ingestion.reference_data import candidate_reference_data_hash


def process_candidate(
    *,
    candidate_id: int,
    decision_provider: CanonicalizationDecisionProvider,
    storage: RawContentStorage,
) -> CanonicalizationPlan | None:
    """Run the complete source-neutral READY-candidate canonicalization workflow."""
    candidate = EventCandidate.objects.select_related(
        "source_representation",
        "extraction_run__model_invocation__job",
        "extraction_run__raw_source_document__ingestion_job",
    ).get(pk=candidate_id)
    if candidate.status != CandidateStatus.READY:
        return None
    payload = EventCandidatePayload.model_validate(candidate.effective_payload)
    matches = find_candidate_matches(candidate, payload)
    match_snapshot = [match_record(match) for match in matches]
    if not matches:
        return canonicalize_candidate(
            candidate.pk,
            expected_version=candidate.edit_version,
            precomputed_matches=matches,
            match_snapshot=match_snapshot,
        )

    raw_document = _load_raw_document(candidate, storage)
    context = build_canonicalization_context(
        candidate,
        payload,
        raw_document=raw_document,
        match_snapshot=match_snapshot,
    )
    started_at = timezone.now()
    result = None
    error: Exception | None = None
    try:
        result = decision_provider.decide(context)
    except Exception as exc:
        error = exc
    completed_at = timezone.now()

    raw_output_key = ""
    response_identifier = ""
    token_usage: dict[str, Any] = {}
    if result is not None:
        raw_output_key = storage.save(result.raw_response, suffix=".json").storage_key
        response_identifier = result.response_identifier
        token_usage = result.token_usage
    elif isinstance(error, ModelOutputError):
        raw_output_key = storage.save(error.raw_response, suffix=".json").storage_key
        response_identifier = error.response_identifier
        token_usage = error.token_usage

    serialized_context = json.dumps(
        context,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    job = _originating_job(candidate)
    invocation = ModelInvocation.objects.create(
        job=job,
        stage=ModelInvocationStage.CANONICALIZATION,
        model_name=decision_provider.model_name,
        prompt_version=CANONICALIZATION_PROMPT_VERSION,
        schema_version=CANONICALIZATION_SCHEMA_VERSION,
        batch_index=candidate.pk,
        attempt_number=_next_canonicalization_attempt(job, candidate.pk),
        status=ExtractionStatus.SUCCEEDED if result else ExtractionStatus.FAILED,
        started_at=started_at,
        completed_at=completed_at,
        response_identifier=response_identifier,
        input_hash=hashlib.sha256(serialized_context.encode("utf-8")).hexdigest(),
        reference_data_hash=candidate_reference_data_hash(context["catalog"]),
        reference_data_snapshot=context["catalog"],
        raw_output_storage_key=raw_output_key,
        token_usage=token_usage,
        error_type=type(error).__name__ if error else "",
        error_message=str(error) if error else "",
    )
    if error is not None and not isinstance(error, ModelOutputError):
        raise error
    plan = canonicalize_candidate(
        candidate.pk,
        expected_version=candidate.edit_version,
        decision=result.parsed if result else None,
        model_invocation_id=invocation.pk,
        precomputed_matches=matches,
        match_snapshot=match_snapshot,
        target_snapshot_hashes={
            record["event_id"]: event_snapshot_payload_hash(record["event"])
            for record in match_snapshot
        },
    )
    if plan is not None and error is not None:
        plan.application_error = f"Canonicalization model failed: {error}"[:2000]
        plan.status = CanonicalizationPlanStatus.REVIEW_REQUIRED
        plan.save(update_fields=("application_error", "status", "updated_at"))
    return plan


def _load_raw_document(
    candidate: EventCandidate,
    storage: RawContentStorage,
) -> dict[str, Any]:
    storage_key = candidate.extraction_run.raw_source_document.storage_key
    payload = json.loads(storage.load(storage_key))
    if not isinstance(payload, dict):
        raise ValueError(f"Raw document {storage_key!r} must contain a JSON object")
    return payload


def _originating_job(candidate: EventCandidate) -> IngestionJob:
    invocation = candidate.extraction_run.model_invocation
    if invocation is not None:
        return invocation.job
    job = candidate.extraction_run.raw_source_document.ingestion_job
    if job is None:
        raise RuntimeError(
            f"Candidate {candidate.pk} has no originating ingestion job for model provenance"
        )
    return job


def _next_canonicalization_attempt(job: IngestionJob, candidate_id: int) -> int:
    latest = ModelInvocation.objects.filter(
        job=job,
        stage=ModelInvocationStage.CANONICALIZATION,
        batch_index=candidate_id,
    ).aggregate(latest=Max("attempt_number"))["latest"]
    return (latest or 0) + 1
