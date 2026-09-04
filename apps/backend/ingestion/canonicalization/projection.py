from organizers.models import Organizer

from ingestion.canonicalization.matching import normalize_match_text
from ingestion.contracts import (
    CanonicalEventCreate,
    CanonicalizationAction,
    CanonicalizationProposal,
    CanonicalOccurrenceValue,
    CanonicalOrganizerValue,
    CanonicalRegistrationValue,
    EventCandidatePayload,
    RegistrationScope,
    TimePrecision,
)
from ingestion.http_urls import is_valid_http_url


def automatic_add_proposal(payload: EventCandidatePayload) -> CanonicalizationProposal:
    organizers: list[CanonicalOrganizerValue] = []
    seen_organizers: set[int] = set()
    for position, source in enumerate(payload.organizers):
        if not source.name:
            continue
        matches = list(
            Organizer.objects.filter(normalized_name=normalize_match_text(source.name))[:2]
        )
        if len(matches) != 1 or matches[0].pk in seen_organizers:
            continue
        seen_organizers.add(matches[0].pk)
        organizers.append(
            CanonicalOrganizerValue(
                organizer_id=matches[0].pk,
                role=source.role,
                is_primary=source.is_primary,
                position=position,
            )
        )
    occurrences = []
    projected_occurrence_refs: set[str] = set()
    for item in payload.occurrences:
        if item.start_date is None:
            continue
        start_time = item.start_time
        end_time = item.end_time
        time_precision = item.time_precision
        if item.is_all_day or time_precision == TimePrecision.DATE_ONLY:
            start_time = None
            end_time = None
        if time_precision == TimePrecision.EXACT and start_time is None:
            time_precision = TimePrecision.UNKNOWN
        if start_time is None or item.end_date is None:
            end_time = None
        occurrences.append(
            CanonicalOccurrenceValue(
                client_ref=item.local_ref,
                label=item.label,
                sequence=len(occurrences) + 1,
                start_date=item.start_date,
                start_time=start_time,
                end_date=item.end_date,
                end_time=end_time,
                time_precision=time_precision,
                is_all_day=item.is_all_day,
                attendance_mode=item.attendance_mode,
                raw_location_text=item.raw_location,
                meeting_url=(item.meeting_url if is_valid_http_url(item.meeting_url) else None),
                occurrence_status=item.status,
                venue_ids=item.suggested_venue_ids,
            )
        )
        projected_occurrence_refs.add(item.local_ref)

    registrations = []
    for item in payload.registrations:
        if (
            item.scope == RegistrationScope.OCCURRENCE
            and item.occurrence_ref not in projected_occurrence_refs
        ):
            continue
        url = item.url if is_valid_http_url(item.url) else None
        opens_time = item.opens_time if item.opens_date is not None else None
        closes_time = item.closes_time if item.closes_date is not None else None
        if not any(
            (
                bool(item.name and item.name.strip()),
                bool(url),
                bool(item.instructions and item.instructions.strip()),
                item.opens_date is not None,
                item.closes_date is not None,
            )
        ):
            continue
        registrations.append(
            CanonicalRegistrationValue(
                name=item.name,
                scope=item.scope,
                occurrence_id=None,
                occurrence_client_ref=(
                    item.occurrence_ref if item.scope == RegistrationScope.OCCURRENCE else None
                ),
                url=url,
                opens_date=item.opens_date,
                opens_time=opens_time,
                closes_date=item.closes_date,
                closes_time=closes_time,
                instructions=item.instructions,
            )
        )
    return CanonicalizationProposal(
        action=CanonicalizationAction.ADD,
        target_event_id=None,
        reasoning="No deterministic canonical Event match was found.",
        add_event=CanonicalEventCreate(
            title=(payload.title or "").strip(),
            description=payload.description,
            image_reference=(payload.image_url if is_valid_http_url(payload.image_url) else None),
            audience_notes=None,
            formats=payload.formats.supported_codes,
            topics=payload.topics.supported_codes,
            purposes=payload.purposes.supported_codes,
            audiences=payload.audiences.supported_codes,
            organizers=organizers,
            occurrences=occurrences,
            registrations=registrations,
        ),
        event_changes=[],
        classification_changes=[],
        organizer_changes=[],
        occurrence_changes=[],
        registration_changes=[],
    )
