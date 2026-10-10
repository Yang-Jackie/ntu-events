import { describe, expect, it } from "vitest";

import type { EventListItem } from "./api";
import { occurrenceLocation } from "./event-formatting";
import {
  buildFacets,
  buildMapMarkers,
  eventQuery,
  pathWith,
} from "./discovery";

function event(
  id: number,
  title: string,
  buildingId: number,
  overrides: Partial<EventListItem> = {},
): EventListItem {
  return {
    id,
    slug: `event-${id}`,
    title,
    updated_at: "2026-09-06T00:00:00+08:00",
    formats: [{ code: "WORKSHOP", label: "Workshop" }],
    topics: [{ code: "TECHNOLOGY", label: "Technology" }],
    purposes: [],
    audiences: [],
    organizers: [],
    occurrences: [
      {
        id,
        sequence: 1,
        start_date: "2026-09-10",
        time_precision: "EXACT",
        attendance_mode: "IN_PERSON",
        venues: [
          {
            id,
            name: "Lecture Theatre 1",
            floor: "",
            room_code: "LT1",
            venue_type: "LECTURE_THEATRE",
            building: {
              id: buildingId,
              code: "NS",
              name: "North Spine",
              campus_area: "North",
            },
            map_point: { latitude: 1.3483, longitude: 103.6831 },
          },
        ],
      },
    ],
    ...overrides,
  };
}

describe("eventQuery", () => {
  it("applies discovery defaults and supported filters", () => {
    const query = eventQuery({
      q: "  robotics  ",
      attendance_mode: "HYBRID",
      building: "12",
      ordering: "-start_date",
    });

    expect(query).toMatchObject({
      q: "robotics",
      attendance_mode: "HYBRID",
      building: 12,
      ordering: "-start_date",
    });
    expect(query.date_from).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  it("omits the default date floor when past events are included", () => {
    expect(eventQuery({ include_past: "1" }).date_from).toBeUndefined();
  });

  it("drops malformed map bounds before calling the API", () => {
    expect(eventQuery({ bbox: "not,a,bounding,box" }).bbox).toBeUndefined();
  });

  it("does not send an end date before the effective start date", () => {
    const query = eventQuery({
      date_from: "2026-10-01",
      date_to: "2026-09-01",
    });

    expect(query.date_from).toBe("2026-10-01");
    expect(query.date_to).toBeUndefined();
  });
});

describe("discovery projections", () => {
  it("deduplicates filter options and groups events at one building marker", () => {
    const events = [event(1, "First event", 7), event(2, "Second event", 7)];

    expect(buildFacets(events).formats).toEqual([
      { value: "WORKSHOP", label: "Workshop" },
    ]);
    expect(buildMapMarkers(events)).toEqual([
      expect.objectContaining({
        key: "point-103.6831,1.3483",
        label: "North Spine",
        events: [
          { id: 1, title: "First event" },
          { id: 2, title: "Second event" },
        ],
      }),
    ]);
  });

  it("shows every event when different buildings share a reviewed point", () => {
    const first = event(1, "North Spine event", 7);
    const second = event(2, "Block event", 8);
    second.occurrences[0]!.venues[0]!.building!.name = "Block NS1";
    const markers = buildMapMarkers([first, second, first]);
    expect(markers).toHaveLength(1);
    expect(markers[0]).toMatchObject({
      label: "Block NS1 / North Spine",
      events: [
        { id: 1, title: "North Spine event" },
        { id: 2, title: "Block event" },
      ],
    });
  });

  it("keeps distinct points in one building separate", () => {
    const first = event(1, "First place", 7);
    const second = event(2, "Second place", 7);
    second.occurrences[0]!.venues[0]!.map_point!.latitude = 1.35;
    expect(buildMapMarkers([first, second])).toHaveLength(2);
  });

  it("keeps the reading-room detail when only its building is mapped", () => {
    const occurrence = event(1, "Reading room event", 7).occurrences[0]!;
    occurrence.venues[0]!.name = "Hall 11";
    occurrence.venues[0]!.building!.name = "Hall 11";
    occurrence.raw_location_text = "Hall 11 Reading Room";
    expect(occurrenceLocation(occurrence)).toBe("Hall 11 Reading Room");
  });

  it("updates and removes URL-backed discovery state", () => {
    const params = { q: "music", bbox: "1,2,3,4" };

    expect(pathWith(params, { bbox: undefined, view: "map" })).toBe(
      "/?q=music&view=map",
    );
  });
});
