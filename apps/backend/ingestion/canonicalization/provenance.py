from events.models import Event, EventObservation, EventSourceLink

from ingestion.models import EventCandidate


def link_observation(candidate: EventCandidate, event: Event) -> None:
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
