from __future__ import annotations

from typing import Any

from organizers.models import Organizer

from ingestion.canonicalization.snapshots import event_snapshot
from ingestion.contracts import (
    EventCandidatePayload,
)
from ingestion.models import (
    CandidateMatch,
    EventCandidate,
)
from ingestion.reference_data import build_candidate_reference_data


def build_canonicalization_context(
    candidate: EventCandidate,
    payload: EventCandidatePayload,
    *,
    raw_document: dict[str, Any],
    match_snapshot: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "event_candidate": {
            "id": candidate.pk,
            "version": candidate.edit_version,
            "effective_payload": payload.model_dump(mode="json"),
        },
        "raw_document": raw_document,
        "possible_matches": match_snapshot,
        "catalog": {
            "organizers": list(
                Organizer.objects.order_by("pk").values("id", "name", "organization_type")
            ),
            **build_candidate_reference_data(),
        },
    }


def match_record(match: CandidateMatch) -> dict[str, Any]:
    return {
        "event_id": match.event_id,
        "rank": match.rank,
        "match_percentage": round(float(match.score) * 100, 2),
        "signals": match.signals,
        "event": event_snapshot(match.event),
    }
