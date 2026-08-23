from __future__ import annotations

from typing import Any

from django.db import transaction
from django.utils import timezone
from pydantic import ValidationError as PydanticValidationError
from sources.models import SourceRepresentation

from ingestion.candidate_validation import validate_candidate
from ingestion.contracts import EventCandidatePayload
from ingestion.models import CandidateStatus, EventCandidate, ExtractionRun
from ingestion.reference_data import build_candidate_reference_data


class CandidateVersionConflict(RuntimeError):
    pass


def create_extracted_candidate(
    *,
    extraction_run: ExtractionRun,
    source_representation: SourceRepresentation,
    candidate_index: int,
    payload: EventCandidatePayload,
    reference_data: dict[str, Any] | None = None,
) -> EventCandidate:
    """Persist the source-neutral handoff from extraction to candidate processing."""
    reference_data = reference_data or build_candidate_reference_data()
    validation = validate_candidate(payload, reference_data)
    serialized = payload.model_dump(mode="json")
    return EventCandidate.objects.create(
        extraction_run=extraction_run,
        source_representation=source_representation,
        candidate_index=candidate_index,
        schema_version=payload.schema_version,
        observation_type=payload.observation_type.value,
        extracted_payload=serialized,
        effective_payload=serialized,
        title=payload.title or "",
        overall_confidence=payload.overall_confidence,
        status=candidate_status_for_issues(validation.issues),
        validation_issues=validation.issues,
    )


@transaction.atomic
def update_event_candidate(
    candidate_id: int,
    *,
    expected_version: int,
    effective_payload: dict[str, Any],
    reviewer_notes: str,
    edited_by_id: int | None,
    reference_data: dict[str, Any] | None = None,
) -> EventCandidate:
    """Repair a blocked candidate and make a valid repair eligible for processing.

    A valid repair transitions BLOCKED to READY. The canonicalization worker
    consumes READY candidates regardless of whether extraction or a reviewer
    produced that state.
    """
    candidate = EventCandidate.objects.select_for_update().get(pk=candidate_id)
    if candidate.edit_version != expected_version:
        raise CandidateVersionConflict(
            f"Candidate {candidate_id} changed from version {expected_version} "
            f"to {candidate.edit_version}; reload before saving again."
        )
    if candidate.status != CandidateStatus.BLOCKED:
        raise CandidateVersionConflict(
            f"Candidate {candidate_id} is {candidate.status} and can no longer be edited."
        )

    reference_data = reference_data or build_candidate_reference_data()
    _payload, issues = parse_and_validate_candidate_payload(effective_payload, reference_data)
    candidate.effective_payload = effective_payload
    candidate.validation_issues = issues
    candidate.status = candidate_status_for_issues(issues)
    candidate.has_manual_edits = True
    candidate.edit_version += 1
    candidate.reviewer_notes = reviewer_notes
    candidate.edited_by_id = edited_by_id
    candidate.edited_at = timezone.now()
    candidate.save()
    return candidate


def parse_and_validate_candidate_payload(
    raw_payload: object,
    reference_data: dict[str, Any],
) -> tuple[EventCandidatePayload | None, list[dict[str, object]]]:
    try:
        payload = EventCandidatePayload.model_validate(raw_payload)
    except PydanticValidationError as exc:
        return None, [
            {
                "code": "STRUCTURAL_PAYLOAD_INVALID",
                "path": ".".join(str(part) for part in error.get("loc", ())),
                "message": error.get("msg", "The candidate payload is structurally invalid."),
                "severity": "ERROR",
                "blocks_canonicalization": True,
            }
            for error in exc.errors(include_url=False)
        ]
    validation = validate_candidate(payload, reference_data)
    return payload, list(validation.issues)


def candidate_status_for_issues(issues: list[dict[str, object]]) -> str:
    if any(issue.get("blocks_canonicalization") for issue in issues):
        return CandidateStatus.BLOCKED
    return CandidateStatus.READY
