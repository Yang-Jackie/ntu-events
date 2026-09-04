from __future__ import annotations

from typing import Any

from django.db.models import Q
from events.models import (
    Event,
    EventAudience,
    EventFormat,
    EventOccurrence,
    EventOrganizer,
    EventPurpose,
    EventTopic,
    Registration,
)
from organizers.models import Organizer
from pydantic import ValidationError as PydanticValidationError
from venues.models import Venue

from ingestion.contracts import (
    CanonicalEventCreate,
    CanonicalizationAction,
    CanonicalizationProposal,
    ClassificationKind,
    ClassificationOperation,
    EventField,
    ObjectOperation,
    RegistrationScope,
)
from ingestion.http_urls import is_valid_http_url
from ingestion.models import (
    CandidateMatch,
    EventCandidate,
)

from .proposal_issues import hard_issue as _hard_issue
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
    _validate_catalogs(value.formats, value.topics, value.purposes, value.audiences, issues)
    _validate_organizer_ids([item.organizer_id for item in value.organizers], issues)
    _validate_venue_ids(
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
        _validate_occurrence_value(
            occurrence, f"add_event.occurrences.{index}", issues, adding=True
        )
    for index, registration in enumerate(value.registrations):
        _validate_registration_value(
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
    _unique_change_fields(proposal.event_changes, "event_changes", issues)
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
    _validate_catalogs(
        classification_values.get(ClassificationKind.FORMAT, []),
        classification_values.get(ClassificationKind.TOPIC, []),
        classification_values.get(ClassificationKind.PURPOSE, []),
        classification_values.get(ClassificationKind.AUDIENCE, []),
        issues,
    )

    _validate_object_changes(proposal.organizer_changes, "organizer_changes", issues)
    _validate_object_changes(proposal.occurrence_changes, "occurrence_changes", issues)
    _validate_object_changes(proposal.registration_changes, "registration_changes", issues)

    organizer_ids = [
        item.value.organizer_id
        for item in proposal.organizer_changes
        if item.value is not None and item.operation != ObjectOperation.REMOVE
    ]
    _validate_organizer_ids(organizer_ids, issues)
    _validate_owned_ids(event, proposal, issues)
    _validate_venue_ids(
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
                value = merged_occurrence_value(
                    event.occurrences.filter(pk=change.id).first(),
                    change,
                )
            _validate_occurrence_value(
                value,
                f"occurrence_changes.{index}.value",
                issues,
                adding=True,
            )
    for index, change in enumerate(proposal.registration_changes):
        if change.value is not None:
            value = change.value
            if change.operation == ObjectOperation.UPDATE and change.id is not None:
                value = merged_registration_value(
                    Registration.objects.filter(pk=change.id).first(),
                    change,
                )
            _validate_registration_value(
                value,
                f"registration_changes.{index}.value",
                issues,
                event=event,
                added_occurrence_refs={value for value in added_refs if value},
            )
    validate_final_occurrence_sequences(event, proposal.occurrence_changes, issues)
    validate_final_organizers(event, proposal.organizer_changes, issues)


def _validate_catalogs(formats, topics, purposes, audiences, issues) -> None:
    for path, model, values in (
        ("formats", EventFormat, formats),
        ("topics", EventTopic, topics),
        ("purposes", EventPurpose, purposes),
        ("audiences", EventAudience, audiences),
    ):
        supplied = set(values)
        supported = set(
            model.objects.filter(is_active=True, code__in=supplied).values_list("code", flat=True)
        )
        unknown = sorted(supplied - supported)
        if unknown:
            issues.append(
                _hard_issue(
                    "UNSUPPORTED_CLASSIFICATION_CODE", path, f"Unsupported codes: {unknown}."
                )
            )


def _validate_organizer_ids(ids: list[int], issues: list[dict[str, Any]]) -> None:
    supplied = set(ids)
    existing = set(Organizer.objects.filter(pk__in=supplied).values_list("pk", flat=True))
    if supplied - existing:
        issues.append(
            _hard_issue(
                "ORGANIZER_NOT_FOUND",
                "organizers",
                f"Organizer IDs do not exist: {sorted(supplied - existing)}.",
            )
        )


def _validate_venue_ids(ids: list[int], issues: list[dict[str, Any]]) -> None:
    supplied = set(ids)
    existing = set(Venue.objects.filter(pk__in=supplied).values_list("pk", flat=True))
    if supplied - existing:
        issues.append(
            _hard_issue(
                "VENUE_NOT_FOUND",
                "occurrences.venue_ids",
                f"Venue IDs do not exist: {sorted(supplied - existing)}.",
            )
        )


def _validate_owned_ids(event: Event, proposal: CanonicalizationProposal, issues) -> None:
    for path, model, changes, owner_filter in (
        ("organizer_changes", EventOrganizer, proposal.organizer_changes, {"event": event}),
        ("occurrence_changes", EventOccurrence, proposal.occurrence_changes, {"event": event}),
        (
            "registration_changes",
            Registration,
            proposal.registration_changes,
            {},
        ),
    ):
        ids = {item.id for item in changes if item.operation != ObjectOperation.ADD and item.id}
        queryset = model.objects.filter(pk__in=ids, **owner_filter)
        if model is Registration:
            queryset = queryset.filter(Q(event=event) | Q(occurrence__event=event))
        existing = set(queryset.values_list("pk", flat=True))
        if ids - existing:
            issues.append(
                _hard_issue(
                    "CHILD_NOT_FOUND_OR_WRONG_OWNER",
                    path,
                    f"Child IDs are missing or belong to another Event: {sorted(ids - existing)}.",
                )
            )


def _validate_object_changes(changes, path: str, issues) -> None:
    seen: set[int] = set()
    for index, change in enumerate(changes):
        if change.operation == ObjectOperation.ADD:
            if change.id is not None or change.value is None:
                issues.append(
                    _hard_issue(
                        "ADD_OBJECT_INVALID", f"{path}.{index}", "ADD requires id null and a value."
                    )
                )
        elif change.operation == ObjectOperation.UPDATE:
            if change.id is None or change.value is None or not change.changed_fields:
                issues.append(
                    _hard_issue(
                        "UPDATE_OBJECT_INVALID",
                        f"{path}.{index}",
                        "UPDATE requires an ID, value, and changed fields.",
                    )
                )
        elif change.id is None or change.value is not None or change.changed_fields:
            issues.append(
                _hard_issue(
                    "REMOVE_OBJECT_INVALID",
                    f"{path}.{index}",
                    "REMOVE requires an ID and no value or changed fields.",
                )
            )
        if change.id is not None:
            if change.id in seen:
                issues.append(
                    _hard_issue(
                        "OBJECT_CHANGE_DUPLICATE",
                        f"{path}.{index}.id",
                        "An object is changed more than once.",
                    )
                )
            seen.add(change.id)
        if len(change.changed_fields) != len(set(change.changed_fields)):
            issues.append(
                _hard_issue(
                    "FIELD_CHANGE_DUPLICATE",
                    f"{path}.{index}.changed_fields",
                    "A field is changed more than once.",
                )
            )


def _validate_occurrence_value(value, path, issues, *, adding: bool) -> None:
    if adding and (
        value.start_date is None
        or value.sequence is None
        or value.time_precision is None
        or value.attendance_mode is None
        or value.is_all_day is None
        or value.occurrence_status is None
    ):
        issues.append(
            _hard_issue(
                "OCCURRENCE_REQUIRED_FIELD_MISSING",
                path,
                "An occurrence is missing a field required by canonical storage.",
            )
        )
        return
    if value.start_date and value.end_date and value.end_date < value.start_date:
        issues.append(
            _hard_issue("OCCURRENCE_TIME_INVALID", path, "Occurrence end precedes start.")
        )
    if value.end_time is not None and (value.end_date is None or value.start_time is None):
        issues.append(
            _hard_issue(
                "OCCURRENCE_TIME_INVALID",
                path,
                "An end time requires both end date and start time.",
            )
        )
    if (
        value.start_date
        and value.end_date == value.start_date
        and value.start_time
        and value.end_time
        and value.end_time < value.start_time
    ):
        issues.append(
            _hard_issue("OCCURRENCE_TIME_INVALID", path, "Occurrence end precedes start.")
        )
    if value.is_all_day and (value.start_time is not None or value.end_time is not None):
        issues.append(
            _hard_issue(
                "OCCURRENCE_TIME_INVALID",
                path,
                "An all-day occurrence cannot contain times.",
            )
        )
    if value.time_precision and value.time_precision.value == "EXACT" and not value.start_time:
        issues.append(
            _hard_issue(
                "OCCURRENCE_TIME_INVALID",
                path,
                "An exact occurrence requires a start time.",
            )
        )
    if (
        value.time_precision
        and value.time_precision.value == "DATE_ONLY"
        and (value.start_time is not None or value.end_time is not None)
    ):
        issues.append(
            _hard_issue(
                "OCCURRENCE_TIME_INVALID",
                path,
                "A date-only occurrence cannot contain times.",
            )
        )
    if value.meeting_url and not is_valid_http_url(value.meeting_url):
        issues.append(
            _hard_issue("MEETING_URL_INVALID", f"{path}.meeting_url", "Meeting URL is invalid.")
        )


def _validate_registration_value(value, path, issues, *, event, added_occurrence_refs) -> None:
    if value.scope is None:
        issues.append(
            _hard_issue(
                "REGISTRATION_OWNER_INVALID",
                path,
                "Registration scope is required.",
            )
        )
        return
    if value.url and not is_valid_http_url(value.url):
        issues.append(
            _hard_issue("REGISTRATION_URL_INVALID", f"{path}.url", "Registration URL is invalid.")
        )
    if value.scope == RegistrationScope.OCCURRENCE:
        valid_id = bool(
            event
            and value.occurrence_id
            and event.occurrences.filter(pk=value.occurrence_id).exists()
        )
        valid_ref = bool(value.occurrence_client_ref in added_occurrence_refs)
        if not (valid_id or valid_ref):
            issues.append(
                _hard_issue(
                    "REGISTRATION_OWNER_INVALID",
                    path,
                    "Occurrence registration has no valid occurrence owner.",
                )
            )
    elif value.scope == RegistrationScope.EVENT:
        if value.occurrence_id is not None or value.occurrence_client_ref is not None:
            issues.append(
                _hard_issue(
                    "REGISTRATION_OWNER_INVALID",
                    path,
                    "Event registration cannot reference an occurrence.",
                )
            )
    if value.opens_time is not None and value.opens_date is None:
        issues.append(
            _hard_issue("REGISTRATION_TIME_INVALID", path, "Opening time requires a date.")
        )
    if value.closes_time is not None and value.closes_date is None:
        issues.append(
            _hard_issue("REGISTRATION_TIME_INVALID", path, "Closing time requires a date.")
        )
    if value.opens_date and value.closes_date and value.closes_date < value.opens_date:
        issues.append(
            _hard_issue("REGISTRATION_TIME_INVALID", path, "Registration closes before it opens.")
        )
    if (
        value.opens_date
        and value.closes_date == value.opens_date
        and value.opens_time
        and value.closes_time
        and value.closes_time < value.opens_time
    ):
        issues.append(
            _hard_issue("REGISTRATION_TIME_INVALID", path, "Registration closes before it opens.")
        )


def _unique_change_fields(changes, path, issues) -> None:
    fields = [item.field for item in changes]
    if len(fields) != len(set(fields)):
        issues.append(
            _hard_issue("FIELD_CHANGE_DUPLICATE", path, "A field is changed more than once.")
        )
