"""Read-only inventory of physical location wording and affected records."""

from collections import defaultdict

from django.db.models import Q
from events.models import EventOccurrence
from venues.resolution import VenueResolver, normalize_location

from ingestion.models import EventCandidate


def review_locations(*, source_ids=()):
    resolver = VenueResolver()
    groups = defaultdict(
        lambda: {
            "spellings": set(),
            "candidate_ids": set(),
            "event_ids": set(),
            "occurrence_ids": set(),
            "source_urls": set(),
            "suggested_venue_ids": set(),
            "current_venue_ids": set(),
        }
    )
    candidates = EventCandidate.objects.select_related("source_representation").order_by("pk")
    occurrences = (
        EventOccurrence.objects.filter(
            Q(attendance_mode__in=["IN_PERSON", "HYBRID"])
            | (Q(attendance_mode="UNKNOWN") & ~Q(raw_location_text=""))
        )
        .prefetch_related("venues")
        .order_by("pk")
    )
    if source_ids:
        candidates = candidates.filter(source_representation__source_id__in=source_ids)
        occurrences = occurrences.filter(
            event__source_links__source_representation__source_id__in=source_ids
        ).distinct()
    for candidate in candidates:
        for occurrence in candidate.effective_payload.get("occurrences", []):
            raw = occurrence.get("raw_location") or ""
            mode = occurrence.get("attendance_mode")
            if mode == "ONLINE" or (mode not in {"IN_PERSON", "HYBRID"} and not raw):
                continue
            row = groups[normalize_location(raw)]
            row["spellings"].add(raw)
            row["candidate_ids"].add(candidate.pk)
            row["source_urls"].add(candidate.source_representation.source_url)
            row["suggested_venue_ids"].update(occurrence.get("suggested_venue_ids", []))
    for occurrence in occurrences:
        raw = occurrence.raw_location_text
        row = groups[normalize_location(raw)]
        row["spellings"].add(raw)
        row["event_ids"].add(occurrence.event_id)
        row["occurrence_ids"].add(occurrence.pk)
        row["current_venue_ids"].update(venue.pk for venue in occurrence.venues.all())
    report = []
    for location, row in sorted(groups.items()):
        spellings = sorted(row["spellings"])
        resolutions = [resolver.resolve(raw) for raw in spellings]
        resolved = set(resolutions[0].venue_ids)
        # Distinct spellings may have different landmark boundaries; never merge those silently.
        consistent = all(set(result.venue_ids) == resolved for result in resolutions)
        needs_review = (
            not resolved
            or not consistent
            or any(
                ids and ids != resolved
                for ids in (row["suggested_venue_ids"], row["current_venue_ids"])
            )
            or (bool(row["occurrence_ids"]) and row["current_venue_ids"] != resolved)
        )
        report.append(
            {
                "location": location,
                "spellings": spellings,
                "resolved_venue_codes": [resolver.venues[pk].code for pk in sorted(resolved)]
                if consistent
                else [],
                "resolution_method": resolutions[0].method if consistent else "ambiguous",
                "needs_review": needs_review,
                **{key: sorted(value) for key, value in row.items() if key != "spellings"},
            }
        )
    return report
