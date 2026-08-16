# NTU CCDS Events Source Research

**Status:** Structured-source research; not the first production pipeline
**Listing:** `https://www.ntu.edu.sg/computing/news-events/events`
**Initial observation:** 2026-07-22, Asia/Singapore

## Purpose

The NTU College of Computing and Data Science events site was studied to expose
structured-source cases before the core domain was scaffolded. Public Telegram
broadcast channels were later selected and implemented as the first production
ingestion source.

CCDS remains a useful candidate for later official-site ingestion because it
provides a large official archive, physical campus venues, event detail pages,
and several imperfect cases that exercise time, location, eligibility, and
duplicate handling.

## Observed source shape

The observed public listing contained event cards with stable-looking detail
URLs, categories, titles, human-readable schedule labels, machine-readable
calendar attributes, locations, descriptions, and images where available.

Observed detail pages also exposed Schema.org `Event` JSON-LD with names,
schedules, locations, images, descriptions, and organizers. This suggests that
a future adapter should investigate structured extraction before adding
model-assisted interpretation.

The reviewed research fixture is
`fixtures/sources/ntu_ccds_events/representative_observations.json`.

## Cases observed

- Timed physical events with precise rooms
- Missing locations
- Single-day and multi-day all-day events
- Long-running date ranges
- Online-only events
- Off-campus events
- Near-duplicate records
- Location punctuation and alias variations
- Detail URLs containing punctuation
- Source categories that do not directly match product discovery facets

These observations informed the initial domain questions. They do not settle
future adapter, validation, or canonicalization behavior.

## Questions for a future adapter

When CCDS ingestion is implemented, decide:

- Which source identifier remains stable enough for repeated retrieval
- How listing and detail observations are reconciled
- How changed content is detected and retained
- How source schedules map into candidate occurrences
- How missing, off-campus, and ambiguous facts enter review
- How occurrence attendance mode and online access map into shared candidates
- How source categories map to product facets
- What source-specific evidence is required for troubleshooting

Make these decisions from a fresh observation of the live source rather than
assuming the 2026 research shape is unchanged.

## Safe access boundary

- Use only approved public NTU pages.
- Prefer ordinary unauthenticated retrieval while it remains reliable.
- Bound concurrency, timeouts, and retries.
- Do not submit forms, bypass access controls, or follow registration flows as
  part of ingestion.
- Treat page content, embedded data, and URLs as untrusted.
- Reconfirm access and usage conditions before scheduled or public operation.
