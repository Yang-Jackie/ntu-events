from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from django.contrib.postgres.search import TrigramDistance, TrigramSimilarity
from django.db.models import Q
from events.models import (
    Event,
    EventSourceLink,
)

from ingestion.candidate_validation import is_valid_http_url
from ingestion.contracts import (
    EventCandidatePayload,
)
from ingestion.models import (
    CandidateMatch,
    EventCandidate,
)

MATCH_THRESHOLD = 0.30
TITLE_RETRIEVAL_LIMIT = 10
STRUCTURED_RETRIEVAL_LIMIT = 50
MAX_MATCHES = 5
MATCH_WEIGHTS = {
    "TITLE": 0.65,
    "REGISTRATION_URL": 0.15,
    "OCCURRENCE_DATE": 0.10,
    "ORGANIZER": 0.04,
    "VENUE": 0.04,
    "SOURCE": 0.02,
}


def find_candidate_matches(
    candidate: EventCandidate,
    payload: EventCandidatePayload,
) -> list[CandidateMatch]:
    CandidateMatch.objects.filter(event_candidate=candidate).delete()
    candidate_dates = {item.start_date for item in payload.occurrences if item.start_date}
    candidate_raw_urls = {
        item.url for item in payload.registrations if item.url and is_valid_http_url(item.url)
    }
    candidate_urls = {normalize_match_url(item) for item in candidate_raw_urls}
    candidate_venues = {
        venue_id for item in payload.occurrences for venue_id in item.suggested_venue_ids
    }
    candidate_organizers = {
        normalize_match_text(item.name)
        for item in payload.organizers
        if item.name and item.name.strip()
    }
    normalized_title = normalize_match_text(payload.title or "")
    source_representation_id = candidate.source_representation_id
    source_id = candidate.source_representation.source_id
    retrieval_reasons = _retrieve_candidate_event_ids(
        normalized_title=normalized_title,
        source_representation_id=source_representation_id,
        candidate_urls=candidate_raw_urls,
        candidate_dates=candidate_dates,
        candidate_organizers=candidate_organizers,
        candidate_venues=candidate_venues,
    )
    if not retrieval_reasons:
        return []

    scored: list[tuple[float, int, list[dict[str, Any]]]] = []
    events = (
        Event.objects.filter(pk__in=retrieval_reasons)
        .annotate(title_similarity=TrigramSimilarity("normalized_title", normalized_title))
        .prefetch_related(
            "occurrences__venues",
            "occurrences__registrations",
            "registrations",
            "organizers",
            "source_links__source_representation",
        )
    )
    for event in events:
        source_representation_ids = {
            link.source_representation_id for link in event.source_links.all()
        }
        event_source_ids = {
            link.source_representation.source_id for link in event.source_links.all()
        }
        event_dates = {item.start_date for item in event.occurrences.all()}
        event_urls = {
            normalize_match_url(item.url)
            for item in event.registrations.all()
            if item.url and is_valid_http_url(item.url)
        }
        event_urls.update(
            normalize_match_url(item.url)
            for occurrence in event.occurrences.all()
            for item in occurrence.registrations.all()
            if item.url and is_valid_http_url(item.url)
        )
        event_organizers = {normalize_match_text(item.name) for item in event.organizers.all()}
        event_venues = {
            venue.pk for occurrence in event.occurrences.all() for venue in occurrence.venues.all()
        }
        title_similarity = float(event.title_similarity or 0)
        exact_registration_url = bool(candidate_urls & event_urls)
        same_source_representation = source_representation_id in source_representation_ids
        evidence_signals = []
        if same_source_representation:
            evidence_signals.append("SAME_SOURCE_REPRESENTATION")
        if exact_registration_url:
            evidence_signals.append("REGISTRATION_URL_NORMALIZED_EXACT")
        if title_similarity > 0:
            evidence_signals.append("TITLE_SIMILARITY")

        field_signals = [
            _field_match_signal(
                kind="REGISTRATION_URL",
                weight=MATCH_WEIGHTS["REGISTRATION_URL"],
                candidate_available=bool(candidate_urls),
                event_available=bool(event_urls),
                similarity=1.0 if exact_registration_url else 0.0,
            ),
            _field_match_signal(
                kind="TITLE",
                weight=MATCH_WEIGHTS["TITLE"],
                candidate_available=bool(normalized_title),
                event_available=bool(event.normalized_title),
                similarity=title_similarity,
            ),
            _field_match_signal(
                kind="OCCURRENCE_DATE",
                weight=MATCH_WEIGHTS["OCCURRENCE_DATE"],
                candidate_available=bool(candidate_dates),
                event_available=bool(event_dates),
                similarity=_date_similarity(candidate_dates, event_dates),
            ),
            _field_match_signal(
                kind="ORGANIZER",
                weight=MATCH_WEIGHTS["ORGANIZER"],
                candidate_available=bool(candidate_organizers),
                event_available=bool(event_organizers),
                similarity=_set_overlap_similarity(candidate_organizers, event_organizers),
            ),
            _field_match_signal(
                kind="VENUE",
                weight=MATCH_WEIGHTS["VENUE"],
                candidate_available=bool(candidate_venues),
                event_available=bool(event_venues),
                similarity=_set_overlap_similarity(candidate_venues, event_venues),
            ),
            _field_match_signal(
                kind="SOURCE",
                weight=MATCH_WEIGHTS["SOURCE"],
                candidate_available=True,
                event_available=bool(event_source_ids),
                similarity=1.0 if source_id in event_source_ids else 0.0,
            ),
        ]
        weighted_contribution = sum(signal["contribution"] for signal in field_signals)
        score = weighted_contribution
        signals = [
            {
                "kind": "MATCH_SUMMARY",
                "match_percentage": round(score * 100, 2),
                "weighted_contribution_percentage": round(weighted_contribution * 100, 2),
                "evidence_signals": evidence_signals,
                "retrieval_reasons": sorted(retrieval_reasons[event.pk]),
            },
            {
                "kind": "SAME_SOURCE_REPRESENTATION",
                "matched": same_source_representation,
                "weighted": False,
            },
            *field_signals,
        ]
        if score >= MATCH_THRESHOLD:
            scored.append((score, event.pk, signals))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return CandidateMatch.objects.bulk_create(
        [
            CandidateMatch(
                event_candidate=candidate,
                event_id=event_id,
                rank=rank,
                score=score,
                signals=signals,
            )
            for rank, (score, event_id, signals) in enumerate(scored[:MAX_MATCHES], start=1)
        ]
    )


def _retrieve_candidate_event_ids(
    *,
    normalized_title: str,
    source_representation_id: int,
    candidate_urls: set[str],
    candidate_dates: set[date],
    candidate_organizers: set[str],
    candidate_venues: set[int],
) -> dict[int, set[str]]:
    reasons: defaultdict[int, set[str]] = defaultdict(set)

    def include(event_ids, reason: str) -> None:
        for event_id in event_ids:
            reasons[event_id].add(reason)

    if normalized_title:
        title_ids = (
            Event.objects.annotate(
                title_distance=TrigramDistance("normalized_title", normalized_title)
            )
            .order_by("title_distance")
            .values_list("pk", flat=True)[:TITLE_RETRIEVAL_LIMIT]
        )
        include(title_ids, "TITLE_TRIGRAM_NEAREST")

    include(
        EventSourceLink.objects.filter(
            source_representation_id=source_representation_id
        ).values_list("event_id", flat=True),
        "SAME_SOURCE_REPRESENTATION",
    )
    if candidate_urls:
        include(
            Event.objects.filter(
                Q(registrations__url__in=candidate_urls)
                | Q(occurrences__registrations__url__in=candidate_urls)
            )
            .distinct()
            .values_list("pk", flat=True),
            "REGISTRATION_URL_EXACT",
        )

    if candidate_dates:
        include(
            Event.objects.filter(occurrences__start_date__in=candidate_dates)
            .order_by("pk")
            .distinct()
            .values_list("pk", flat=True)[:STRUCTURED_RETRIEVAL_LIMIT],
            "OCCURRENCE_DATE_EXACT",
        )
    if candidate_organizers:
        include(
            Event.objects.filter(organizers__normalized_name__in=candidate_organizers)
            .order_by("pk")
            .distinct()
            .values_list("pk", flat=True)[:STRUCTURED_RETRIEVAL_LIMIT],
            "ORGANIZER_EXACT",
        )
    if candidate_venues:
        include(
            Event.objects.filter(occurrences__venues__pk__in=candidate_venues)
            .order_by("pk")
            .distinct()
            .values_list("pk", flat=True)[:STRUCTURED_RETRIEVAL_LIMIT],
            "VENUE_EXACT",
        )
    return dict(reasons)


def _field_match_signal(
    *,
    kind: str,
    weight: float,
    candidate_available: bool,
    event_available: bool,
    similarity: float,
) -> dict[str, Any]:
    comparable = candidate_available and event_available
    bounded_similarity = min(max(float(similarity), -2.0), 1.0) if comparable else 0.0
    contribution = weight * bounded_similarity
    return {
        "kind": kind,
        "candidate_available": candidate_available,
        "event_available": event_available,
        "weight": weight,
        "weight_percentage": round(weight * 100, 2),
        "similarity": round(bounded_similarity, 4),
        "similarity_percentage": round(bounded_similarity * 100, 2),
        "contribution": contribution,
        "contribution_percentage": round(contribution * 100, 2),
    }


def _date_similarity(left: set[date], right: set[date]) -> float:
    if not left or not right:
        return 0.0
    if left & right:
        return 1.0
    nearest_days = min(abs((a - b).days) for a in left for b in right)
    if nearest_days <= 1:
        return 0.4
    if nearest_days >= 120:
        return -2.0
    return 0.0


def _set_overlap_similarity(left: set[Any], right: set[Any]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))


def normalize_match_text(value: str) -> str:
    return " ".join(value.split()).casefold()


def normalize_match_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    hostname = (parsed.hostname or "").casefold()
    if hostname.startswith("www."):
        hostname = hostname[4:]
    port = f":{parsed.port}" if parsed.port else ""
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit(("https", f"{hostname}{port}", path, parsed.query, ""))
