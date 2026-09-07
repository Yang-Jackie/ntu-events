import {
  createApiClient,
  type components,
  type operations,
} from "@ntu-events/api-client";

export type EventDetail = components["schemas"]["EventDetail"];
export type EventListItem = components["schemas"]["EventList"];
export type EventListQuery = NonNullable<
  operations["v1_events_list"]["parameters"]["query"]
>;
export type PaginatedEventList =
  components["schemas"]["PaginatedEventListList"];

const apiBaseUrl =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ??
  "http://127.0.0.1:8000";

export class ApiRequestError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

function backendClient() {
  return createApiClient({ baseUrl: apiBaseUrl });
}

export async function listEvents(
  query: EventListQuery,
): Promise<PaginatedEventList> {
  const { data, response } = await backendClient().GET("/api/v1/events/", {
    params: { query },
    cache: "no-store",
  });
  if (!response.ok || !data) {
    throw new ApiRequestError(
      "The event list could not be loaded.",
      response.status,
    );
  }
  return data;
}

export async function getEvent(id: number): Promise<EventDetail> {
  const { data, response } = await backendClient().GET("/api/v1/events/{id}/", {
    params: { path: { id } },
    cache: "no-store",
  });
  if (!response.ok || !data) {
    throw new ApiRequestError(
      "The event could not be loaded.",
      response.status,
    );
  }
  return data;
}
