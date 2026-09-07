import Link from "next/link";

import type { EventListQuery } from "@/lib/api";
import {
  first,
  pathWith,
  type DiscoveryFacets,
  type SearchParamRecord,
  type SelectOption,
} from "@/lib/discovery";

type DiscoveryFiltersProps = {
  facets: DiscoveryFacets;
  params: SearchParamRecord;
  query: EventListQuery;
};

function FilterSelect({
  label,
  name,
  options,
  value,
}: {
  label: string;
  name: string;
  options: SelectOption[];
  value?: string;
}) {
  return (
    <label className="select-field">
      <span>{label}</span>
      <select name={name} defaultValue={value ?? ""}>
        <option value="">Any</option>
        {options.map((option) => (
          <option value={option.value} key={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function DiscoveryFilters({
  facets,
  params,
  query,
}: DiscoveryFiltersProps) {
  const hasMapArea = Boolean(query.bbox);
  return (
    <form className="filter-form" action="/" method="get" role="search">
      {first(params.view) === "map" ? (
        <input type="hidden" name="view" value="map" />
      ) : null}
      <div className="filter-bar">
        <label className="search-field">
          <span className="sr-only">Search events</span>
          <span aria-hidden="true">⌕</span>
          <input
            type="search"
            name="q"
            defaultValue={query.q}
            placeholder="Search events or organizers"
          />
        </label>
        <label className="date-field">
          <span>From</span>
          <input
            type="date"
            name="date_from"
            defaultValue={query.date_from}
            max={query.date_to}
          />
        </label>
        <label className="date-field">
          <span>To</span>
          <input
            type="date"
            name="date_to"
            defaultValue={query.date_to}
            min={query.date_from}
          />
        </label>
        <button className="button button--primary" type="submit">
          Apply
        </button>
        <Link className="button button--quiet" href="/">
          Reset
        </Link>
      </div>

      <details className="filter-drawer">
        <summary>
          More filters
          <span aria-hidden="true">＋</span>
        </summary>
        <div className="filter-grid">
          <FilterSelect
            label="Attendance"
            name="attendance_mode"
            value={query.attendance_mode}
            options={[
              { value: "IN_PERSON", label: "In person" },
              { value: "ONLINE", label: "Online" },
              { value: "HYBRID", label: "Hybrid" },
              { value: "UNKNOWN", label: "Not confirmed" },
            ]}
          />
          <FilterSelect
            label="Format"
            name="format"
            value={query.format}
            options={facets.formats}
          />
          <FilterSelect
            label="Topic"
            name="topic"
            value={query.topic}
            options={facets.topics}
          />
          <FilterSelect
            label="Purpose"
            name="purpose"
            value={query.purpose}
            options={facets.purposes}
          />
          <FilterSelect
            label="Audience"
            name="audience"
            value={query.audience}
            options={facets.audiences}
          />
          <FilterSelect
            label="Building"
            name="building"
            value={query.building ? String(query.building) : undefined}
            options={facets.buildings}
          />
          <label className="select-field">
            <span>Order</span>
            <select name="ordering" defaultValue={query.ordering}>
              <option value="start_date">Soonest first</option>
              <option value="-start_date">Latest first</option>
            </select>
          </label>
          <label className="checkbox-field">
            <input
              type="checkbox"
              name="include_past"
              value="1"
              defaultChecked={first(params.include_past) === "1"}
            />
            <span>Include past events</span>
          </label>
          {hasMapArea ? (
            <input type="hidden" name="bbox" value={query.bbox} />
          ) : null}
          <button className="button button--secondary" type="submit">
            Update results
          </button>
          {hasMapArea ? (
            <Link
              className="button button--quiet"
              href={pathWith(params, { bbox: undefined })}
            >
              Clear map area
            </Link>
          ) : null}
        </div>
      </details>
    </form>
  );
}
