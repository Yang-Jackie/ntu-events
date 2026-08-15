# NTU Events Implementation Plan

**Document status:** Active implementation plan
**Current milestone:** 4 — Processing workflow
**Next delivery goal:** Turn a reviewed Telegram candidate into a canonical
event safely and repeatably

## 1. Delivery target

The first complete personal-use slice will retrieve one approved source,
preserve its provenance, produce a reviewable candidate, resolve its location,
create canonical event data, expose it through the generated API client, and
show it in a local map/list interface.

Reruns must not create accidental duplicates or silently undo manual decisions.
Public deployment remains a separate later gate.

## 2. Milestones

| Milestone                       | Outcome                                                                                          | Status      |
| ------------------------------- | ------------------------------------------------------------------------------------------------ | ----------- |
| 0. Foundation research          | Product scope, initial source research, and domain questions are understood well enough to begin | Complete    |
| 1. Repository scaffold          | Backend, web, API-client package, local database, and basic checks run                           | Complete    |
| 2. Domain foundation            | Core source, ingestion, event, organizer, classification, and venue records are reviewable       | Complete    |
| 3. First-source ingestion       | Telegram content can be processed repeatedly with retained provenance and inspectable results    | Complete    |
| 4. Processing workflow          | A reviewed candidate can become canonical event data safely and without accidental duplication   | In progress |
| 5. API contract                 | The web application can retrieve typed event data through the generated client                   | Not started |
| 6. Personal discovery interface | The owner can find the ingested event through a local map, list, and detail view                 | Not started |
| 7. Personal-use hardening       | Corrections, reruns, failures, and source changes are handled reliably                           | Not started |
| 8. Controlled source expansion  | Additional approved sources reuse the shared workflow                                            | Not started |
| 9. Public-readiness gate        | The owner approves evidence, quality, security, privacy, accessibility, and rollout readiness    | Not started |
| 10. Public deployment           | The approved audience can reliably access the product                                            | Not started |

## 3. Completed foundation

### Product and source research

- Defined the owner-first, map-based discovery product and its public-release
  gate.
- Studied the NTU CCDS events site as a representative structured official
  source.
- Studied public Telegram club channels as representative unstructured sources.
- Selected public Telegram broadcast channels as the first production ingestion
  source.
- Recorded the important event, time, location, provenance, and review questions
  exposed by those sources.

CCDS remains source research and a candidate for later official-site ingestion;
it is not the implemented first production pipeline.

### Repository scaffold

- Created the Django backend, Next.js web application, and generated API-client
  workspace.
- Added PostgreSQL/PostGIS and the backend runtime through Docker Compose.
- Added repository-wide format, lint, type, migration, contract, test, and build
  commands.
- Documented reproducible local setup in the root README.

### Domain foundation

- Added the initial source, ingestion, event, occurrence, registration,
  organizer, classification, building, venue, alias, and provenance models.
- Added migrations, database constraints, reviewed building-level seed data,
  and Django Admin registration.
- Kept seeded coordinates empty where no approved authoritative import was
  available.

### First production ingestion

- Added durable requests and single-source jobs with a database-backed worker.
- Added a pipeline boundary so future source workflows can reuse job execution
  without sharing source-specific behavior.
- Added Telegram authentication, channel registration, incremental retrieval,
  screening, candidate extraction, selective raw retention, and provenance.
- Added Admin and command entry points that invoke the same workflow.
- Added regression coverage for job execution, batching, raw retention, and
  unchanged reruns.
- Verified an authenticated production-path run and inspected its persisted
  results.

## 4. Milestone 4 — Processing workflow

The current implementation has enough candidate and domain structure to expose
the remaining decisions. Milestone 4 should make those decisions while building
the working path rather than fixing them in planning prose.

### Candidate and validation work

- Review the current candidate contract against real Telegram cases and the
  canonical domain.
- Decide how incomplete, ambiguous, ineligible, and ready candidates are
  represented.
- Ensure occurrences, registrations, classifications, modality, and source
  evidence can be carried into later processing without losing meaning.
- Define deterministic validation outcomes and add focused regression cases.

### Venue and canonical-event work

- Implement a first useful venue-resolution path against the reviewed campus
  data.
- Decide how unresolved and suggested locations enter review.
- Decide and implement the initial canonicalization behavior, including
  provenance, safe reruns, transaction boundaries, and protection of manual
  decisions.
- Make processing results and review actions inspectable in Django Admin.

### Milestone 4 exit condition

Milestone 4 is complete when:

- A representative reviewed candidate can become canonical event and occurrence
  data.
- Reprocessing the same input does not create an accidental duplicate.
- Incomplete or unsafe candidates remain reviewable rather than being
  fabricated or silently accepted.
- The chosen venue and canonicalization behavior is covered by focused tests.
- The technical documentation records the durable behavior actually
  implemented, without prescribing unimplemented future update or matching
  rules.

Cross-source duplicate matching, general canonical updates, and automatic
publication remain later work unless Milestone 4 evidence makes a minimal part
of them necessary.

## 5. Later milestone prompts

### API contract

Decide resource shapes, visibility, filtering, ordering, pagination, identifiers,
and map-query semantics while implementing the first event endpoints. Regenerate
and verify OpenAPI and the TypeScript client with every contract change.

### Personal discovery interface

Choose the map provider and rendering approach while building the smallest
useful map/list/detail flow. Preserve shareable filter state and accessibility.

### Personal-use hardening

Use repeated owner operation to decide source cadence, edit handling, recovery,
manual override behavior, and operational tooling.

### Source expansion

Add sources only when they improve coverage and the existing workflow can
support their access, provenance, and interpretation needs without duplicating
business rules.

### Public readiness and deployment

Define measurable readiness thresholds and the rollout plan before choosing
production hosting and operations.

## 6. Progress rules

- Keep one milestone active at a time.
- Complete the current vertical path before broadening coverage or polishing
  later interfaces.
- Make detailed decisions in the milestone that supplies real evidence for
  them.
- Add migrations, tests, and representative fixtures with the behavior they
  support.
- Update this plan when milestone scope or status changes.
- Update durable technical or architecture documentation only after decisions
  are implemented and verified.

## 7. Task completion standard

An implementation task is complete when its behavior is reproducible, relevant
checks pass, schema changes have migrations, and material decisions or
limitations are documented in the appropriate authoritative file.
