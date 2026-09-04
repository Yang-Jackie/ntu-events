from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ingestion.contracts import CandidateControlledValues, EventCandidatePayload
from ingestion.models import ValidationStatus

from .occurrence_validation import validate_occurrence
from .registration_validation import validate_registration
from .validation_issues import IssueSeverity, add_issue, validate_optional_url


@dataclass(frozen=True)
class CandidateValidation:
    status: str
    issues: list[dict[str, object]]


def validate_candidate(
    candidate: EventCandidatePayload,
    reference_data: dict[str, Any],
) -> CandidateValidation:
    issues: list[dict[str, object]] = []

    if not candidate.title or not candidate.title.strip():
        add_issue(
            issues,
            code="TITLE_MISSING",
            path="title",
            message="The source does not provide a usable event title.",
            severity=IssueSeverity.ERROR,
            blocks_canonicalization=True,
        )
    elif not _has_information_beyond_title(candidate):
        add_issue(
            issues,
            code="TITLE_ONLY",
            path="title",
            message="The candidate contains a title but no other useful event information.",
            severity=IssueSeverity.ERROR,
            blocks_canonicalization=True,
        )

    if not candidate.occurrences:
        add_issue(
            issues,
            code="OCCURRENCE_MISSING",
            path="occurrences",
            message="The source does not provide an event occurrence.",
            severity=IssueSeverity.WARNING,
            blocks_canonicalization=False,
        )

    occurrence_refs = [occurrence.local_ref for occurrence in candidate.occurrences]
    duplicate_refs = {ref for ref in occurrence_refs if occurrence_refs.count(ref) > 1}
    for duplicate_ref in sorted(duplicate_refs):
        add_issue(
            issues,
            code="OCCURRENCE_REFERENCE_DUPLICATE",
            path="occurrences",
            message=f"Occurrence reference {duplicate_ref!r} is used more than once.",
            severity=IssueSeverity.ERROR,
            blocks_canonicalization=True,
        )

    supported_venue_ids = {
        int(item["id"])
        for item in reference_data.get("venues", [])
        if isinstance(item, dict) and isinstance(item.get("id"), int)
    }
    for index, occurrence in enumerate(candidate.occurrences):
        validate_occurrence(
            occurrence,
            index=index,
            supported_venue_ids=supported_venue_ids,
            issues=issues,
        )

    known_occurrence_refs = set(occurrence_refs)
    for index, registration in enumerate(candidate.registrations):
        validate_registration(
            registration,
            index=index,
            known_occurrence_refs=known_occurrence_refs,
            issues=issues,
        )

    classification_references = reference_data.get("classifications", {})
    for facet_name, selection in (
        ("formats", candidate.formats),
        ("topics", candidate.topics),
        ("purposes", candidate.purposes),
        ("audiences", candidate.audiences),
    ):
        entries = (
            classification_references.get(facet_name, [])
            if isinstance(classification_references, dict)
            else []
        )
        supported_codes = {
            str(item["code"])
            for item in entries
            if isinstance(item, dict) and isinstance(item.get("code"), str)
        }
        _validate_controlled_values(
            facet_name,
            selection,
            supported_codes=supported_codes,
            issues=issues,
        )

    for index, organizer in enumerate(candidate.organizers):
        if not organizer.name or not organizer.name.strip():
            add_issue(
                issues,
                code="ORGANIZER_NAME_MISSING",
                path=f"organizers.{index}.name",
                message="An organizer entry has no usable name.",
                severity=IssueSeverity.ERROR,
                blocks_canonicalization=False,
            )

    validate_optional_url(
        candidate.image_url,
        path="image_url",
        code="IMAGE_URL_INVALID",
        issues=issues,
        blocks_canonicalization=False,
    )
    validate_optional_url(
        candidate.source_url,
        path="source_url",
        code="SOURCE_URL_INVALID",
        issues=issues,
        blocks_canonicalization=False,
    )

    if candidate.ambiguities:
        add_issue(
            issues,
            code="SOURCE_AMBIGUITY",
            path="ambiguities",
            message="The extracted source facts contain an explicit ambiguity.",
            severity=IssueSeverity.WARNING,
            blocks_canonicalization=False,
        )

    status = ValidationStatus.REVIEW_REQUIRED if issues else ValidationStatus.READY
    return CandidateValidation(status=status, issues=issues)


def _has_information_beyond_title(candidate: EventCandidatePayload) -> bool:
    controlled_values = (
        candidate.formats,
        candidate.topics,
        candidate.purposes,
        candidate.audiences,
    )
    return any(
        (
            bool(candidate.description and candidate.description.strip()),
            bool(candidate.occurrences),
            bool(candidate.organizers),
            bool(candidate.registrations),
            any(item.supported_codes or item.other_values for item in controlled_values),
            bool(candidate.image_url),
        )
    )


def _validate_controlled_values(
    facet_name: str,
    selection: CandidateControlledValues,
    *,
    supported_codes: set[str],
    issues: list[dict[str, object]],
) -> None:
    unknown_codes = sorted(set(selection.supported_codes) - supported_codes)
    if unknown_codes:
        add_issue(
            issues,
            code="UNSUPPORTED_CLASSIFICATION_CODE",
            path=f"{facet_name}.supported_codes",
            message=f"Unsupported {facet_name} codes: {unknown_codes}.",
            severity=IssueSeverity.WARNING,
            blocks_canonicalization=False,
        )
    outside_values = sorted({value.strip() for value in selection.other_values if value.strip()})
    if outside_values:
        add_issue(
            issues,
            code="UNMAPPED_CLASSIFICATION",
            path=f"{facet_name}.other_values",
            message=f"Unmapped {facet_name} values require review: {outside_values}.",
            severity=IssueSeverity.WARNING,
            blocks_canonicalization=False,
        )
