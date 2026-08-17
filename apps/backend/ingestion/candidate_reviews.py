from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from django.utils.text import slugify
from events.models import (
    Event,
    EventAudience,
    EventFormat,
    EventOccurrence,
    EventOrganizer,
    EventProvenance,
    EventPurpose,
    EventTopic,
    OccurrenceVenue,
    PublicationStatus,
    Registration,
    RegistrationStatus,
    RegistrationType,
    VerificationStatus,
)
from events.models import (
    TimePrecision as CanonicalTimePrecision,
)
from organizers.models import Organizer
from pydantic import ValidationError as PydanticValidationError
from venues.models import Venue

from ingestion.contracts import (
    AttendanceMode,
    CandidateOccurrence,
    CandidateRegistration,
    EventCandidatePayload,
    RegistrationScope,
)
from ingestion.models import (
    CandidateReview,
    CandidateReviewOccurrence,
    CandidateReviewRegistration,
    EventCandidate,
    PromotionMethod,
    ReviewStatus,
    ReviewSyncStatus,
)
from ingestion.reference_data import build_candidate_reference_data
from ingestion.validation import is_valid_http_url, validate_candidate


class ReviewVersionConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class ReviewSyncResult:
    review_id: int
    sync_status: str
    event_id: int | None
    message: str = ""


def create_review_and_sync(
    candidate: EventCandidate,
    *,
    reference_data: dict[str, Any] | None = None,
) -> CandidateReview:
    reference_data = reference_data or build_candidate_reference_data()
    payload, issues = _parse_and_validate(candidate.payload, reference_data)
    existing_provenance = (
        EventProvenance.objects.filter(event_candidate=candidate).select_related("event").first()
    )
    review, created = CandidateReview.objects.get_or_create(
        event_candidate=candidate,
        defaults={
            "canonical_event": existing_provenance.event if existing_provenance else None,
            "effective_payload": candidate.payload,
            "validation_issues": issues,
            "review_status": (
                ReviewStatus.NOT_REQUIRED
                if payload is not None and not issues
                else ReviewStatus.NEEDS_REVIEW
            ),
        },
    )
    if created:
        synchronize_review(
            review.pk,
            expected_version=review.review_version,
            reference_data=reference_data,
        )
        review.refresh_from_db()
    return review


def synchronize_review(
    review_id: int,
    *,
    expected_version: int,
    reference_data: dict[str, Any] | None = None,
) -> ReviewSyncResult:
    try:
        return _synchronize_review(
            review_id,
            expected_version=expected_version,
            reference_data=reference_data,
        )
    except ReviewVersionConflict:
        raise
    except Exception as exc:  # keep the review even when projection fails unexpectedly
        message = f"{type(exc).__name__}: {exc}"[:2000]
        CandidateReview.objects.filter(
            pk=review_id,
            review_version=expected_version,
        ).update(sync_status=ReviewSyncStatus.FAILED, sync_error=message)
        review = CandidateReview.objects.filter(pk=review_id).only("canonical_event_id").first()
        return ReviewSyncResult(
            review_id=review_id,
            sync_status=ReviewSyncStatus.FAILED,
            event_id=review.canonical_event_id if review else None,
            message=message,
        )


@transaction.atomic
def _synchronize_review(
    review_id: int,
    *,
    expected_version: int,
    reference_data: dict[str, Any] | None,
) -> ReviewSyncResult:
    review = (
        CandidateReview.objects.select_for_update()
        .select_related("event_candidate")
        .get(pk=review_id)
    )
    if review.review_version != expected_version:
        raise ReviewVersionConflict(
            f"Review {review_id} changed from version {expected_version} "
            f"to {review.review_version}; reload before saving again."
        )
    if (
        review.sync_status == ReviewSyncStatus.SYNCED
        and review.synced_version == review.review_version
    ):
        return ReviewSyncResult(
            review_id=review.pk,
            sync_status=review.sync_status,
            event_id=review.canonical_event_id,
        )

    if review.review_status == ReviewStatus.REJECTED:
        return _synchronize_rejection(review)

    reference_data = reference_data or build_candidate_reference_data()
    payload, issues = _parse_and_validate(review.effective_payload, reference_data)
    if payload is not None:
        issues.extend(_organizer_issues(payload))
        issues.extend(_duplicate_event_issues(review, payload))

    blockers = [issue for issue in issues if issue.get("blocks_canonicalization")]
    review.validation_issues = issues
    if review.review_status == ReviewStatus.NOT_REQUIRED and issues:
        review.review_status = ReviewStatus.NEEDS_REVIEW
    elif (
        review.review_status == ReviewStatus.NEEDS_REVIEW
        and not review.has_manual_edits
        and not issues
    ):
        review.review_status = ReviewStatus.NOT_REQUIRED

    if payload is None or blockers:
        if review.review_status == ReviewStatus.APPROVED:
            review.review_status = ReviewStatus.NEEDS_REVIEW
        review.sync_status = ReviewSyncStatus.BLOCKED
        review.sync_error = _blocking_message(blockers or issues)
        review.save(
            update_fields=(
                "validation_issues",
                "review_status",
                "sync_status",
                "sync_error",
                "updated_at",
            )
        )
        return ReviewSyncResult(
            review_id=review.pk,
            sync_status=review.sync_status,
            event_id=review.canonical_event_id,
            message=review.sync_error,
        )

    event = _upsert_event(review, payload)
    _synchronize_classifications(event, payload)
    _synchronize_organizers(event, payload)
    occurrence_by_ref = _synchronize_occurrences(review, event, payload, reference_data)
    _synchronize_registrations(review, event, payload, occurrence_by_ref)
    _synchronize_provenance(review, event)

    review.canonical_event = event
    review.sync_status = ReviewSyncStatus.SYNCED
    review.synced_version = review.review_version
    review.promotion_method = (
        PromotionMethod.MANUAL
        if review.has_manual_edits or review.review_status == ReviewStatus.APPROVED
        else PromotionMethod.AUTOMATIC
    )
    review.last_synced_at = timezone.now()
    review.sync_error = ""
    review.save(
        update_fields=(
            "canonical_event",
            "validation_issues",
            "review_status",
            "sync_status",
            "synced_version",
            "promotion_method",
            "last_synced_at",
            "sync_error",
            "updated_at",
        )
    )
    return ReviewSyncResult(
        review_id=review.pk,
        sync_status=review.sync_status,
        event_id=event.pk,
    )


def _synchronize_rejection(review: CandidateReview) -> ReviewSyncResult:
    event = review.canonical_event
    if event is not None:
        event.publication_status = PublicationStatus.WITHHELD
        event.verification_status = VerificationStatus.UNVERIFIED
        event.last_verified_at = None
        event.save(
            update_fields=(
                "publication_status",
                "verification_status",
                "last_verified_at",
                "updated_at",
            )
        )
    review.sync_status = ReviewSyncStatus.SYNCED
    review.synced_version = review.review_version
    review.promotion_method = PromotionMethod.MANUAL
    review.last_synced_at = timezone.now()
    review.sync_error = ""
    review.save(
        update_fields=(
            "sync_status",
            "synced_version",
            "promotion_method",
            "last_synced_at",
            "sync_error",
            "updated_at",
        )
    )
    return ReviewSyncResult(
        review_id=review.pk,
        sync_status=review.sync_status,
        event_id=review.canonical_event_id,
    )


def _parse_and_validate(
    raw_payload: object,
    reference_data: dict[str, Any],
) -> tuple[EventCandidatePayload | None, list[dict[str, object]]]:
    try:
        payload = EventCandidatePayload.model_validate(raw_payload)
    except PydanticValidationError as exc:
        return None, [
            {
                "code": "STRUCTURAL_PAYLOAD_INVALID",
                "path": ".".join(str(part) for part in error.get("loc", ())),
                "message": error.get("msg", "The review payload is structurally invalid."),
                "severity": "ERROR",
                "blocks_canonicalization": True,
            }
            for error in exc.errors(include_url=False)
        ]
    validation = validate_candidate(payload, reference_data)
    return payload, list(validation.issues)


def _duplicate_event_issues(
    review: CandidateReview,
    payload: EventCandidatePayload,
) -> list[dict[str, object]]:
    if review.allow_duplicate or not payload.title or not payload.title.strip():
        return []
    duplicates = Event.objects.filter(normalized_title=_normalize(payload.title))
    if review.canonical_event_id:
        duplicates = duplicates.exclude(pk=review.canonical_event_id)
    duplicate_ids = list(duplicates.order_by("pk").values_list("pk", flat=True)[:10])
    if not duplicate_ids:
        return []
    return [
        {
            "code": "POSSIBLE_DUPLICATE_EVENT",
            "path": "title",
            "message": f"Exact normalized-title matches exist for event IDs {duplicate_ids}.",
            "severity": "ERROR",
            "blocks_canonicalization": True,
        }
    ]


def _organizer_issues(payload: EventCandidatePayload) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    seen_organizer_ids: set[int] = set()
    primary_count = sum(1 for item in payload.organizers if item.is_primary)
    if primary_count > 1:
        issues.append(
            {
                "code": "MULTIPLE_PRIMARY_ORGANIZERS",
                "path": "organizers",
                "message": "More than one organizer is marked as primary.",
                "severity": "WARNING",
                "blocks_canonicalization": False,
            }
        )
    for index, item in enumerate(payload.organizers):
        name = item.name.strip() if item.name else ""
        if not name:
            continue
        matches = list(Organizer.objects.filter(normalized_name=_normalize(name))[:2])
        if len(matches) != 1:
            issues.append(
                {
                    "code": "ORGANIZER_UNRESOLVED",
                    "path": f"organizers.{index}.name",
                    "message": (
                        f"Organizer {name!r} does not resolve to exactly one known organizer."
                    ),
                    "severity": "WARNING",
                    "blocks_canonicalization": False,
                }
            )
            continue
        if matches[0].pk in seen_organizer_ids:
            issues.append(
                {
                    "code": "ORGANIZER_DUPLICATE",
                    "path": f"organizers.{index}",
                    "message": f"Organizer {name!r} appears more than once.",
                    "severity": "WARNING",
                    "blocks_canonicalization": False,
                }
            )
        seen_organizer_ids.add(matches[0].pk)
    return issues


def _upsert_event(review: CandidateReview, payload: EventCandidatePayload) -> Event:
    title = payload.title.strip()  # title validation guarantees a usable value
    verification_status = _verification_status(review)
    verified_at = (
        timezone.now()
        if verification_status
        in (VerificationStatus.AUTOMATICALLY_VERIFIED, VerificationStatus.MANUALLY_VERIFIED)
        else None
    )
    image_reference = payload.image_url if is_valid_http_url(payload.image_url) else ""
    event = review.canonical_event
    if event is None:
        event = Event.objects.create(
            slug=_candidate_slug(title, review.event_candidate_id),
            title=title,
            normalized_title=_normalize(title),
            description=payload.description or "",
            publication_status=PublicationStatus.DRAFT,
            verification_status=verification_status,
            image_reference=image_reference,
            last_verified_at=verified_at,
        )
    else:
        event.title = title
        event.normalized_title = _normalize(title)
        event.description = payload.description or ""
        event.image_reference = image_reference
        event.verification_status = verification_status
        event.last_verified_at = verified_at
        if event.publication_status == PublicationStatus.WITHHELD:
            event.publication_status = PublicationStatus.DRAFT
        event.save(
            update_fields=(
                "title",
                "normalized_title",
                "description",
                "image_reference",
                "verification_status",
                "last_verified_at",
                "publication_status",
                "updated_at",
            )
        )
    return event


def _verification_status(review: CandidateReview) -> str:
    if review.review_status == ReviewStatus.APPROVED:
        return VerificationStatus.MANUALLY_VERIFIED
    if review.review_status == ReviewStatus.NOT_REQUIRED:
        return VerificationStatus.AUTOMATICALLY_VERIFIED
    return VerificationStatus.UNVERIFIED


def _synchronize_classifications(event: Event, payload: EventCandidatePayload) -> None:
    for relation, model, selection in (
        (event.formats, EventFormat, payload.formats),
        (event.topics, EventTopic, payload.topics),
        (event.purposes, EventPurpose, payload.purposes),
        (event.audiences, EventAudience, payload.audiences),
    ):
        relation.set(model.objects.filter(is_active=True, code__in=set(selection.supported_codes)))


def _synchronize_organizers(event: Event, payload: EventCandidatePayload) -> None:
    EventOrganizer.objects.filter(event=event).delete()
    resolved: list[tuple[Organizer, object]] = []
    seen_ids: set[int] = set()
    for item in payload.organizers:
        if not item.name or not item.name.strip():
            continue
        matches = list(Organizer.objects.filter(normalized_name=_normalize(item.name))[:2])
        if len(matches) != 1 or matches[0].pk in seen_ids:
            continue
        seen_ids.add(matches[0].pk)
        resolved.append((matches[0], item))
    primary_indexes = [
        index for index, (_organizer, item) in enumerate(resolved) if item.is_primary
    ]
    primary_index = primary_indexes[0] if len(primary_indexes) == 1 else None
    EventOrganizer.objects.bulk_create(
        [
            EventOrganizer(
                event=event,
                organizer=organizer,
                role=item.role or "",
                is_primary=index == primary_index,
                position=index,
            )
            for index, (organizer, item) in enumerate(resolved)
        ]
    )


def _synchronize_occurrences(
    review: CandidateReview,
    event: Event,
    payload: EventCandidatePayload,
    reference_data: dict[str, Any],
) -> dict[str, EventOccurrence]:
    links = {
        link.local_ref: link for link in review.occurrence_links.select_related("occurrence").all()
    }
    if links:
        EventOccurrence.objects.filter(candidate_review_link__review=review).update(
            sequence=F("sequence") + 10000
        )
    supported_venue_ids = {
        int(item["id"])
        for item in reference_data.get("venues", [])
        if isinstance(item, dict) and isinstance(item.get("id"), int)
    }
    kept_refs: set[str] = set()
    occurrences: dict[str, EventOccurrence] = {}
    for index, source in enumerate(payload.occurrences):
        if not _occurrence_is_projectable(source):
            continue
        kept_refs.add(source.local_ref)
        link = links.get(source.local_ref)
        if link is None:
            occurrence = EventOccurrence(event=event)
        else:
            occurrence = link.occurrence
        occurrence.sequence = index + 1
        occurrence.label = source.label or ""
        occurrence.start_date = source.start_date
        occurrence.start_time = source.start_time
        occurrence.end_date = source.end_date
        occurrence.end_time = source.end_time
        occurrence.time_precision = source.time_precision.value
        occurrence.is_all_day = source.is_all_day
        occurrence.attendance_mode = source.attendance_mode.value
        occurrence.raw_location_text = source.raw_location or ""
        occurrence.meeting_url = (
            source.meeting_url
            if source.attendance_mode in (AttendanceMode.ONLINE, AttendanceMode.HYBRID)
            and is_valid_http_url(source.meeting_url)
            else ""
        )
        occurrence.occurrence_status = source.status.value
        occurrence.save()
        if link is None:
            CandidateReviewOccurrence.objects.create(
                review=review,
                local_ref=source.local_ref,
                occurrence=occurrence,
            )
        _synchronize_occurrence_venues(
            occurrence,
            source,
            supported_venue_ids=supported_venue_ids,
        )
        occurrences[source.local_ref] = occurrence

    for local_ref, link in links.items():
        if local_ref not in kept_refs:
            link.occurrence.delete()
    return occurrences


def _occurrence_is_projectable(source: CandidateOccurrence) -> bool:
    if source.start_date is None:
        return False
    if source.end_date is not None and source.end_date < source.start_date:
        return False
    if source.end_time is not None and (source.end_date is None or source.start_time is None):
        return False
    if (
        source.end_date == source.start_date
        and source.start_time is not None
        and source.end_time is not None
        and source.end_time < source.start_time
    ):
        return False
    if source.is_all_day and (source.start_time is not None or source.end_time is not None):
        return False
    if source.time_precision.value == CanonicalTimePrecision.EXACT and source.start_time is None:
        return False
    if source.time_precision.value == CanonicalTimePrecision.DATE_ONLY and (
        source.start_time is not None or source.end_time is not None
    ):
        return False
    return True


def _synchronize_occurrence_venues(
    occurrence: EventOccurrence,
    source: CandidateOccurrence,
    *,
    supported_venue_ids: set[int],
) -> None:
    OccurrenceVenue.objects.filter(occurrence=occurrence).delete()
    if source.attendance_mode == AttendanceMode.ONLINE:
        return
    venue_ids = list(
        dict.fromkeys(
            venue_id for venue_id in source.suggested_venue_ids if venue_id in supported_venue_ids
        )
    )
    venues = {venue.pk: venue for venue in Venue.objects.filter(pk__in=venue_ids)}
    OccurrenceVenue.objects.bulk_create(
        [
            OccurrenceVenue(
                occurrence=occurrence,
                venue=venues[venue_id],
                is_primary=position == 0,
                position=position,
            )
            for position, venue_id in enumerate(venue_ids)
            if venue_id in venues
        ]
    )


def _synchronize_registrations(
    review: CandidateReview,
    event: Event,
    payload: EventCandidatePayload,
    occurrence_by_ref: dict[str, EventOccurrence],
) -> None:
    links = {
        link.source_index: link
        for link in review.registration_links.select_related("registration").all()
    }
    kept_indexes: set[int] = set()
    for index, source in enumerate(payload.registrations):
        owners = _registration_owners(event, source, occurrence_by_ref)
        if owners is None or not _registration_is_projectable(source):
            continue
        event_owner, occurrence_owner = owners
        kept_indexes.add(index)
        link = links.get(index)
        if link is None:
            registration = Registration()
        else:
            registration = link.registration
        registration.event = event_owner
        registration.occurrence = occurrence_owner
        registration.name = (source.name or "").strip() or "Registration"
        registration.registration_type = RegistrationType.ATTENDEE
        registration.url = source.url if is_valid_http_url(source.url) else ""
        registration.opens_date = source.opens_date
        registration.opens_time = source.opens_time if source.opens_date is not None else None
        registration.closes_date = source.closes_date
        registration.closes_time = source.closes_time if source.closes_date is not None else None
        registration.time_precision = CanonicalTimePrecision.UNKNOWN
        registration.instructions = source.instructions or ""
        registration.status = RegistrationStatus.UNKNOWN
        registration.save()
        if link is None:
            CandidateReviewRegistration.objects.create(
                review=review,
                source_index=index,
                registration=registration,
            )

    for index, link in links.items():
        if index not in kept_indexes:
            link.registration.delete()


def _registration_owners(
    event: Event,
    source: CandidateRegistration,
    occurrence_by_ref: dict[str, EventOccurrence],
) -> tuple[Event | None, EventOccurrence | None] | None:
    if source.scope == RegistrationScope.EVENT:
        return event, None
    if not source.occurrence_ref or source.occurrence_ref not in occurrence_by_ref:
        return None
    return None, occurrence_by_ref[source.occurrence_ref]


def _registration_is_projectable(source: CandidateRegistration) -> bool:
    has_meaningful_detail = any(
        (
            bool(source.name and source.name.strip()),
            is_valid_http_url(source.url),
            bool(source.instructions and source.instructions.strip()),
            source.opens_date is not None,
            source.closes_date is not None,
        )
    )
    if not has_meaningful_detail:
        return False
    if (
        source.opens_date is not None
        and source.closes_date is not None
        and source.closes_date < source.opens_date
    ):
        return False
    if (
        source.opens_date is not None
        and source.closes_date == source.opens_date
        and source.opens_time is not None
        and source.closes_time is not None
        and source.closes_time < source.opens_time
    ):
        return False
    return True


def _synchronize_provenance(review: CandidateReview, event: Event) -> None:
    provenance, created = EventProvenance.objects.get_or_create(
        event_candidate=review.event_candidate,
        defaults={
            "event": event,
            "source_representation": review.event_candidate.source_representation,
            "is_primary_source": True,
        },
    )
    if not created and provenance.event_id != event.pk:
        raise RuntimeError(
            f"Candidate {review.event_candidate_id} is already linked to event "
            f"{provenance.event_id}."
        )


def _candidate_slug(title: str, candidate_id: int) -> str:
    suffix = f"-{candidate_id}"
    base = slugify(title)[: 255 - len(suffix)] or "event"
    proposed = f"{base}{suffix}"
    if not Event.objects.filter(slug=proposed).exists():
        return proposed
    counter = 2
    while True:
        counter_suffix = f"-{candidate_id}-{counter}"
        proposed = f"{base[: 255 - len(counter_suffix)]}{counter_suffix}"
        if not Event.objects.filter(slug=proposed).exists():
            return proposed
        counter += 1


def _blocking_message(issues: list[dict[str, object]]) -> str:
    codes = [str(issue.get("code", "UNKNOWN")) for issue in issues]
    return f"Canonical synchronization is blocked by: {', '.join(codes)}"[:2000]


def _normalize(value: str) -> str:
    return " ".join(value.split()).casefold()
