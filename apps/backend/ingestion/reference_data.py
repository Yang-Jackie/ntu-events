from __future__ import annotations

import hashlib
import json
from typing import Any

from django.db.models import Prefetch, Q
from events.models import EventAudience, EventFormat, EventPurpose, EventTopic
from venues.models import Venue, VenueAlias


def build_candidate_reference_data() -> dict[str, Any]:
    return {
        "classifications": {
            "formats": _classification_values(EventFormat),
            "topics": _classification_values(EventTopic),
            "purposes": _classification_values(EventPurpose),
            "audiences": _classification_values(EventAudience),
        },
        "venues": _venue_values(),
    }


def candidate_reference_data_hash(reference_data: dict[str, Any]) -> str:
    serialized = json.dumps(
        reference_data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _classification_values(model) -> list[dict[str, Any]]:
    return list(
        model.objects.filter(is_active=True)
        .order_by("sort_order", "code")
        .values("code", "label", "description")
    )


def _venue_values() -> list[dict[str, Any]]:
    verified_aliases = VenueAlias.objects.filter(is_verified=True).order_by("normalized_alias")
    venues = (
        Venue.objects.filter(is_verified=True)
        .filter(Q(building__isnull=True) | Q(building__is_active=True))
        .select_related("building")
        .prefetch_related(Prefetch("aliases", queryset=verified_aliases))
        .order_by("pk")
    )
    return [
        {
            "id": venue.pk,
            "name": venue.name,
            "building_code": venue.building.code if venue.building else None,
            "building_name": venue.building.name if venue.building else None,
            "room_code": venue.room_code or None,
            "aliases": [alias.alias for alias in venue.aliases.all()],
        }
        for venue in venues
    ]
