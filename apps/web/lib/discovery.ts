import type { EventListItem, EventListQuery } from "./api";
import { singaporeToday } from "./event-formatting";

export type SearchParamRecord = Record<string, string | string[] | undefined>;

export type SelectOption = {
  value: string;
  label: string;
};

export type DiscoveryFacets = {
  formats: SelectOption[];
  topics: SelectOption[];
  purposes: SelectOption[];
  audiences: SelectOption[];
  buildings: SelectOption[];
};

export type MapMarker = {
  key: string;
  label: string;
  latitude: number;
  longitude: number;
  events: Array<{ id: number; title: string }>;
};

const attendanceModes = new Set(["IN_PERSON", "ONLINE", "HYBRID", "UNKNOWN"]);

export function first(
  value: string | string[] | undefined,
): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

export function eventQuery(params: SearchParamRecord): EventListQuery {
  const query: EventListQuery = {
    ordering:
      first(params.ordering) === "-start_date" ? "-start_date" : "start_date",
  };
  const search = first(params.q)?.trim();
  if (search) query.q = search.slice(0, 200);

  const includePast = first(params.include_past) === "1";
  const dateFrom = first(params.date_from);
  const dateTo = first(params.date_to);
  if (!includePast)
    query.date_from = validDate(dateFrom) ? dateFrom : singaporeToday();
  if (validDate(dateTo) && (!query.date_from || query.date_from <= dateTo)) {
    query.date_to = dateTo;
  }

  const attendanceMode = first(params.attendance_mode);
  if (attendanceMode && attendanceModes.has(attendanceMode)) {
    query.attendance_mode = attendanceMode as EventListQuery["attendance_mode"];
  }
  for (const key of ["format", "topic", "purpose", "audience"] as const) {
    const value = first(params[key])?.trim();
    if (value) query[key] = value.slice(0, 80);
  }

  const building = Number(first(params.building));
  if (Number.isInteger(building) && building > 0) query.building = building;
  const bbox = first(params.bbox);
  if (validBbox(bbox)) query.bbox = bbox;
  const page = Number(first(params.page));
  if (Number.isInteger(page) && page > 1) query.page = page;
  return query;
}

export function discoveryPath(params: SearchParamRecord): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    const item = first(value);
    if (item) search.set(key, item);
  }
  return search.size ? `/?${search}` : "/";
}

export function pathWith(
  params: SearchParamRecord,
  changes: Record<string, string | undefined>,
): string {
  const search = new URLSearchParams(discoveryPath(params).split("?")[1] ?? "");
  for (const [key, value] of Object.entries(changes)) {
    if (value) search.set(key, value);
    else search.delete(key);
  }
  return search.size ? `/?${search}` : "/";
}

export function buildFacets(events: EventListItem[]): DiscoveryFacets {
  const classifications = (
    key: "formats" | "topics" | "purposes" | "audiences",
  ) => {
    const values = new Map<string, string>();
    for (const event of events) {
      for (const item of event[key]) values.set(item.code, item.label);
    }
    return [...values]
      .map(([value, label]) => ({ value, label }))
      .sort(byLabel);
  };
  const buildings = new Map<string, string>();
  for (const event of events) {
    for (const occurrence of event.occurrences) {
      for (const venue of occurrence.venues) {
        if (venue.building)
          buildings.set(String(venue.building.id), venue.building.name);
      }
    }
  }
  return {
    formats: classifications("formats"),
    topics: classifications("topics"),
    purposes: classifications("purposes"),
    audiences: classifications("audiences"),
    buildings: [...buildings]
      .map(([value, label]) => ({ value, label }))
      .sort(byLabel),
  };
}

export function buildMapMarkers(events: EventListItem[]): MapMarker[] {
  const markers = new Map<string, MapMarker>();
  for (const event of events) {
    for (const occurrence of event.occurrences) {
      for (const venue of occurrence.venues) {
        if (!venue.map_point) continue;
        const key = venue.building
          ? `building-${venue.building.id}`
          : `venue-${venue.id}`;
        const marker = markers.get(key) ?? {
          key,
          label: venue.building?.name ?? venue.name,
          latitude: venue.map_point.latitude,
          longitude: venue.map_point.longitude,
          events: [],
        };
        if (!marker.events.some((item) => item.id === event.id)) {
          marker.events.push({ id: event.id, title: event.title });
        }
        markers.set(key, marker);
      }
    }
  }
  return [...markers.values()];
}

function validDate(value: string | undefined): value is string {
  return Boolean(value && /^\d{4}-\d{2}-\d{2}$/.test(value));
}

function validBbox(value: string | undefined): value is string {
  if (!value) return false;
  const values = value.split(",").map(Number);
  if (values.length !== 4 || values.some((item) => !Number.isFinite(item)))
    return false;
  const [west, south, east, north] = values;
  return Boolean(
    west !== undefined &&
    south !== undefined &&
    east !== undefined &&
    north !== undefined &&
    west >= -180 &&
    east <= 180 &&
    south >= -90 &&
    north <= 90 &&
    west < east &&
    south < north,
  );
}

function byLabel(left: SelectOption, right: SelectOption): number {
  return left.label.localeCompare(right.label);
}
