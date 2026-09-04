from events.models import EventOccurrence, Registration

from ingestion.contracts import (
    CanonicalOccurrenceChange,
    CanonicalOccurrenceValue,
    CanonicalRegistrationChange,
    CanonicalRegistrationValue,
    ObjectOperation,
    OccurrenceField,
    RegistrationField,
)

from .proposal_issues import hard_issue as _hard_issue


def merged_occurrence_value(
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


def merged_registration_value(
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


def validate_final_occurrence_sequences(event, changes, issues) -> None:
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


def validate_final_organizers(event, changes, issues) -> None:
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
