"""Public orchestration for candidate processing and plan repair/application."""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction

from ingestion.canonicalization.application.service import apply_canonicalization_plan
from ingestion.canonicalization.decisions.provider import CanonicalizationDecisionProvider
from ingestion.canonicalization.decisions.service import decide_candidate, prepare_decision
from ingestion.canonicalization.plans.service import (
    create_plan,
    prepare_candidate,
    record_decision_failure,
    update_plan,
)
from ingestion.contracts import CanonicalizationProposal, EventCandidatePayload
from ingestion.models import (
    CandidateMatch,
    CandidateStatus,
    CanonicalizationPlan,
    CanonicalizationPlanStatus,
    EventCandidate,
)
from ingestion.observability import log_context, log_event, logged_phase
from ingestion.raw_storage import RawContentStorage


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
    """Create a candidate's sole plan, then optionally apply it after committing."""
    with (
        log_context(candidate_id=candidate_id),
        logged_phase("canonicalization.plan_preparation"),
        transaction.atomic(),
    ):
        candidate, payload, existing = prepare_candidate(
            candidate_id, expected_version=expected_version
        )
        if existing is not None:
            return existing
        if payload is None:
            return None
        prepared = prepare_decision(
            candidate,
            payload,
            proposal=decision,
            matches=precomputed_matches,
            match_snapshot=match_snapshot,
            model_invocation_id=model_invocation_id,
            target_snapshot_hashes=target_snapshot_hashes,
        )
        plan = create_plan(
            candidate,
            payload,
            decision=prepared.proposal,
            matches=prepared.matches,
            frozen_match_snapshot=prepared.match_snapshot,
            model_invocation_id=prepared.model_invocation_id,
            target_snapshot_hashes=prepared.target_snapshot_hashes,
            domain_flags=domain_flags,
            grounding_flags=grounding_flags,
        )
    if apply_ready and plan.status == CanonicalizationPlanStatus.READY:
        with logged_phase(
            "canonicalization.application", candidate_id=candidate_id, plan_id=plan.pk
        ):
            apply_canonicalization_plan(plan.pk, expected_version=plan.plan_version)
        plan.refresh_from_db()
    log_event(
        "canonicalization.plan_finished",
        candidate_id=candidate_id,
        plan_id=plan.pk,
        status=plan.status,
    )
    return plan


def process_candidate(
    *,
    candidate_id: int,
    decision_provider: CanonicalizationDecisionProvider,
    storage: RawContentStorage,
) -> CanonicalizationPlan | None:
    """Run the complete source-neutral READY-candidate canonicalization workflow."""
    with log_context(candidate_id=candidate_id), logged_phase("canonicalization.candidate"):
        candidate = EventCandidate.objects.select_related(
            "source_representation",
            "extraction_run__model_invocation__job",
            "extraction_run__raw_source_document__ingestion_job",
        ).get(pk=candidate_id)
        if candidate.status != CandidateStatus.READY:
            return None
        payload = EventCandidatePayload.model_validate(candidate.effective_payload)
        decision = decide_candidate(
            candidate, payload, decision_provider=decision_provider, storage=storage
        )
        plan = canonicalize_candidate(
            candidate.pk,
            expected_version=candidate.edit_version,
            decision=decision.proposal,
            model_invocation_id=decision.model_invocation_id,
            precomputed_matches=decision.matches,
            match_snapshot=decision.match_snapshot,
            target_snapshot_hashes=decision.target_snapshot_hashes,
        )
        if plan is not None and decision.error is not None:
            record_decision_failure(plan, decision.error)
            log_event(
                decision.failure_event,
                level=logging.WARNING,
                plan_id=plan.pk,
                status=plan.status,
                error_type=type(decision.error).__name__,
                continuing=True,
            )
        return plan


def update_canonicalization_plan(
    plan_id: int,
    *,
    expected_version: int,
    effective_proposal: dict[str, Any],
    apply_ready: bool = True,
) -> CanonicalizationPlan:
    """Repair a plan, then optionally apply it after committing the repair."""
    plan = update_plan(
        plan_id, expected_version=expected_version, effective_proposal=effective_proposal
    )
    if apply_ready and plan.status == CanonicalizationPlanStatus.READY:
        apply_canonicalization_plan(plan.pk, expected_version=plan.plan_version)
        plan.refresh_from_db()
    return plan
