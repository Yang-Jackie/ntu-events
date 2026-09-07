import type { EventListItem } from "./api";

type EventOccurrence = EventListItem["occurrences"][number];

const dateFormatter = new Intl.DateTimeFormat("en-SG", {
  weekday: "short",
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "Asia/Singapore",
});

export function singaporeToday(): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    timeZone: "Asia/Singapore",
  }).formatToParts(new Date());
  const values = Object.fromEntries(
    parts.map((part) => [part.type, part.value]),
  );
  return `${values.year}-${values.month}-${values.day}`;
}

export function formatDate(value: string): string {
  return dateFormatter.format(new Date(`${value}T00:00:00+08:00`));
}

export function formatTime(value?: string | null): string {
  if (!value) return "Time TBA";
  const [hours = "0", minutes = "00"] = value.split(":");
  const date = new Date(`2000-01-01T${hours}:${minutes}:00+08:00`);
  return new Intl.DateTimeFormat("en-SG", {
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
    timeZone: "Asia/Singapore",
  }).format(date);
}

export function formatOccurrenceWhen(occurrence: EventOccurrence): string {
  if (occurrence.is_all_day)
    return `${formatDate(occurrence.start_date)} · All day`;
  return `${formatDate(occurrence.start_date)} · ${formatTime(occurrence.start_time)}`;
}

export function occurrenceLocation(occurrence: EventOccurrence): string {
  const primary =
    occurrence.venues.find((venue) => venue.is_primary) ?? occurrence.venues[0];
  if (primary) {
    const building = primary.building?.name;
    return building && building !== primary.name
      ? `${primary.name}, ${building}`
      : primary.name;
  }
  if (occurrence.attendance_mode === "ONLINE") return "Online";
  return occurrence.raw_location_text || "Location not confirmed";
}

export function attendanceLabel(value?: string): string {
  return (
    {
      IN_PERSON: "In person",
      ONLINE: "Online",
      HYBRID: "Hybrid",
      UNKNOWN: "Attendance TBA",
    }[value ?? "UNKNOWN"] ?? "Attendance TBA"
  );
}

export function verificationLabel(value?: string): string {
  return (
    {
      UNVERIFIED: "Source not yet verified",
      AUTOMATICALLY_VERIFIED: "Automatically verified",
      MANUALLY_VERIFIED: "Manually verified",
      CONFLICTING: "Conflicting source details",
    }[value ?? "UNVERIFIED"] ?? "Source not yet verified"
  );
}
