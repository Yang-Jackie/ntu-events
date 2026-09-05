from __future__ import annotations

from django.db.models import F, Q
from events.models import (
    EventOccurrence,
    OccurrenceVenue,
    Registration,
    RegistrationStatus,
    RegistrationType,
)

from ingestion.contracts import (
    AttendanceMode,
    CanonicalOccurrenceChange,
    CanonicalOccurrenceValue,
    ObjectOperation,
    OccurrenceField,
    RegistrationField,
    RegistrationScope,
)


def apply_occurrence_changes(
    event, changes: list[CanonicalOccurrenceChange]
) -> dict[str, EventOccurrence]:
    if not changes:
        return {}
    existing = {item.pk: item for item in event.occurrences.all()}
    original_sequences = {item.pk: item.sequence for item in existing.values()}
    EventOccurrence.objects.filter(event=event).update(sequence=F("sequence") + 10000)
    added: dict[str, EventOccurrence] = {}
    for change in changes:
        if change.operation == ObjectOperation.REMOVE:
            existing[change.id].delete()
        elif change.operation == ObjectOperation.ADD:
            occurrence = create_occurrence(event, change.value)
            if change.value.client_ref:
                added[change.value.client_ref] = occurrence
        else:
            occurrence = existing[change.id]
            value = change.value
            for field in change.changed_fields:
                if field == OccurrenceField.VENUE_IDS:
                    continue
                attr = field.value.lower()
                setattr(occurrence, attr, getattr(value, attr))
            if OccurrenceField.SEQUENCE not in change.changed_fields:
                occurrence.sequence = original_sequences[occurrence.pk]
            _normalize_occurrence_blanks(occurrence)
            occurrence.save()
            if OccurrenceField.VENUE_IDS in change.changed_fields:
                _set_occurrence_venues(occurrence, value.venue_ids or [])
    changed_ids = {item.id for item in changes if item.id is not None}
    for pk, occurrence in existing.items():
        if pk not in changed_ids:
            occurrence.sequence = original_sequences[pk]
            occurrence.save(update_fields=("sequence", "updated_at"))
    return added


def apply_registration_changes(event, changes, added_occurrences) -> None:
    existing = {
        item.pk: item
        for item in Registration.objects.filter(Q(event=event) | Q(occurrence__event=event))
    }
    for change in changes:
        if change.operation == ObjectOperation.REMOVE:
            existing[change.id].delete()
        elif change.operation == ObjectOperation.ADD:
            create_registration(event, change.value, added_occurrences)
        else:
            registration = existing[change.id]
            value = change.value
            for field in change.changed_fields:
                if field == RegistrationField.OWNER:
                    _set_registration_owner(registration, event, value, added_occurrences)
                    continue
                attr = field.value.lower()
                setattr(registration, attr, getattr(value, attr) or "")
            registration.save()


def create_occurrence(event, value: CanonicalOccurrenceValue) -> EventOccurrence:
    occurrence = EventOccurrence(
        event=event,
        label=value.label or "",
        sequence=value.sequence,
        start_date=value.start_date,
        start_time=value.start_time,
        end_date=value.end_date,
        end_time=value.end_time,
        time_precision=value.time_precision.value,
        is_all_day=bool(value.is_all_day),
        attendance_mode=(value.attendance_mode or AttendanceMode.UNKNOWN).value,
        raw_location_text=value.raw_location_text or "",
        meeting_url=value.meeting_url or "",
        occurrence_status=value.occurrence_status.value,
    )
    occurrence.save()
    _set_occurrence_venues(occurrence, value.venue_ids or [])
    return occurrence


def _normalize_occurrence_blanks(occurrence) -> None:
    for field in ("label", "raw_location_text", "meeting_url"):
        if getattr(occurrence, field) is None:
            setattr(occurrence, field, "")


def _set_occurrence_venues(occurrence, venue_ids: list[int]) -> None:
    OccurrenceVenue.objects.filter(occurrence=occurrence).delete()
    OccurrenceVenue.objects.bulk_create(
        [
            OccurrenceVenue(
                occurrence=occurrence,
                venue_id=venue_id,
                is_primary=index == 0,
                position=index,
            )
            for index, venue_id in enumerate(dict.fromkeys(venue_ids))
        ]
    )


def create_registration(event, value, added_occurrences) -> Registration:
    registration = Registration(
        name=(value.name or "").strip() or "Registration",
        registration_type=RegistrationType.ATTENDEE,
        url=value.url or "",
        opens_date=value.opens_date,
        opens_time=value.opens_time,
        closes_date=value.closes_date,
        closes_time=value.closes_time,
        instructions=value.instructions or "",
        status=RegistrationStatus.UNKNOWN,
    )
    _set_registration_owner(registration, event, value, added_occurrences)
    registration.save()
    return registration


def _set_registration_owner(registration, event, value, added_occurrences) -> None:
    if value.scope == RegistrationScope.EVENT:
        registration.event = event
        registration.occurrence = None
    else:
        registration.event = None
        registration.occurrence = (
            added_occurrences.get(value.occurrence_client_ref)
            if value.occurrence_client_ref
            else event.occurrences.get(pk=value.occurrence_id)
        )
