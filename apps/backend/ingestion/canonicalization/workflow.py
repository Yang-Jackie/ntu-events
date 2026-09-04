from __future__ import annotations

import hashlib
import json
from typing import Any

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from events.models import (
    Event,
)
from pydantic import ValidationError as PydanticValidationError

from ingestion.candidates import CandidateVersionConflict, parse_and_validate_candidate_payload
from ingestion.canonicalization.application import apply_canonicalization_plan
from ingestion.canonicalization.context import build_canonicalization_context, match_record
from ingestion.canonicalization.decision_provider import (
    CANONICALIZATION_PROMPT_VERSION,
    CanonicalizationDecisionProvider,
)
from ingestion.canonicalization.grounding import synthesis_flags
from ingestion.canonicalization.matching import find_candidate_matches
from ingestion.canonicalization.projection import automatic_add_proposal
from ingestion.canonicalization.proposal_validation import validate_proposal
from ingestion.canonicalization.snapshots import (
    event_snapshot_hash,
    event_snapshot_payload_hash,
)
from ingestion.contracts import (
    CANONICALIZATION_SCHEMA_VERSION,
    CanonicalizationProposal,
    EventCandidatePayload,
)
from ingestion.model_outputs import ModelOutputError
from ingestion.models import (
    CandidateMatch,
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
from ingestion.reference_data import (
    build_candidate_reference_data,
    candidate_reference_data_hash,
)


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


def canonicalize_candidate(
    candidate_id: int,
    *,
    expected_version: int,
    decision: CanonicalizationProposal | dict[str, Any] | None = None,
    model_invocation_id: int | None = None,
    domain_flags: list[dict[str, Any]] | None = None,
    grounding_flags: list[dict[str, Any]] | None = None,
    apply_ready: bool = True,
    precomputed_matches: list[CandidateMatch] | None = None,
    match_snapshot: list[dict[str, Any]] | None = None,
    target_snapshot_hashes: dict[int, str] | None = None,
) -> CanonicalizationPlan | None:
    """Match one READY candidate, create its sole plan, and optionally apply it."""
    with transaction.atomic():
        candidate = (
            EventCandidate.objects.select_for_update()
            .select_related("source_representation")
            .get(pk=candidate_id)
        )
        if candidate.edit_version != expected_version:
            raise CandidateVersionConflict(
                f"Candidate {candidate_id} changed from version {expected_version} "
                f"to {candidate.edit_version}; reload before canonicalizing."
            )
        existing = CanonicalizationPlan.objects.filter(event_candidate=candidate).first()
        if existing is not None:
            return existing
        if candidate.status != CandidateStatus.READY:
            return None

        reference_data = build_candidate_reference_data()
        payload, issues = parse_and_validate_candidate_payload(
            candidate.effective_payload,
            reference_data,
        )
        if payload is None or any(issue.get("blocks_canonicalization") for issue in issues):
            candidate.validation_issues = issues
            candidate.status = CandidateStatus.BLOCKED
            candidate.save(update_fields=("validation_issues", "status", "updated_at"))
            return None

        matches = (
            find_candidate_matches(candidate, payload)
            if precomputed_matches is None
            else precomputed_matches
        )
        frozen_match_snapshot = (
            [match_record(match) for match in matches] if match_snapshot is None else match_snapshot
        )
        parsed_decision: CanonicalizationProposal | None
        if decision is None and not matches:
            parsed_decision = automatic_add_proposal(payload)
        elif decision is None:
            parsed_decision = None
        else:
            parsed_decision = CanonicalizationProposal.model_validate(decision)

        if parsed_decision is None:
            plan = CanonicalizationPlan.objects.create(
                event_candidate=candidate,
                status=CanonicalizationPlanStatus.REVIEW_REQUIRED,
                match_snapshot=frozen_match_snapshot,
                model_invocation_id=model_invocation_id,
                domain_flags=domain_flags or [],
                grounding_flags=grounding_flags or [],
            )
        else:
            hard_issues = validate_proposal(candidate, parsed_decision, matches=matches)
            generated = parsed_decision.model_dump(mode="json")
            target = (
                Event.objects.filter(pk=parsed_decision.target_event_id).first()
                if parsed_decision.target_event_id is not None
                else None
            )
            target_snapshot_hash = ""
            if target is not None:
                target_snapshot_hash = (target_snapshot_hashes or {}).get(
                    target.pk
                ) or event_snapshot_hash(target)
            plan = CanonicalizationPlan.objects.create(
                event_candidate=candidate,
                action=parsed_decision.action.value,
                status=(
                    CanonicalizationPlanStatus.REJECTED
                    if hard_issues
                    else CanonicalizationPlanStatus.READY
                ),
                target_event=target,
                target_event_updated_at=target.updated_at if target else None,
                target_snapshot_hash=target_snapshot_hash,
                model_invocation_id=model_invocation_id,
                match_snapshot=frozen_match_snapshot,
                generated_proposal=generated,
                effective_proposal=generated,
                validation_issues=hard_issues,
                domain_flags=domain_flags or [],
                grounding_flags=(grounding_flags or []) + synthesis_flags(payload, parsed_decision),
            )

        candidate.status = CandidateStatus.PROCESSED
        candidate.processed_at = timezone.now()
        candidate.save(update_fields=("status", "processed_at", "updated_at"))

    if apply_ready and plan.status == CanonicalizationPlanStatus.READY:
        apply_canonicalization_plan(plan.pk, expected_version=plan.plan_version)
        plan.refresh_from_db()
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


def update_canonicalization_plan(
    plan_id: int,
    *,
    expected_version: int,
    effective_proposal: dict[str, Any],
    apply_ready: bool = True,
) -> CanonicalizationPlan:
    with transaction.atomic():
        plan = (
            CanonicalizationPlan.objects.select_for_update()
            .select_related("event_candidate")
            .get(pk=plan_id)
        )
        if plan.plan_version != expected_version:
            raise CandidateVersionConflict(
                f"Plan {plan_id} changed from version {expected_version} "
                f"to {plan.plan_version}; reload before saving again."
            )
        if plan.applied_version:
            raise CandidateVersionConflict(
                "Applied plans are immutable; edit the canonical Event instead."
            )
        issues = validate_proposal(plan.event_candidate, effective_proposal)
        parsed = None
        try:
            parsed = CanonicalizationProposal.model_validate(effective_proposal)
        except PydanticValidationError:
            pass
        plan.effective_proposal = effective_proposal
        plan.validation_issues = issues
        plan.has_manual_edits = True
        plan.plan_version += 1
        plan.applied_snapshot = {}
        plan.applied_at = None
        plan.application_error = ""
        if parsed is None:
            plan.action = ""
            plan.target_event = None
            plan.target_event_updated_at = None
            plan.target_snapshot_hash = ""
        else:
            plan.action = parsed.action.value
            plan.target_event = (
                Event.objects.filter(pk=parsed.target_event_id).first()
                if parsed.target_event_id is not None
                else None
            )
            plan.target_event_updated_at = (
                plan.target_event.updated_at if plan.target_event else None
            )
            plan.target_snapshot_hash = (
                event_snapshot_hash(plan.target_event) if plan.target_event else ""
            )
        plan.status = (
            CanonicalizationPlanStatus.REJECTED if issues else CanonicalizationPlanStatus.READY
        )
        plan.save()
    if apply_ready and plan.status == CanonicalizationPlanStatus.READY:
        apply_canonicalization_plan(plan.pk, expected_version=plan.plan_version)
        plan.refresh_from_db()
    return plan
