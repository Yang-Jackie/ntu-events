from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone
from events.models import Event

from ingestion.candidates import CandidateVersionConflict, parse_and_validate_candidate_payload
from ingestion.canonicalization.application import apply_canonicalization_plan
from ingestion.canonicalization.context import match_record
from ingestion.canonicalization.grounding import synthesis_flags
from ingestion.canonicalization.matching import find_candidate_matches
from ingestion.canonicalization.projection import automatic_add_proposal
from ingestion.canonicalization.proposal_validation import validate_proposal
from ingestion.canonicalization.snapshots import event_snapshot_hash
from ingestion.contracts import CanonicalizationProposal
from ingestion.models import (
    CandidateMatch,
    CandidateStatus,
    CanonicalizationPlan,
    CanonicalizationPlanStatus,
    EventCandidate,
)
from ingestion.reference_data import build_candidate_reference_data


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
