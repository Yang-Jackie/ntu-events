# NTU CCDS Events Source Evaluation

## Selection

- **Source name:** NTU College of Computing and Data Science events
- **Listing URL:** `https://www.ntu.edu.sg/computing/news-events/events`
- **Owner:** Nanyang Technological University, College of Computing and Data Science
- **Access scope:** Public, unauthenticated pages on `www.ntu.edu.sg`
- **Selected role:** First source for the personal-use vertical slice
- **Initial observation date:** 2026-07-22 (Asia/Singapore)

This source is selected because it is an official NTU source with a substantial archive, physical campus venues, several event types, event detail pages, and enough imperfect cases to exercise identity, time, location, eligibility, and deduplication rules.

## Observed Source Shape

The listing returned one server-rendered HTML response of approximately 2.95 MB. The observed response contained 213 event cards across these source categories:

- Conferences & Seminars: 192
- Workshops & Classes: 15
- Competitions: 4
- Networking: 1
- Student Activities: 1

Each observed card contained:

- A stable-looking detail-page URL
- Source category
- Title
- Human-readable date and time labels
- Machine-readable `data-start`, `data-end`, and `data-all-day` values
- Raw location when supplied
- A description embedded in the calendar control
- An image URL when supplied

Observed detail pages also expose Schema.org `Event` JSON-LD with fields including name, start and end timestamps, location, image, description, and organizer. This makes deterministic structured extraction the preferred initial approach.

## Retrieval and Interpretation Decision

Use a direct, allowlisted HTTP adapter first:

1. Fetch and preserve the listing response.
2. Discover event detail URLs and listing-card observations.
3. Fetch and preserve each selected detail response.
4. Parse JSON-LD and stable calendar attributes deterministically.
5. Reconcile listing and detail observations without silently choosing between conflicts.
6. Use LLM interpretation only for unstructured description content or fields that remain ambiguous after structured extraction.
7. Validate candidates and apply eligibility, venue resolution, deduplication, review, and publication rules in the shared ingestion workflow.

Do not introduce Apify or another managed retrieval provider for this source unless direct retrieval proves unreliable or operational evidence justifies the additional dependency. The adapter boundary must allow that substitution later.

## Provenance to Preserve

For every fetch, retain:

- Source identifier and requested URL
- Final URL after redirects
- Retrieval timestamp
- HTTP status and relevant response headers
- Response content type and raw bytes
- Content hash
- Retrieval implementation and version
- Parent listing URL for discovered detail pages
- Parser version and structured observations
- Failures and retry history

All saved structured fixtures for this source must be JSON files. Do not create JSONL fixtures.

## Representative Cases Already Observed

- Timed physical event with a precise room and building code
- Timed event with no location
- Multi-day all-day event whose machine-readable end is exclusive
- Single-day all-day event whose machine-readable end is the following day
- Long-running timed range spanning several weeks
- Online-only Zoom events, which are ineligible for the current product
- An event at Singapore's National Library, outside the current NTU-campus scope
- Two same-time, same-venue records with near-identical titles, requiring duplicate review
- Location aliases and punctuation variants, including ordinary and non-breaking hyphens
- Detail URLs containing punctuation and parentheses
- Multiple source categories that do not directly equal the product taxonomy

The initial observation fixture is `fixtures/sources/ntu_ccds_events/representative_observations.json`. Grow the reviewed sample set toward 50–100 items before finalizing the schema; preserve each future batch as a JSON array or JSON object, never JSONL.

## Domain Questions This Source Must Resolve

- Whether the detail URL is sufficiently stable to serve as source-record identity
- How listing updates and detail-page changes are detected and versioned
- Whether all-day end dates follow the exclusive-end convention consistently
- How long-running ranges differ from multi-session or recurring events
- How source categories map to separate product facets
- How online-only and off-campus items are withheld without losing their source records
- How missing locations enter review and later reprocessing
- Which fields win when listing attributes and detail JSON-LD conflict
- What evidence threshold permits automatic duplicate merging versus review

## Safe Retrieval Boundary

- Allow unauthenticated `GET` requests only to approved `www.ntu.edu.sg` event listing and detail paths during the first slice.
- Apply bounded concurrency, timeouts, retries, and a descriptive user agent.
- Do not authenticate, submit forms, bypass access controls or CAPTCHAs, or follow registration links as part of ingestion.
- Treat HTML, JSON-LD, calendar attributes, URLs, and descriptions as untrusted input.
- Reconfirm applicable access rules before enabling scheduled retrieval or public operation.

