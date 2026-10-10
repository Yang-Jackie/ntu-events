"""Apply reviewed location matches to automatic proposals; retain generated evidence."""

from events.models import EventOccurrence
from venues.resolution import VenueResolver

from ingestion.contracts import AttendanceMode, ObjectOperation, OccurrenceField


def resolve_proposal_locations(proposal):
    effective = proposal.model_copy(deep=True)
    resolver = VenueResolver()
    flags = []

    def resolve(value, *, path, raw_location, attendance_mode):
        result = resolver.resolve(raw_location)
        ids = [] if attendance_mode == AttendanceMode.ONLINE else list(result.venue_ids)
        previous = value.venue_ids or []
        value.venue_ids = ids
        if ids != previous:
            flags.append(
                {
                    "code": "VENUE_RESOLUTION_CHANGED",
                    "path": path,
                    "message": "Venue suggestions were checked against reviewed wording.",
                    "raw_location_text": raw_location,
                    "suggested_venue_ids": previous,
                    "resolved_venue_ids": ids,
                    "resolution_method": result.method,
                }
            )

    if effective.add_event:
        for index, value in enumerate(effective.add_event.occurrences):
            resolve(
                value,
                path=f"add_event.occurrences.{index}.venue_ids",
                raw_location=value.raw_location_text,
                attendance_mode=value.attendance_mode,
            )
    location_fields = {
        OccurrenceField.RAW_LOCATION_TEXT,
        OccurrenceField.VENUE_IDS,
        OccurrenceField.ATTENDANCE_MODE,
    }
    for index, change in enumerate(effective.occurrence_changes):
        if change.value is None or change.operation == ObjectOperation.REMOVE:
            continue
        value = change.value
        if change.operation == ObjectOperation.ADD:
            raw, mode = value.raw_location_text, value.attendance_mode
        elif location_fields.intersection(change.changed_fields):
            current = EventOccurrence.objects.filter(
                pk=change.id, event_id=effective.target_event_id
            ).first()
            if current is None:
                continue  # Ordinary ownership validation rejects this change.
            raw = (
                value.raw_location_text
                if OccurrenceField.RAW_LOCATION_TEXT in change.changed_fields
                else current.raw_location_text
            )
            mode = (
                value.attendance_mode
                if OccurrenceField.ATTENDANCE_MODE in change.changed_fields
                else current.attendance_mode
            )
            if OccurrenceField.VENUE_IDS not in change.changed_fields:
                change.changed_fields.append(OccurrenceField.VENUE_IDS)
        else:
            continue  # A description/time update does not overwrite the owner's location.
        resolve(
            value,
            path=f"occurrence_changes.{index}.value.venue_ids",
            raw_location=raw,
            attendance_mode=mode,
        )
    return effective, flags
