from __future__ import annotations

from django.utils.text import slugify
from events.models import (
    Event,
    EventAudience,
    EventFormat,
    EventOrganizer,
    EventPurpose,
    EventTopic,
    PublicationStatus,
    VerificationStatus,
)

from ingestion.canonicalization.matching import normalize_match_text
from ingestion.canonicalization.schedule_mutations import (
    apply_occurrence_changes,
    apply_registration_changes,
    create_occurrence,
    create_registration,
)
from ingestion.contracts import (
    CanonicalEventCreate,
    CanonicalizationProposal,
    CanonicalOrganizerChange,
    ClassificationKind,
    ClassificationOperation,
    EventField,
    FieldOperation,
    ObjectOperation,
    OrganizerField,
)
from ingestion.models import CanonicalizationPlan


def apply_add(plan: CanonicalizationPlan, value: CanonicalEventCreate | None) -> Event:
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
    occurrences = {}
    for item in value.occurrences:
        occurrence = create_occurrence(event, item)
        if item.client_ref:
            occurrences[item.client_ref] = occurrence
    for item in value.registrations:
        create_registration(event, item, occurrences)
    event.save(update_fields=("updated_at",))
    return event


def apply_update(event: Event, proposal: CanonicalizationProposal) -> Event:
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
    added_occurrences = apply_occurrence_changes(event, proposal.occurrence_changes)
    apply_registration_changes(event, proposal.registration_changes, added_occurrences)
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
