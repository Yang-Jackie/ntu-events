"""Prepare canonicalization decisions and retain matching/model evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from django.db.models import Max
from django.utils import timezone
from openai import APITimeoutError
from pydantic import ValidationError

from ingestion.canonicalization.decisions.context import (
    build_canonicalization_context,
    match_record,
)
from ingestion.canonicalization.decisions.matching import find_candidate_matches
from ingestion.canonicalization.decisions.projection import automatic_add_proposal
from ingestion.canonicalization.decisions.provider import (
    CANONICALIZATION_PROMPT_VERSION,
    CanonicalizationDecisionProvider,
)
from ingestion.canonicalization.snapshots import event_snapshot_payload_hash
from ingestion.contracts import (
    CANONICALIZATION_OUTPUT_SCHEMA_VERSION,
    CanonicalizationProposal,
    EventCandidatePayload,
)
from ingestion.model_outputs import ModelOutputError
from ingestion.models import (
    CandidateMatch,
    EventCandidate,
    ExtractionStatus,
    IngestionJob,
    ModelInvocation,
    ModelInvocationStage,
)
from ingestion.observability import log_context, log_event, logged_phase, usage_fields
from ingestion.raw_storage import RawContentStorage
from ingestion.reference_data import candidate_reference_data_hash

MAX_CANONICALIZATION_MODEL_ATTEMPTS = 3


@dataclass(frozen=True)
class DecisionResult:
    proposal: CanonicalizationProposal | dict[str, Any] | None
    matches: list[CandidateMatch]
    match_snapshot: list[dict[str, Any]]
    model_invocation_id: int | None = None
    target_snapshot_hashes: dict[int, str] = field(default_factory=dict)
    error: Exception | None = None

    @property
    def failure_event(self) -> str:
        return (
            "canonicalization.timeout_review"
            if isinstance(self.error, APITimeoutError)
            else "canonicalization.output_failure_review"
        )


def prepare_decision(
    candidate: EventCandidate,
    payload: EventCandidatePayload,
    *,
    proposal: CanonicalizationProposal | dict[str, Any] | None = None,
    matches: list[CandidateMatch] | None = None,
    match_snapshot: list[dict[str, Any]] | None = None,
    model_invocation_id: int | None = None,
    target_snapshot_hashes: dict[int, str] | None = None,
) -> DecisionResult:
    """Complete deterministic evidence and the no-match ADD under the workflow lock."""
    matches = find_candidate_matches(candidate, payload) if matches is None else matches
    snapshot = (
        [match_record(match) for match in matches] if match_snapshot is None else match_snapshot
    )
    if proposal is None and not matches:
        proposal = automatic_add_proposal(payload)
    return DecisionResult(
        proposal=proposal,
        matches=matches,
        match_snapshot=snapshot,
        model_invocation_id=model_invocation_id,
        target_snapshot_hashes=target_snapshot_hashes or {},
    )


def decide_candidate(
    candidate: EventCandidate,
    payload: EventCandidatePayload,
    *,
    decision_provider: CanonicalizationDecisionProvider,
    storage: RawContentStorage,
) -> DecisionResult:
    """Match and obtain a proposal without creating a plan or changing an Event."""
    with logged_phase("canonicalization.matching"):
        matches = find_candidate_matches(candidate, payload)
        match_snapshot = [match_record(match) for match in matches]
    log_event("canonicalization.matches", match_count=len(matches))
    if not matches:
        log_event("canonicalization.model_bypassed", reason="no_matches")
        return DecisionResult(proposal=None, matches=matches, match_snapshot=match_snapshot)

    with logged_phase("canonicalization.context"):
        raw_document = _load_raw_document(candidate, storage)
        context = build_canonicalization_context(
            candidate,
            payload,
            raw_document=raw_document,
            match_snapshot=match_snapshot,
        )
    result = None
    error: Exception | None = None
    serialized_context = json.dumps(
        context,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    job = _originating_job(candidate)
    invocation: ModelInvocation
    while True:
        attempt_number = _next_canonicalization_attempt(job, candidate.pk)
        started_at = timezone.now()
        result = None
        error = None
        try:
            with (
                log_context(job_id=job.pk, model_attempt=attempt_number),
                logged_phase("canonicalization.model_attempt"),
            ):
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

        invocation = ModelInvocation.objects.create(
            job=job,
            stage=ModelInvocationStage.CANONICALIZATION,
            model_name=decision_provider.model_name,
            prompt_version=CANONICALIZATION_PROMPT_VERSION,
            schema_version=CANONICALIZATION_OUTPUT_SCHEMA_VERSION,
            batch_index=candidate.pk,
            attempt_number=attempt_number,
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
        log_event(
            "canonicalization.invocation_recorded",
            job_id=job.pk,
            model_attempt=attempt_number,
            invocation_id=invocation.pk,
            status=invocation.status,
            error_type=invocation.error_type or None,
            response_id=response_identifier or None,
            **usage_fields(token_usage),
        )
        if error is None:
            break
        if isinstance(error, APITimeoutError):
            break
        if not isinstance(error, (ModelOutputError, ValidationError)):
            raise error
        if invocation.attempt_number >= MAX_CANONICALIZATION_MODEL_ATTEMPTS:
            break
        log_event("canonicalization.output_retry", next_model_attempt=attempt_number + 1)

    return DecisionResult(
        proposal=result.parsed if result else None,
        matches=matches,
        match_snapshot=match_snapshot,
        model_invocation_id=invocation.pk,
        target_snapshot_hashes={
            record["event_id"]: event_snapshot_payload_hash(record["event"])
            for record in match_snapshot
        },
        error=error,
    )


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
