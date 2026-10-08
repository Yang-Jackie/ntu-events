"""Candidate gates, plan persistence, validation, and owner repairs."""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone
from events.models import Event
from pydantic import ValidationError as PydanticValidationError

from ingestion.candidates.service import parse_and_validate_candidate_payload
from ingestion.canonicalization.plans.validation.proposal import validate_proposal
from ingestion.canonicalization.snapshots import event_snapshot_hash
from ingestion.contracts import (
    CanonicalizationProposal,
    EventCandidatePayload,
    EventField,
    FieldOperation,
)
from ingestion.errors import CandidateVersionConflict
from ingestion.models import (
    CandidateMatch,
    CandidateStatus,
    CanonicalizationPlan,
    CanonicalizationPlanStatus,
    EventCandidate,
)
from ingestion.observability import log_event, logged_phase
from ingestion.reference_data import build_candidate_reference_data


def prepare_candidate(
    candidate_id: int, *, expected_version: int
) -> tuple[EventCandidate, EventCandidatePayload | None, CanonicalizationPlan | None]:
    """Lock and revalidate a candidate inside the workflow's transaction."""
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
        return candidate, None, existing
    if candidate.status != CandidateStatus.READY:
        return candidate, None, None

    reference_data = build_candidate_reference_data()
    payload, issues = parse_and_validate_candidate_payload(
        candidate.effective_payload,
        reference_data,
    )
    if payload is None or any(issue.get("blocks_canonicalization") for issue in issues):
        candidate.validation_issues = issues
        candidate.status = CandidateStatus.BLOCKED
        candidate.save(update_fields=("validation_issues", "status", "updated_at"))
        return candidate, None, None

    return candidate, payload, None


def create_plan(
    candidate: EventCandidate,
    payload: EventCandidatePayload,
    *,
    decision: CanonicalizationProposal | dict[str, Any] | None,
    matches: list[CandidateMatch],
    frozen_match_snapshot: list[dict[str, Any]],
    model_invocation_id: int | None = None,
    target_snapshot_hashes: dict[int, str] | None = None,
    domain_flags: list[dict[str, Any]] | None = None,
    grounding_flags: list[dict[str, Any]] | None = None,
) -> CanonicalizationPlan:
    """Persist the sole plan and freeze the locked candidate; never apply it."""
    parsed_decision: CanonicalizationProposal | None
    invalid_decision_issues = []
    invalid_decision_payload = {}
    if decision is None:
        parsed_decision = None
    else:
        try:
            parsed_decision = CanonicalizationProposal.model_validate(decision)
        except PydanticValidationError:
            parsed_decision = None
            invalid_decision_issues = validate_proposal(candidate, decision, matches=matches)
            invalid_decision_payload = (
                decision.model_dump(mode="json")
                if isinstance(decision, CanonicalizationProposal)
                else decision
            )

    if parsed_decision is None:
        plan = CanonicalizationPlan.objects.create(
            event_candidate=candidate,
            status=(
                CanonicalizationPlanStatus.REJECTED
                if invalid_decision_issues
                else CanonicalizationPlanStatus.REVIEW_REQUIRED
            ),
            generated_proposal=invalid_decision_payload,
            effective_proposal=invalid_decision_payload,
            validation_issues=invalid_decision_issues,
            match_snapshot=frozen_match_snapshot,
            model_invocation_id=model_invocation_id,
            domain_flags=domain_flags or [],
            grounding_flags=grounding_flags or [],
        )
    else:
        with logged_phase("canonicalization.proposal_validation"):
            hard_issues = validate_proposal(candidate, parsed_decision, matches=matches)
        log_event("canonicalization.proposal_validated", issue_count=len(hard_issues))
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

    return plan


def update_plan(
    plan_id: int,
    *,
    expected_version: int,
    effective_proposal: dict[str, Any],
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
    return plan


def record_decision_failure(plan: CanonicalizationPlan, error: Exception) -> None:
    plan.application_error = f"Canonicalization model failed: {error}"[:2000]
    plan.status = CanonicalizationPlanStatus.REVIEW_REQUIRED
    plan.save(update_fields=("application_error", "status", "updated_at"))


def synthesis_flags(payload, proposal) -> list[dict[str, Any]]:
    descriptions: list[str] = []
    if proposal.add_event and proposal.add_event.description:
        descriptions.append(proposal.add_event.description)
    descriptions.extend(
        change.value
        for change in proposal.event_changes
        if change.field == EventField.DESCRIPTION
        and change.operation == FieldOperation.SET
        and change.value
    )
    source_description = (payload.description or "").strip()
    return [
        {
            "code": "SYNTHESIZED_DESCRIPTION",
            "path": "description",
            "message": (
                "The proposed description is synthesized rather than copied from the candidate."
            ),
        }
        for description in descriptions
        if description.strip() != source_description
    ]
