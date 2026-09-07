import { describe, expect, it } from "vitest";

import type { EventListItem } from "./api";
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
        key: "building-7",
        label: "North Spine",
        events: [
          { id: 1, title: "First event" },
          { id: 2, title: "Second event" },
        ],
      }),
    ]);
  });

  it("updates and removes URL-backed discovery state", () => {
    const params = { q: "music", bbox: "1,2,3,4" };

    expect(pathWith(params, { bbox: undefined, view: "map" })).toBe(
      "/?q=music&view=map",
    );
  });
});
