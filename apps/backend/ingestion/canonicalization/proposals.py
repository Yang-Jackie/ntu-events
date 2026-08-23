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

from ingestion.candidate_validation import is_valid_http_url
from ingestion.canonicalization.matching import normalize_match_text
from ingestion.contracts import (
    CanonicalEventCreate,
    CanonicalizationAction,
    CanonicalizationProposal,
    CanonicalOccurrenceChange,
    CanonicalOccurrenceValue,
    CanonicalOrganizerValue,
    CanonicalRegistrationChange,
    CanonicalRegistrationValue,
    ClassificationKind,
    ClassificationOperation,
    EventCandidatePayload,
    EventField,
    FieldOperation,
    ObjectOperation,
    OccurrenceField,
    RegistrationField,
    RegistrationScope,
    TimePrecision,
)
from ingestion.models import (
    CandidateMatch,
    EventCandidate,
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


def automatic_add_proposal(payload: EventCandidatePayload) -> CanonicalizationProposal:
    organizers: list[CanonicalOrganizerValue] = []
    seen_organizers: set[int] = set()
    for position, source in enumerate(payload.organizers):
        if not source.name:
            continue
        matches = list(
            Organizer.objects.filter(normalized_name=normalize_match_text(source.name))[:2]
        )
        if len(matches) != 1 or matches[0].pk in seen_organizers:
            continue
        seen_organizers.add(matches[0].pk)
        organizers.append(
            CanonicalOrganizerValue(
                organizer_id=matches[0].pk,
                role=source.role,
                is_primary=source.is_primary,
                position=position,
            )
        )
    occurrences = []
    projected_occurrence_refs: set[str] = set()
    for item in payload.occurrences:
        if item.start_date is None:
            continue
        start_time = item.start_time
        end_time = item.end_time
        time_precision = item.time_precision
        if item.is_all_day or time_precision == TimePrecision.DATE_ONLY:
            start_time = None
            end_time = None
        if time_precision == TimePrecision.EXACT and start_time is None:
            time_precision = TimePrecision.UNKNOWN
        if start_time is None or item.end_date is None:
            end_time = None
        occurrences.append(
            CanonicalOccurrenceValue(
                client_ref=item.local_ref,
                label=item.label,
                sequence=len(occurrences) + 1,
                start_date=item.start_date,
                start_time=start_time,
                end_date=item.end_date,
                end_time=end_time,
                time_precision=time_precision,
                is_all_day=item.is_all_day,
                attendance_mode=item.attendance_mode,
                raw_location_text=item.raw_location,
                meeting_url=(item.meeting_url if is_valid_http_url(item.meeting_url) else None),
                occurrence_status=item.status,
                venue_ids=item.suggested_venue_ids,
            )
        )
        projected_occurrence_refs.add(item.local_ref)

    registrations = []
    for item in payload.registrations:
        if (
            item.scope == RegistrationScope.OCCURRENCE
            and item.occurrence_ref not in projected_occurrence_refs
        ):
            continue
        url = item.url if is_valid_http_url(item.url) else None
        opens_time = item.opens_time if item.opens_date is not None else None
        closes_time = item.closes_time if item.closes_date is not None else None
        if not any(
            (
                bool(item.name and item.name.strip()),
                bool(url),
                bool(item.instructions and item.instructions.strip()),
                item.opens_date is not None,
                item.closes_date is not None,
            )
        ):
            continue
        registrations.append(
            CanonicalRegistrationValue(
                name=item.name,
                scope=item.scope,
                occurrence_id=None,
                occurrence_client_ref=(
                    item.occurrence_ref if item.scope == RegistrationScope.OCCURRENCE else None
                ),
                url=url,
                opens_date=item.opens_date,
                opens_time=opens_time,
                closes_date=item.closes_date,
                closes_time=closes_time,
                instructions=item.instructions,
            )
        )
    return CanonicalizationProposal(
        action=CanonicalizationAction.ADD,
        target_event_id=None,
        reasoning="No deterministic canonical Event match was found.",
        add_event=CanonicalEventCreate(
            title=(payload.title or "").strip(),
            description=payload.description,
            image_reference=(payload.image_url if is_valid_http_url(payload.image_url) else None),
            audience_notes=None,
            formats=payload.formats.supported_codes,
            topics=payload.topics.supported_codes,
            purposes=payload.purposes.supported_codes,
            audiences=payload.audiences.supported_codes,
            organizers=organizers,
            occurrences=occurrences,
            registrations=registrations,
        ),
        event_changes=[],
        classification_changes=[],
        organizer_changes=[],
        occurrence_changes=[],
        registration_changes=[],
    )


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
                value = _merged_occurrence_value(
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
                value = _merged_registration_value(
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
    _validate_final_occurrence_sequences(event, proposal.occurrence_changes, issues)
    _validate_final_organizers(event, proposal.organizer_changes, issues)


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


def _merged_occurrence_value(
    occurrence: EventOccurrence | None,
    change: CanonicalOccurrenceChange,
) -> CanonicalOccurrenceValue:
    if occurrence is None or change.value is None:
        return change.value
    values = {
        "client_ref": None,
        "label": occurrence.label,
        "sequence": occurrence.sequence,
        "start_date": occurrence.start_date,
        "start_time": occurrence.start_time,
        "end_date": occurrence.end_date,
        "end_time": occurrence.end_time,
        "time_precision": occurrence.time_precision,
        "is_all_day": occurrence.is_all_day,
        "attendance_mode": occurrence.attendance_mode,
        "raw_location_text": occurrence.raw_location_text,
        "meeting_url": occurrence.meeting_url,
        "occurrence_status": occurrence.occurrence_status,
        "venue_ids": list(occurrence.venues.values_list("pk", flat=True)),
    }
    for field in change.changed_fields:
        values[field.value.lower()] = getattr(change.value, field.value.lower())
    return CanonicalOccurrenceValue.model_validate(values)


def _merged_registration_value(
    registration: Registration | None,
    change: CanonicalRegistrationChange,
) -> CanonicalRegistrationValue:
    if registration is None or change.value is None:
        return change.value
    values = {
        "name": registration.name,
        "scope": "EVENT" if registration.event_id else "OCCURRENCE",
        "occurrence_id": registration.occurrence_id,
        "occurrence_client_ref": None,
        "url": registration.url,
        "opens_date": registration.opens_date,
        "opens_time": registration.opens_time,
        "closes_date": registration.closes_date,
        "closes_time": registration.closes_time,
        "instructions": registration.instructions,
    }
    for field in change.changed_fields:
        if field == RegistrationField.OWNER:
            for name in ("scope", "occurrence_id", "occurrence_client_ref"):
                values[name] = getattr(change.value, name)
        else:
            values[field.value.lower()] = getattr(change.value, field.value.lower())
    return CanonicalRegistrationValue.model_validate(values)


def _validate_final_occurrence_sequences(event, changes, issues) -> None:
    sequences = {item.pk: item.sequence for item in event.occurrences.all()}
    next_temporary_id = -1
    for change in changes:
        if change.operation == ObjectOperation.REMOVE:
            sequences.pop(change.id, None)
        elif change.operation == ObjectOperation.ADD:
            sequences[next_temporary_id] = change.value.sequence
            next_temporary_id -= 1
        elif OccurrenceField.SEQUENCE in change.changed_fields:
            sequences[change.id] = change.value.sequence
    values = list(sequences.values())
    if None in values or len(values) != len(set(values)):
        issues.append(
            _hard_issue(
                "OCCURRENCE_SEQUENCE_INVALID",
                "occurrence_changes",
                "The resulting occurrence sequences must be present and unique.",
            )
        )


def _validate_final_organizers(event, changes, issues) -> None:
    values = {
        item.pk: {
            "organizer_id": item.organizer_id,
            "role": item.role,
            "is_primary": item.is_primary,
            "position": item.position,
        }
        for item in event.eventorganizer_set.all()
    }
    next_temporary_id = -1
    for change in changes:
        if change.operation == ObjectOperation.REMOVE:
            values.pop(change.id, None)
        elif change.operation == ObjectOperation.ADD:
            values[next_temporary_id] = change.value.model_dump()
            next_temporary_id -= 1
        else:
            current = values.get(change.id)
            if current is None:
                continue
            for field in change.changed_fields:
                current[field.value.lower()] = getattr(change.value, field.value.lower())
    organizer_ids = [item["organizer_id"] for item in values.values()]
    if len(organizer_ids) != len(set(organizer_ids)):
        issues.append(
            _hard_issue(
                "ORGANIZER_DUPLICATE",
                "organizer_changes",
                "The resulting Event cannot reference one Organizer more than once.",
            )
        )
    if sum(1 for item in values.values() if item["is_primary"]) > 1:
        issues.append(
            _hard_issue(
                "MULTIPLE_PRIMARY_ORGANIZERS",
                "organizer_changes",
                "The resulting Event can have at most one primary Organizer.",
            )
        )


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


def _hard_issue(code: str, path: str, message: str) -> dict[str, Any]:
    return {
        "code": code,
        "path": path,
        "message": message,
        "severity": "ERROR",
        "blocks_application": True,
    }
