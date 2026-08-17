# NTU Events Implementation Plan

**Document status:** Active implementation plan
**Current milestone:** 5 — API contract
**Next delivery goal:** Expose the first useful canonical event resource through
OpenAPI and the generated TypeScript client

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
| 4. Processing workflow          | A reviewed candidate can become canonical event data safely and without accidental duplication   | Complete    |
| 5. API contract                 | The web application can retrieve typed event data through the generated client                   | In progress |
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

## 4. Completed processing workflow

### Candidate and validation work

- Candidate v2 preserves incomplete source facts, stable occurrence references,
  attendance mode, meeting access, scoped registrations, controlled-value
  suggestions, unmatched values, ambiguity, and evidence.
- Structurally invalid provider output creates no candidate while retaining
  available diagnostic evidence.
- Business-rule problems are stored as structured issues and route the
  candidate to review instead of discarding it.
- Supported venue and classification references are supplied to extraction and
  snapshotted with the invocation.
- Every candidate receives a mutable review record while the extracted candidate
  remains immutable.

### Review and canonical-event work

- Automatic and manual promotion share a versioned, repeatable review-to-event
  synchronization workflow.
- Useful sparse candidates can create draft event shells, while contradictions
  block synchronization and preserve the last good event state.
- Supported venue references and canonical classification values are projected;
  unmatched data remains visible as review issues.
- Exact-title duplicates pause for an explicit reviewer decision rather than
  being merged or created automatically.
- Reviewer corrections, approval, rejection, synchronization state, and linked
  canonical data are inspectable in Django Admin.
- Focused tests cover projection, correction, rejection, duplicate gating,
  incomplete data, failures, reruns, and provenance.

Cross-source duplicate matching, general canonical updates, and automatic
publication remain later work.

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
