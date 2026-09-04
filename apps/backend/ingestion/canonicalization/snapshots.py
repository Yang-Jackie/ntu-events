import hashlib
import json
from typing import Any

from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q
from events.models import Event, Registration


def event_snapshot(event: Event) -> dict[str, Any]:
    event = Event.objects.prefetch_related(
        "formats",
        "topics",
        "purposes",
        "audiences",
        "eventorganizer_set",
        "occurrences__occurrencevenue_set",
        "registrations",
        "occurrences__registrations",
    ).get(pk=event.pk)
    occurrences = []
    for occurrence in event.occurrences.order_by("sequence", "pk"):
        occurrences.append(
            {
                "id": occurrence.pk,
                "label": occurrence.label,
                "sequence": occurrence.sequence,
                "start_date": occurrence.start_date.isoformat(),
                "start_time": _iso(occurrence.start_time),
                "end_date": _iso(occurrence.end_date),
                "end_time": _iso(occurrence.end_time),
                "time_precision": occurrence.time_precision,
                "is_all_day": occurrence.is_all_day,
                "attendance_mode": occurrence.attendance_mode,
                "raw_location_text": occurrence.raw_location_text,
                "meeting_url": occurrence.meeting_url,
                "occurrence_status": occurrence.occurrence_status,
                "capacity_status": occurrence.capacity_status,
                "venue_ids": list(
                    occurrence.occurrencevenue_set.order_by("position", "pk").values_list(
                        "venue_id", flat=True
                    )
                ),
            }
        )
    registrations = Registration.objects.filter(
        Q(event=event) | Q(occurrence__event=event)
    ).order_by("pk")
    return {
        "id": event.pk,
        "slug": event.slug,
        "title": event.title,
        "description": event.description,
        "image_reference": event.image_reference,
        "audience_notes": event.audience_notes,
        "publication_status": event.publication_status,
        "verification_status": event.verification_status,
        "last_verified_at": _iso(event.last_verified_at),
        "archived_at": _iso(event.archived_at),
        "formats": list(event.formats.order_by("code").values_list("code", flat=True)),
        "topics": list(event.topics.order_by("code").values_list("code", flat=True)),
        "purposes": list(event.purposes.order_by("code").values_list("code", flat=True)),
        "audiences": list(event.audiences.order_by("code").values_list("code", flat=True)),
        "organizers": list(
            event.eventorganizer_set.order_by("position", "pk").values(
                "id", "organizer_id", "role", "is_primary", "position"
            )
        ),
        "occurrences": occurrences,
        "registrations": [
            {
                "id": item.pk,
                "scope": "EVENT" if item.event_id else "OCCURRENCE",
                "occurrence_id": item.occurrence_id,
                "name": item.name,
                "registration_type": item.registration_type,
                "url": item.url,
                "opens_date": _iso(item.opens_date),
                "opens_time": _iso(item.opens_time),
                "closes_date": _iso(item.closes_date),
                "closes_time": _iso(item.closes_time),
                "instructions": item.instructions,
                "time_precision": item.time_precision,
                "status": item.status,
            }
            for item in registrations
        ],
    }


def event_snapshot_hash(event: Event) -> str:
    return event_snapshot_payload_hash(event_snapshot(event))


def event_snapshot_payload_hash(snapshot: dict[str, Any]) -> str:
    serialized = json.dumps(
        snapshot,
        cls=DjangoJSONEncoder,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _iso(value):
    return value.isoformat() if value is not None else None
