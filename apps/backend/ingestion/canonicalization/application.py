from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from events.models import Event, EventRevision

from ingestion.candidates import CandidateVersionConflict
from ingestion.canonicalization.event_mutations import apply_add, apply_update
from ingestion.canonicalization.proposal_validation import validate_proposal
from ingestion.canonicalization.provenance import link_observation
from ingestion.canonicalization.snapshots import event_snapshot, event_snapshot_hash
from ingestion.contracts import CanonicalizationAction, CanonicalizationProposal
from ingestion.models import CanonicalizationPlan, CanonicalizationPlanStatus


@dataclass(frozen=True)
class PlanResult:
    plan_id: int | None
    status: str
    event_id: int | None
    message: str = ""


def apply_canonicalization_plan(plan_id: int, *, expected_version: int) -> PlanResult:
    try:
        return _apply_canonicalization_plan(plan_id, expected_version=expected_version)
    except CandidateVersionConflict:
        raise
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"[:2000]
        CanonicalizationPlan.objects.filter(
            pk=plan_id,
            plan_version=expected_version,
        ).update(status=CanonicalizationPlanStatus.FAILED, application_error=message)
        return PlanResult(plan_id, CanonicalizationPlanStatus.FAILED, None, message)


@transaction.atomic
def _apply_canonicalization_plan(plan_id: int, *, expected_version: int) -> PlanResult:
    plan = (
        CanonicalizationPlan.objects.select_for_update()
        .select_related("event_candidate__source_representation")
        .get(pk=plan_id)
    )
    if plan.plan_version != expected_version:
        raise CandidateVersionConflict(
            f"Plan {plan_id} changed from version {expected_version} "
            f"to {plan.plan_version}; reload before applying."
        )
    if (
        plan.status == CanonicalizationPlanStatus.APPLIED
        and plan.applied_version == expected_version
    ):
        return PlanResult(plan.pk, plan.status, plan.target_event_id)
    if plan.status != CanonicalizationPlanStatus.READY:
        return PlanResult(plan.pk, plan.status, plan.target_event_id, "Plan is not ready.")

    proposal = CanonicalizationProposal.model_validate(plan.effective_proposal)
    issues = validate_proposal(plan.event_candidate, proposal)
    if issues:
        plan.validation_issues = issues
        plan.status = CanonicalizationPlanStatus.REJECTED
        plan.save(update_fields=("validation_issues", "status", "updated_at"))
        return PlanResult(plan.pk, plan.status, plan.target_event_id, "Plan validation failed.")

    target = None
    before: dict[str, Any] = {}
    if proposal.target_event_id is not None:
        target = Event.objects.select_for_update().get(pk=proposal.target_event_id)
        if event_snapshot_hash(target) != plan.target_snapshot_hash:
            plan.status = CanonicalizationPlanStatus.STALE
            plan.application_error = "The target Event changed after this plan was generated."
            plan.save(update_fields=("status", "application_error", "updated_at"))
            return PlanResult(plan.pk, plan.status, target.pk, plan.application_error)
        before = event_snapshot(target)

    if proposal.action == CanonicalizationAction.ADD:
        event = apply_add(plan, proposal.add_event)
    elif proposal.action == CanonicalizationAction.UPDATE:
        if target is None:
            raise RuntimeError("UPDATE plan has no target Event")
        event = apply_update(target, proposal)
    else:
        if target is None:
            raise RuntimeError("LINK_ONLY plan has no target Event")
        event = target

    link_observation(plan.event_candidate, event)
    after = event_snapshot(event)
    if proposal.action != CanonicalizationAction.LINK_ONLY:
        revision_number = (
            EventRevision.objects.filter(event=event).aggregate(maximum=Max("revision_number"))[
                "maximum"
            ]
            or 0
        ) + 1
        EventRevision.objects.create(
            event=event,
            canonicalization_plan=plan,
            revision_number=revision_number,
            before_snapshot=before,
            after_snapshot=after,
        )

    plan.target_event = event
    plan.target_event_updated_at = event.updated_at
    plan.target_snapshot_hash = event_snapshot_hash(event)
    plan.applied_snapshot = after
    plan.applied_version = plan.plan_version
    plan.applied_at = timezone.now()
    plan.status = CanonicalizationPlanStatus.APPLIED
    plan.application_error = ""
    plan.save()
    return PlanResult(plan.pk, plan.status, event.pk)


__all__ = ("PlanResult", "apply_canonicalization_plan")
