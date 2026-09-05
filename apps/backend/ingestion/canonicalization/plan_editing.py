from __future__ import annotations

from typing import Any

from django.db import transaction
from events.models import Event
from pydantic import ValidationError as PydanticValidationError

from ingestion.candidates import CandidateVersionConflict
from ingestion.canonicalization.application import apply_canonicalization_plan
from ingestion.canonicalization.proposal_validation import validate_proposal
from ingestion.canonicalization.snapshots import event_snapshot_hash
from ingestion.contracts import CanonicalizationProposal
from ingestion.models import CanonicalizationPlan, CanonicalizationPlanStatus


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
