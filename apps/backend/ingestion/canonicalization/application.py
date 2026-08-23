from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import F, Max, Q
from django.utils import timezone
from django.utils.text import slugify
from events.models import (
    Event,
    EventAudience,
    EventFormat,
    EventObservation,
    EventOccurrence,
    EventOrganizer,
    EventPurpose,
    EventRevision,
    EventSourceLink,
    EventTopic,
    OccurrenceVenue,
    PublicationStatus,
    Registration,
    RegistrationStatus,
    RegistrationType,
    VerificationStatus,
)

from ingestion.candidates import CandidateVersionConflict
from ingestion.canonicalization.matching import normalize_match_text
from ingestion.canonicalization.proposals import validate_proposal
from ingestion.contracts import (
    AttendanceMode,
    CanonicalEventCreate,
    CanonicalizationAction,
    CanonicalizationProposal,
    CanonicalOccurrenceChange,
    CanonicalOccurrenceValue,
    CanonicalOrganizerChange,
    ClassificationKind,
    ClassificationOperation,
    EventField,
    FieldOperation,
    ObjectOperation,
    OccurrenceField,
    OrganizerField,
    RegistrationField,
    RegistrationScope,
)
from ingestion.models import (
    CanonicalizationPlan,
    CanonicalizationPlanStatus,
    EventCandidate,
)


@dataclass(frozen=True)
class PlanResult:
    plan_id: int | None
    status: str
    event_id: int | None
    message: str = ""


def apply_canonicalization_plan(plan_id: int, *, expected_version: int) -> PlanResult:
    try:
        return _apply_canonicalization_plan(plan_id, expected_version=expected_version)
    except CandidateVersionConflict:
        raise
    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"[:2000]
        CanonicalizationPlan.objects.filter(
            pk=plan_id,
            plan_version=expected_version,
        ).update(status=CanonicalizationPlanStatus.FAILED, application_error=message)
        return PlanResult(plan_id, CanonicalizationPlanStatus.FAILED, None, message)


@transaction.atomic
def _apply_canonicalization_plan(plan_id: int, *, expected_version: int) -> PlanResult:
    plan = (
        CanonicalizationPlan.objects.select_for_update()
        .select_related("event_candidate__source_representation")
        .get(pk=plan_id)
    )
    if plan.plan_version != expected_version:
        raise CandidateVersionConflict(
            f"Plan {plan_id} changed from version {expected_version} "
            f"to {plan.plan_version}; reload before applying."
        )
    if (
        plan.status == CanonicalizationPlanStatus.APPLIED
        and plan.applied_version == expected_version
    ):
        return PlanResult(plan.pk, plan.status, plan.target_event_id)
    if plan.status != CanonicalizationPlanStatus.READY:
        return PlanResult(plan.pk, plan.status, plan.target_event_id, "Plan is not ready.")

    proposal = CanonicalizationProposal.model_validate(plan.effective_proposal)
    issues = validate_proposal(plan.event_candidate, proposal)
    if issues:
        plan.validation_issues = issues
        plan.status = CanonicalizationPlanStatus.REJECTED
        plan.save(update_fields=("validation_issues", "status", "updated_at"))
        return PlanResult(plan.pk, plan.status, plan.target_event_id, "Plan validation failed.")

    target = None
    before: dict[str, Any] = {}
    if proposal.target_event_id is not None:
        target = Event.objects.select_for_update().get(pk=proposal.target_event_id)
        if event_snapshot_hash(target) != plan.target_snapshot_hash:
            plan.status = CanonicalizationPlanStatus.STALE
            plan.application_error = "The target Event changed after this plan was generated."
            plan.save(update_fields=("status", "application_error", "updated_at"))
            return PlanResult(plan.pk, plan.status, target.pk, plan.application_error)
        before = event_snapshot(target)

    if proposal.action == CanonicalizationAction.ADD:
        event = _apply_add(plan, proposal.add_event)
    elif proposal.action == CanonicalizationAction.UPDATE:
        if target is None:
            raise RuntimeError("UPDATE plan has no target Event")
        event = _apply_update(target, proposal)
    else:
        if target is None:
            raise RuntimeError("LINK_ONLY plan has no target Event")
        event = target

    _link_observation(plan.event_candidate, event)
    after = event_snapshot(event)
    if proposal.action != CanonicalizationAction.LINK_ONLY:
        revision_number = (
            EventRevision.objects.filter(event=event).aggregate(maximum=Max("revision_number"))[
                "maximum"
            ]
            or 0
        ) + 1
        EventRevision.objects.create(
            event=event,
            canonicalization_plan=plan,
            revision_number=revision_number,
            before_snapshot=before,
            after_snapshot=after,
        )

    plan.target_event = event
    plan.target_event_updated_at = event.updated_at
    plan.target_snapshot_hash = event_snapshot_hash(event)
    plan.applied_snapshot = after
    plan.applied_version = plan.plan_version
    plan.applied_at = timezone.now()
    plan.status = CanonicalizationPlanStatus.APPLIED
    plan.application_error = ""
    plan.save()
    return PlanResult(plan.pk, plan.status, event.pk)


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


def _apply_add(plan: CanonicalizationPlan, value: CanonicalEventCreate | None) -> Event:
    if value is None:
        raise RuntimeError("ADD plan has no event payload")
    event = Event.objects.create(
        slug=_candidate_slug(value.title, plan.event_candidate_id),
        title=value.title.strip(),
        normalized_title=normalize_match_text(value.title),
        description=value.description or "",
        image_reference=value.image_reference or "",
        audience_notes=value.audience_notes or "",
        publication_status=PublicationStatus.DRAFT,
        verification_status=VerificationStatus.UNVERIFIED,
    )
    _set_classifications(event, value.formats, value.topics, value.purposes, value.audiences)
    for item in value.organizers:
        EventOrganizer.objects.create(event=event, **item.model_dump())
    occurrences: dict[str, EventOccurrence] = {}
    for item in value.occurrences:
        occurrence = _create_occurrence(event, item)
        if item.client_ref:
            occurrences[item.client_ref] = occurrence
    for item in value.registrations:
        _create_registration(event, item, occurrences)
    event.save(update_fields=("updated_at",))
    return event


def _apply_update(event: Event, proposal: CanonicalizationProposal) -> Event:
    field_map = {
        EventField.TITLE: "title",
        EventField.DESCRIPTION: "description",
        EventField.IMAGE_REFERENCE: "image_reference",
        EventField.AUDIENCE_NOTES: "audience_notes",
    }
    changed_event_fields: set[str] = set()
    for change in proposal.event_changes:
        field = field_map[change.field]
        value = change.value if change.operation == FieldOperation.SET else ""
        setattr(event, field, value)
        changed_event_fields.add(field)
        if field == "title":
            event.normalized_title = normalize_match_text(value or "")
            changed_event_fields.add("normalized_title")
    if changed_event_fields:
        event.save(update_fields=(*sorted(changed_event_fields), "updated_at"))

    for change in proposal.classification_changes:
        relation, model = {
            ClassificationKind.FORMAT: (event.formats, EventFormat),
            ClassificationKind.TOPIC: (event.topics, EventTopic),
            ClassificationKind.PURPOSE: (event.purposes, EventPurpose),
            ClassificationKind.AUDIENCE: (event.audiences, EventAudience),
        }[change.kind]
        values = model.objects.filter(code__in=change.codes, is_active=True)
        if change.operation == ClassificationOperation.ADD_CODES:
            relation.add(*values)
        elif change.operation == ClassificationOperation.REMOVE_CODES:
            relation.remove(*values)
        else:
            relation.set(values)

    _apply_organizer_changes(event, proposal.organizer_changes)
    added_occurrences = _apply_occurrence_changes(event, proposal.occurrence_changes)
    _apply_registration_changes(
        event,
        proposal.registration_changes,
        added_occurrences,
    )
    event.save(update_fields=("updated_at",))
    return event


def _set_classifications(event, formats, topics, purposes, audiences) -> None:
    for relation, model, codes in (
        (event.formats, EventFormat, formats),
        (event.topics, EventTopic, topics),
        (event.purposes, EventPurpose, purposes),
        (event.audiences, EventAudience, audiences),
    ):
        relation.set(model.objects.filter(code__in=codes, is_active=True))


def _apply_organizer_changes(event, changes: list[CanonicalOrganizerChange]) -> None:
    if not changes:
        return
    existing = {item.pk: item for item in event.eventorganizer_set.all()}
    EventOrganizer.objects.filter(event=event).update(is_primary=False)
    desired_primary: set[int] = {item.pk for item in existing.values() if item.is_primary}
    for change in changes:
        if change.operation == ObjectOperation.REMOVE:
            existing[change.id].delete()
            desired_primary.discard(change.id)
        elif change.operation == ObjectOperation.ADD:
            value = change.value
            created = EventOrganizer.objects.create(
                event=event,
                organizer_id=value.organizer_id,
                role=value.role or "",
                is_primary=False,
                position=value.position,
            )
            if value.is_primary:
                desired_primary = {created.pk}
        else:
            item = existing[change.id]
            value = change.value
            for field in change.changed_fields:
                attr = field.value.lower()
                setattr(
                    item,
                    attr,
                    getattr(value, attr) or "" if attr == "role" else getattr(value, attr),
                )
            item.is_primary = False
            item.save()
            if OrganizerField.IS_PRIMARY in change.changed_fields:
                if value.is_primary:
                    desired_primary = {item.pk}
                else:
                    desired_primary.discard(item.pk)
    if desired_primary:
        EventOrganizer.objects.filter(pk=next(iter(desired_primary))).update(is_primary=True)


def _apply_occurrence_changes(
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
            occurrence = _create_occurrence(event, change.value)
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


def _apply_registration_changes(event, changes, added_occurrences) -> None:
    existing = {
        item.pk: item
        for item in Registration.objects.filter(Q(event=event) | Q(occurrence__event=event))
    }
    for change in changes:
        if change.operation == ObjectOperation.REMOVE:
            existing[change.id].delete()
        elif change.operation == ObjectOperation.ADD:
            _create_registration(event, change.value, added_occurrences)
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


def _create_occurrence(event, value: CanonicalOccurrenceValue) -> EventOccurrence:
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


def _create_registration(event, value, added_occurrences) -> Registration:
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


def _link_observation(candidate: EventCandidate, event: Event) -> None:
    representation = candidate.source_representation
    link, _created = EventSourceLink.objects.get_or_create(
        event=event,
        source_representation=representation,
        defaults={"is_primary_source": not event.source_links.exists()},
    )
    existing = EventObservation.objects.filter(event_candidate=candidate).first()
    if existing is not None and existing.source_link_id != link.pk:
        raise RuntimeError("The EventCandidate is already linked to another canonical Event.")
    EventObservation.objects.get_or_create(
        source_link=link,
        event_candidate=candidate,
        defaults={"observation_type": candidate.observation_type},
    )


def _candidate_slug(title: str, candidate_id: int) -> str:
    suffix = f"-{candidate_id}"
    base = slugify(title)[: 255 - len(suffix)] or "event"
    proposed = f"{base}{suffix}"
    counter = 2
    while Event.objects.filter(slug=proposed).exists():
        counter_suffix = f"-{candidate_id}-{counter}"
        proposed = f"{base[: 255 - len(counter_suffix)]}{counter_suffix}"
        counter += 1
    return proposed


def _iso(value):
    return value.isoformat() if value is not None else None
