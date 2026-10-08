from __future__ import annotations

from typing import Any

from events.models import (
    Event,
    Registration,
)
from pydantic import ValidationError as PydanticValidationError

from ingestion.contracts import (
    CanonicalEventCreate,
    CanonicalizationAction,
    CanonicalizationProposal,
    ClassificationKind,
    ClassificationOperation,
    EventField,
    ObjectOperation,
)
from ingestion.models import (
    CandidateMatch,
    EventCandidate,
)

from . import objects, references
from .issues import hard_issue as _hard_issue
from .resulting_state import (
    merged_occurrence_value,
    merged_registration_value,
    validate_final_occurrence_sequences,
    validate_final_organizers,
)


def validate_proposal(
    candidate: EventCandidate,
    proposal: CanonicalizationProposal | dict[str, Any],
    *,
    matches: list[CandidateMatch] | None = None,
) -> list[dict[str, Any]]:
    try:
        proposal = CanonicalizationProposal.model_validate(proposal)
    except PydanticValidationError as exc:
        return [
            _hard_issue(
                "PROPOSAL_SCHEMA_INVALID",
                ".".join(str(part) for part in error.get("loc", ())),
                error.get("msg", "The proposal is structurally invalid."),
            )
            for error in exc.errors(include_url=False)
        ]

    issues: list[dict[str, Any]] = []
    matched_ids = {
        match.event_id
        for match in (
            matches
            if matches is not None
            else CandidateMatch.objects.filter(event_candidate=candidate)
        )
    }
    target = None
    if proposal.target_event_id is not None:
        target = Event.objects.filter(pk=proposal.target_event_id).first()
        if target is None:
            issues.append(
                _hard_issue(
                    "TARGET_EVENT_NOT_FOUND",
                    "target_event_id",
                    f"Event {proposal.target_event_id} does not exist.",
                )
            )
        elif proposal.target_event_id not in matched_ids:
            issues.append(
                _hard_issue(
                    "TARGET_EVENT_NOT_MATCHED",
                    "target_event_id",
                    "The target Event is not in this candidate's deterministic shortlist.",
                )
            )

    if proposal.action == CanonicalizationAction.ADD and proposal.add_event is not None:
        _validate_add_event(proposal.add_event, issues)
    elif target is not None and proposal.action == CanonicalizationAction.UPDATE:
        _validate_update(target, proposal, issues)
    return issues


def _validate_add_event(value: CanonicalEventCreate, issues: list[dict[str, Any]]) -> None:
    references.validate_catalogs(
        value.formats, value.topics, value.purposes, value.audiences, issues
    )
    references.validate_organizer_ids([item.organizer_id for item in value.organizers], issues)
    references.validate_venue_ids(
        [venue_id for item in value.occurrences for venue_id in (item.venue_ids or [])],
        issues,
    )
    if sum(1 for item in value.organizers if item.is_primary) > 1:
        issues.append(
            _hard_issue(
                "MULTIPLE_PRIMARY_ORGANIZERS",
                "add_event.organizers",
                "Only one organizer may be primary.",
            )
        )
    for index, organizer in enumerate(value.organizers):
        objects.validate_small_integer(
            organizer.position,
            f"add_event.organizers.{index}.position",
            "ORGANIZER_POSITION_INVALID",
            issues,
        )
    client_refs = [item.client_ref for item in value.occurrences]
    if None in client_refs or len(client_refs) != len(set(client_refs)):
        issues.append(
            _hard_issue(
                "OCCURRENCE_CLIENT_REF_INVALID",
                "add_event.occurrences",
                "Added occurrences require unique client references.",
            )
        )
    sequences = [item.sequence for item in value.occurrences]
    if None in sequences or len(sequences) != len(set(sequences)):
        issues.append(
            _hard_issue(
                "OCCURRENCE_SEQUENCE_INVALID",
                "add_event.occurrences",
                "Added occurrences require unique sequences.",
            )
        )
    for index, occurrence in enumerate(value.occurrences):
        objects.validate_occurrence_value(
            occurrence, f"add_event.occurrences.{index}", issues, adding=True
        )
    for index, registration in enumerate(value.registrations):
        objects.validate_registration_value(
            registration,
            f"add_event.registrations.{index}",
            issues,
            event=None,
            added_occurrence_refs=set(client_refs),
        )


def _validate_update(
    event: Event,
    proposal: CanonicalizationProposal,
    issues: list[dict[str, Any]],
) -> None:
    objects.unique_change_fields(proposal.event_changes, "event_changes", issues)
    title_change = next(
        (item for item in proposal.event_changes if item.field == EventField.TITLE), None
    )
    if title_change and (not title_change.value or not title_change.value.strip()):
        issues.append(_hard_issue("TITLE_INVALID", "event_changes", "Event title cannot be empty."))

    classification_keys = {(item.kind, item.operation) for item in proposal.classification_changes}
    if len(classification_keys) != len(proposal.classification_changes):
        issues.append(
            _hard_issue(
                "CLASSIFICATION_CHANGE_DUPLICATE",
                "classification_changes",
                "A classification kind and operation pair appears more than once.",
            )
        )
    classification_values: dict[ClassificationKind, list[str]] = {
        kind: [] for kind in ClassificationKind
    }
    for kind in ClassificationKind:
        changes = [item for item in proposal.classification_changes if item.kind == kind]
        if (
            any(item.operation == ClassificationOperation.REPLACE_CODES for item in changes)
            and len(changes) > 1
        ):
            issues.append(
                _hard_issue(
                    "CLASSIFICATION_CHANGE_CONFLICT",
                    "classification_changes",
                    f"{kind.value} REPLACE_CODES cannot be combined with another operation.",
                )
            )
        codes = [code for item in changes for code in item.codes]
        if len(codes) != len(set(codes)):
            issues.append(
                _hard_issue(
                    "CLASSIFICATION_CHANGE_CONFLICT",
                    "classification_changes",
                    f"A {kind.value} code appears in more than one operation.",
                )
            )
        classification_values[kind] = codes
    references.validate_catalogs(
        classification_values.get(ClassificationKind.FORMAT, []),
        classification_values.get(ClassificationKind.TOPIC, []),
        classification_values.get(ClassificationKind.PURPOSE, []),
        classification_values.get(ClassificationKind.AUDIENCE, []),
        issues,
    )

    shape_issue_count = len(issues)
    objects.validate_object_changes(proposal.organizer_changes, "organizer_changes", issues)
    objects.validate_object_changes(proposal.occurrence_changes, "occurrence_changes", issues)
    objects.validate_object_changes(proposal.registration_changes, "registration_changes", issues)
    if len(issues) != shape_issue_count:
        return

    organizer_ids = [
        item.value.organizer_id
        for item in proposal.organizer_changes
        if item.value is not None and item.operation != ObjectOperation.REMOVE
    ]
    references.validate_organizer_ids(organizer_ids, issues)
    ownership_issue_count = len(issues)
    references.validate_owned_ids(event, proposal, issues)
    if len(issues) != ownership_issue_count:
        return
    references.validate_venue_ids(
        [
            venue_id
            for change in proposal.occurrence_changes
            if change.value is not None and change.value.venue_ids is not None
            for venue_id in change.value.venue_ids
        ],
        issues,
    )
    added_refs = {
        item.value.client_ref
        for item in proposal.occurrence_changes
        if item.operation == ObjectOperation.ADD and item.value is not None
    }
    raw_added_refs = [
        item.value.client_ref
        for item in proposal.occurrence_changes
        if item.operation == ObjectOperation.ADD and item.value is not None
    ]
    if None in raw_added_refs or len(raw_added_refs) != len(set(raw_added_refs)):
        issues.append(
            _hard_issue(
                "OCCURRENCE_CLIENT_REF_INVALID",
                "occurrence_changes",
                "Added occurrences require unique client references.",
            )
        )
    for index, change in enumerate(proposal.occurrence_changes):
        if change.value is not None:
            value = change.value
            if change.operation == ObjectOperation.UPDATE and change.id is not None:
                try:
                    value = merged_occurrence_value(
                        event.occurrences.filter(pk=change.id).first(), change
                    )
                except PydanticValidationError as exc:
                    issues.extend(
                        _resulting_schema_issues(exc, f"occurrence_changes.{index}.value")
                    )
                    continue
            objects.validate_occurrence_value(
                value,
                f"occurrence_changes.{index}.value",
                issues,
                adding=True,
            )
    for index, change in enumerate(proposal.registration_changes):
        if change.value is not None:
            value = change.value
            if change.operation == ObjectOperation.UPDATE and change.id is not None:
                try:
                    value = merged_registration_value(
                        Registration.objects.filter(pk=change.id).first(), change
                    )
                except PydanticValidationError as exc:
                    issues.extend(
                        _resulting_schema_issues(exc, f"registration_changes.{index}.value")
                    )
                    continue
            objects.validate_registration_value(
                value,
                f"registration_changes.{index}.value",
                issues,
                event=event,
                added_occurrence_refs={value for value in added_refs if value},
            )
    validate_final_occurrence_sequences(event, proposal.occurrence_changes, issues)
    validate_final_organizers(event, proposal.organizer_changes, issues)


def _resulting_schema_issues(error: PydanticValidationError, path: str) -> list[dict[str, Any]]:
    return [
        _hard_issue(
            "RESULTING_STATE_SCHEMA_INVALID",
            ".".join((path, *(str(part) for part in item.get("loc", ())))),
            item.get("msg", "The resulting state is structurally invalid."),
        )
        for item in error.errors(include_url=False)
    ]
