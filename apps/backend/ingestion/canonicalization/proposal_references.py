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
from venues.models import Venue

from ingestion.canonicalization.proposal_issues import hard_issue
from ingestion.contracts import CanonicalizationProposal, ObjectOperation


def validate_catalogs(formats, topics, purposes, audiences, issues) -> None:
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
                hard_issue(
                    "UNSUPPORTED_CLASSIFICATION_CODE", path, f"Unsupported codes: {unknown}."
                )
            )


def validate_organizer_ids(ids: list[int], issues: list[dict[str, Any]]) -> None:
    supplied = set(ids)
    existing = set(Organizer.objects.filter(pk__in=supplied).values_list("pk", flat=True))
    if supplied - existing:
        issues.append(
            hard_issue(
                "ORGANIZER_NOT_FOUND",
                "organizers",
                f"Organizer IDs do not exist: {sorted(supplied - existing)}.",
            )
        )


def validate_venue_ids(ids: list[int], issues: list[dict[str, Any]]) -> None:
    supplied = set(ids)
    existing = set(Venue.objects.filter(pk__in=supplied).values_list("pk", flat=True))
    if supplied - existing:
        issues.append(
            hard_issue(
                "VENUE_NOT_FOUND",
                "occurrences.venue_ids",
                f"Venue IDs do not exist: {sorted(supplied - existing)}.",
            )
        )


def validate_owned_ids(
    event: Event,
    proposal: CanonicalizationProposal,
    issues: list[dict[str, Any]],
) -> None:
    for path, model, changes, owner_filter in (
        ("organizer_changes", EventOrganizer, proposal.organizer_changes, {"event": event}),
        ("occurrence_changes", EventOccurrence, proposal.occurrence_changes, {"event": event}),
        ("registration_changes", Registration, proposal.registration_changes, {}),
    ):
        ids = {item.id for item in changes if item.operation != ObjectOperation.ADD and item.id}
        queryset = model.objects.filter(pk__in=ids, **owner_filter)
        if model is Registration:
            queryset = queryset.filter(Q(event=event) | Q(occurrence__event=event))
        existing = set(queryset.values_list("pk", flat=True))
        if ids - existing:
            issues.append(
                hard_issue(
                    "CHILD_NOT_FOUND_OR_WRONG_OWNER",
                    path,
                    f"Child IDs are missing or belong to another Event: {sorted(ids - existing)}.",
                )
            )
