import Link from "next/link";

import { DiscoveryFilters } from "@/components/discovery-filters";
import { EventCard } from "@/components/event-card";
import { EventMap } from "@/components/event-map";
import { SiteHeader } from "@/components/site-header";
import { listEvents } from "@/lib/api";
import {
  buildFacets,
  buildMapMarkers,
  discoveryPath,
  eventQuery,
  first,
  pathWith,
  type SearchParamRecord,
} from "@/lib/discovery";

export const dynamic = "force-dynamic";

type SearchParams = Promise<SearchParamRecord>;

export default async function Home({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const params = await searchParams;
  const query = eventQuery(params);
  const [result, facetResult] = await Promise.all([
    listEvents(query),
    listEvents({ ordering: "start_date" }),
  ]);
  const facets = buildFacets(facetResult.results);
  const markers = buildMapMarkers(result.results);
  const returnPath = discoveryPath(params);
  const currentPage = query.page ?? 1;
  const mapView = first(params.view) === "map";

  return (
    <main className={`discovery-shell ${mapView ? "view-map" : "view-list"}`}>
      <SiteHeader />
      <section className="discovery-heading">
        <div>
          <p className="eyebrow">Campus field guide</p>
          <h1>Find what’s happening around NTU.</h1>
        </div>
        <p className="result-count">
          <strong>{result.count}</strong> matching{" "}
          {result.count === 1 ? "event" : "events"}
        </p>
      </section>

      <DiscoveryFilters facets={facets} params={params} query={query} />

      <nav className="view-switch" aria-label="Choose discovery view">
        <Link
          aria-current={!mapView ? "page" : undefined}
          href={pathWith(params, { view: undefined })}
        >
          List
        </Link>
        <Link
          aria-current={mapView ? "page" : undefined}
          href={pathWith(params, { view: "map" })}
        >
          Map
        </Link>
      </nav>

      <div className="discovery-grid">
        <section className="event-list-panel" aria-label="Events">
          {result.results.length ? (
            <>
              <div className="event-list">
                {result.results.map((event) => (
                  <EventCard
                    event={event}
                    returnPath={returnPath}
                    key={event.id}
                  />
                ))}
              </div>
              {result.previous || result.next ? (
                <nav className="pagination" aria-label="Event result pages">
                  {result.previous ? (
                    <Link
                      className="button button--secondary"
                      href={pathWith(params, {
                        page:
                          currentPage > 2 ? String(currentPage - 1) : undefined,
                      })}
                    >
                      ← Previous
                    </Link>
                  ) : (
                    <span />
                  )}
                  <span>Page {currentPage}</span>
                  {result.next ? (
                    <Link
                      className="button button--secondary"
                      href={pathWith(params, { page: String(currentPage + 1) })}
                    >
                      Next →
                    </Link>
                  ) : (
                    <span />
                  )}
                </nav>
              ) : null}
            </>
          ) : (
            <div className="empty-state">
              <span className="empty-state__marker" aria-hidden="true">
                <span>0</span>
              </span>
              <div>
                <h2>No published events found</h2>
                <p>
                  Try widening the dates, clearing the map area, or changing the
                  filters. Newly ingested events appear here after publication.
                </p>
              </div>
            </div>
          )}
        </section>
        <aside className="event-map-panel" aria-label="Campus event map">
          <EventMap
            bbox={query.bbox}
            markers={markers}
            returnPath={returnPath}
          />
        </aside>
      </div>
    </main>
  );
}
