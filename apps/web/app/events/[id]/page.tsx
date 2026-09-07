import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { SiteHeader } from "@/components/site-header";
import { ApiRequestError, getEvent } from "@/lib/api";
import {
  attendanceLabel,
  formatDate,
  formatTime,
  occurrenceLocation,
  verificationLabel,
} from "@/lib/event-formatting";

export const dynamic = "force-dynamic";

type PageProps = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ from?: string | string[] }>;
};

function safeReturnPath(value: string | string[] | undefined): string {
  const path = Array.isArray(value) ? value[0] : value;
  return path?.startsWith("/") && !path.startsWith("//") ? path : "/";
}

async function loadEvent(idValue: string) {
  const id = Number(idValue);
  if (!Number.isInteger(id) || id < 1) notFound();
  try {
    return await getEvent(id);
  } catch (error) {
    if (error instanceof ApiRequestError && error.status === 404) notFound();
    throw error;
  }
}

export async function generateMetadata({
  params,
}: PageProps): Promise<Metadata> {
  const event = await loadEvent((await params).id);
  return {
    title: event.title,
    description: event.description || "NTU event details",
  };
}

export default async function EventPage({ params, searchParams }: PageProps) {
  const event = await loadEvent((await params).id);
  const returnPath = safeReturnPath((await searchParams).from);
  const organizer =
    event.organizers.find((item) => item.is_primary) ?? event.organizers[0];
  const registrations = [
    ...event.registrations,
    ...event.occurrences.flatMap((item) => item.registrations),
  ].filter((item) => item.url);

  return (
    <main className="detail-shell">
      <SiteHeader />
      <Link className="back-link" href={returnPath}>
        <span aria-hidden="true">←</span> Back to events
      </Link>

      <article className="detail-layout">
        <header className="detail-hero">
          <p className="eyebrow">{event.formats[0]?.label || "NTU event"}</p>
          <h1>{event.title}</h1>
          <div className="detail-byline">
            {organizer ? <span>By {organizer.name}</span> : null}
            <span>{verificationLabel(event.verification_status)}</span>
          </div>
          {event.description ? (
            <p className="detail-description">{event.description}</p>
          ) : null}
        </header>

        <div className="detail-main">
          <section className="detail-section">
            <div className="section-heading">
              <span>01</span>
              <h2>When and where</h2>
            </div>
            <div className="occurrence-list">
              {event.occurrences.length ? (
                event.occurrences.map((occurrence) => (
                  <article className="occurrence-card" key={occurrence.id}>
                    <div>
                      <p className="occurrence-card__date">
                        {formatDate(occurrence.start_date)}
                      </p>
                      <h3>
                        {occurrence.label || occurrenceLocation(occurrence)}
                      </h3>
                    </div>
                    <dl>
                      <div>
                        <dt>Time</dt>
                        <dd>
                          {occurrence.is_all_day
                            ? "All day"
                            : `${formatTime(occurrence.start_time)}${
                                occurrence.end_time
                                  ? ` – ${formatTime(occurrence.end_time)}`
                                  : ""
                              }`}
                        </dd>
                      </div>
                      <div>
                        <dt>Place</dt>
                        <dd>{occurrenceLocation(occurrence)}</dd>
                      </div>
                      <div>
                        <dt>Attendance</dt>
                        <dd>{attendanceLabel(occurrence.attendance_mode)}</dd>
                      </div>
                    </dl>
                    {occurrence.meeting_url ? (
                      <a
                        className="text-link"
                        href={occurrence.meeting_url}
                        rel="noreferrer"
                      >
                        Open meeting link ↗
                      </a>
                    ) : null}
                  </article>
                ))
              ) : (
                <p className="occurrence-card">
                  Schedule and location have not been confirmed.
                </p>
              )}
            </div>
          </section>

          <aside className="detail-sidebar">
            {registrations.length ? (
              <section className="action-card">
                <p className="eyebrow">Registration</p>
                {registrations.map((registration) => (
                  <a
                    className="button button--primary button--wide"
                    href={registration.url}
                    rel="noreferrer"
                    key={registration.id}
                  >
                    {registration.name || "Register"} ↗
                  </a>
                ))}
                <small>Registration happens on the organizer’s website.</small>
              </section>
            ) : null}

            <section className="detail-facts">
              <h2>Event details</h2>
              {event.audience_notes ? (
                <div>
                  <span>Audience</span>
                  <p>{event.audience_notes}</p>
                </div>
              ) : null}
              {event.topics.length ? (
                <div>
                  <span>Topics</span>
                  <p>{event.topics.map((item) => item.label).join(", ")}</p>
                </div>
              ) : null}
              {event.sources.length ? (
                <div>
                  <span>Sources</span>
                  {event.sources.map((source) =>
                    source.url ? (
                      <a
                        className="text-link"
                        href={source.url}
                        rel="noreferrer"
                        key={source.url}
                      >
                        {source.source_name} ↗
                      </a>
                    ) : (
                      <p key={source.source_name}>{source.source_name}</p>
                    ),
                  )}
                </div>
              ) : null}
            </section>
          </aside>
        </div>
      </article>
    </main>
  );
}
