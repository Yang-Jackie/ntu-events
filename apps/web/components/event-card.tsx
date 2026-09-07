import Link from "next/link";

import type { EventListItem } from "@/lib/api";
import {
  attendanceLabel,
  formatOccurrenceWhen,
  occurrenceLocation,
} from "@/lib/event-formatting";

type EventCardProps = {
  event: EventListItem;
  returnPath: string;
};

export function EventCard({ event, returnPath }: EventCardProps) {
  const occurrence = event.occurrences[0];
  const organizer =
    event.organizers.find((item) => item.is_primary) ?? event.organizers[0];
  const detailHref = `/events/${event.id}?from=${encodeURIComponent(returnPath)}`;

  return (
    <article className="event-card" id={`event-${event.id}`}>
      <Link href={detailHref} className="event-card__link">
        <div className="event-card__date">
          {occurrence ? formatOccurrenceWhen(occurrence) : "Date TBA"}
        </div>
        <h2>{event.title}</h2>
        <p className="event-card__location">
          <span aria-hidden="true">⌖</span>
          {occurrence
            ? occurrenceLocation(occurrence)
            : "Location not confirmed"}
        </p>
        <div className="event-card__meta">
          {occurrence ? (
            <span>{attendanceLabel(occurrence.attendance_mode)}</span>
          ) : null}
          {organizer ? <span>{organizer.name}</span> : null}
        </div>
        {event.formats.length ? (
          <div className="tag-row" aria-label="Event formats">
            {event.formats.slice(0, 2).map((format) => (
              <span className="tag" key={format.code}>
                {format.label}
              </span>
            ))}
          </div>
        ) : null}
      </Link>
    </article>
  );
}
