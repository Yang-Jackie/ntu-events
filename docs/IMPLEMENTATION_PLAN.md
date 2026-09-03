# NTU Events Implementation Plan

**Document status:** Active implementation plan
**Current milestone:** 4A — Deduplication hardening
**Next delivery goal:** Decide and implement workable, strong duplicate
detection and resolution before exposing canonical events through the API

## 1. Delivery target

The first complete personal-use slice will retrieve one approved source,
preserve its provenance, produce a reviewable candidate, resolve its location,
create canonical event data, expose it through the generated API client, and
show it in a local map/list interface.

Reruns must not create accidental duplicates or apply changes against a stale
Event graph. Manual corrections to source-derived fields may be replaced by a
later automatic update that considers the current graph and new evidence.
Public deployment remains a separate later gate.

## 2. Milestones

| Milestone                       | Outcome                                                                                          | Status      |
| ------------------------------- | ------------------------------------------------------------------------------------------------ | ----------- |
| 0. Foundation research          | Product scope, initial source research, and domain questions are understood well enough to begin | Complete    |
| 1. Repository scaffold          | Backend, web, API-client package, local database, and basic checks run                           | Complete    |
| 2. Domain foundation            | Core source, ingestion, event, organizer, classification, and venue records are reviewable       | Complete    |
| 3. First-source ingestion       | Telegram content can be processed repeatedly with retained provenance and inspectable results    | Complete    |
| 4. Processing workflow          | A reviewed candidate can become canonical event data through a safe, repeatable workflow         | Complete    |
| 4A. Deduplication hardening     | Likely duplicates and revisions are identified and resolved using reviewable evidence            | In progress |
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
- Preserved Telegram entity and button URLs as raw evidence and supplied their
  labels and targets to screening and extraction without following them.
- Added Admin and command entry points that invoke the same workflow.
- Added regression coverage for job execution, batching, raw retention, and
  unchanged reruns.
- Verified an authenticated production-path run and inspected its persisted
  results.

## 4. Completed processing workflow

### Candidate and validation work

- Candidate v3 preserves incomplete source facts, stable occurrence references,
  attendance mode, meeting access, scoped registrations, controlled-value
  suggestions, unmatched values, ambiguity, and evidence.
- Structurally invalid provider output creates no candidate while retaining
  available diagnostic evidence.
- Business-rule problems are stored as structured issues and make the candidate
  BLOCKED instead of discarding it.
- Supported venue and classification references are supplied to extraction and
  snapshotted with the invocation.
- Every candidate stores its immutable extracted payload and an initially copied
  effective payload; only BLOCKED candidates may be repaired.

### Candidate and canonical-event work

- Newly extracted and manually repaired READY candidates use the same
  source-neutral canonicalization worker regardless of their source pipeline.
- Useful sparse candidates can create draft event shells, while contradictions
  block synchronization and preserve the last good event state.
- Supported venue references and canonical classification values are projected;
  unmatched data remains visible as candidate issues.
- Direct online meeting access is kept separate from registration and general
  webpages, and useful sparse registration details survive projection with
  their problems retained as candidate issues.
- Possible matches become explicit evidence for a canonicalization decision
  rather than being silently merged or independently created.
- Candidate repairs, plan decisions, processing state, and linked canonical data
  are inspectable in Django Admin.
- Focused tests cover projection, correction, plan rejection, duplicate gating,
  incomplete data, failures, reruns, and provenance.

Explicit matching, planning, observation, and revision records now own the
candidate-to-Event path. Automatic publication remains later work.

## 5. Current deduplication-hardening milestone

The implemented foundation now:

- Classifies each extracted observation as an announcement, follow-up, or
  unknown without using that label as policy yet.
- Normalizes an exact `+08:00` model-output offset to an offset-free Singapore
  wall-clock value and rejects other offsets so times cannot be converted
  independently from their dates. The changed extraction and canonicalization
  contracts have distinct schema versions, keeping cache reuse and model
  provenance aligned with their implemented behavior.
- Consolidates the old CandidateReview into EventCandidate: immutable extracted
  payload, editable effective payload, and BLOCKED/READY/PROCESSED lifecycle.
  Missing or title-only candidates, broken ownership references, duplicate
  occurrence references, and impossible ordering block the whole candidate;
  other incomplete optional facts remain review issues and are safely omitted
  from automatic ADD projection when canonical storage cannot represent them.
  Only BLOCKED candidates can be repaired; a valid repair becomes READY and is
  eligible for the same downstream worker as a newly extracted READY candidate.
- Splits source ingestion from canonicalization at the durable EventCandidate
  boundary. Ingestion jobs finish after candidate persistence; a separate
  serial worker consumes unplanned READY candidates. A PostgreSQL advisory lock
  enforces one canonicalization worker globally, and unexpected exceptions leave
  the candidate READY while stopping the worker visibly.
- Uses a PostgreSQL trigram title index plus exact and bounded structured
  lookups to retrieve a small canonical-Event pool without scanning every Event
  graph.
- Uses a fixed additive score led by 65% title weight, plus normalized
  registration URL, date, organizer, venue, and source evidence. Missing or
  mismatching fields contribute zero, dates at least 120 days apart subtract 20
  points, the threshold is 30%, no identity gate applies, and at most five
  CandidateMatch records explain the complete calculation.
- Automatically creates and applies ADD when no match exists, while matched
  candidates use a structured-output model to choose one ADD, UPDATE, or LINK_ONLY
  action.
- Represents UPDATE as explicit sparse operations with child identity, ADD,
  UPDATE, REMOVE, SET, and CLEAR semantics, plus explicit classification
  ADD_CODES, REMOVE_CODES, and REPLACE_CODES operations.
- Rejects unsupported classification codes, nonexistent catalog references,
  invalid targets, wrong child ownership, and persistence-invalid graphs before
  any write; domain and grounding concerns remain flags.
- Applies plans transactionally and idempotently with graph-level staleness
  checks, source links, immutable observations, and EventRevision snapshots.
- Builds reconciliation decisions from the latest committed Event graph.
  Source-derived manual edits are not durable overrides and may be replaced by
  later automatic UPDATE plans; publication and verification controls remain
  owner-owned and outside those proposals.
- Exposes BLOCKED candidate repairs and unapplied plans in Django Admin while
  keeping extracted payloads, PROCESSED candidates, generated proposals, and
  applied plans immutable.
- Separates source-specific retrieval, document handling, screening, and
  extraction under each pipeline from the source-neutral candidate and
  canonicalization workflows. Canonicalization is organized into matching,
  context, decision-provider, proposal, application, and workflow modules.

The remaining milestone work is:

- Continue evaluating the implemented matching weights and thresholds against
  representative duplicate, follow-up, separate-edition, and false-match
  fixtures; the GitHub workshop reminder is now a focused regression case.
- Exercise failed model calls, rejected-plan repair, stale-plan regeneration,
  and ingestion retry behavior in repeated owner operation.

Complete Milestone 4A only when those remaining behaviors are repeatable,
explainable, avoid stale writes, and have focused coverage for reruns and the
agreed difficult cases.

## 6. Later milestone prompts

### API contract

Decide resource shapes, visibility, filtering, ordering, pagination, identifiers,
and map-query semantics while implementing the first event endpoints. Regenerate
and verify OpenAPI and the TypeScript client with every contract change.

### Personal discovery interface

Choose the map provider and rendering approach while building the smallest
useful map/list/detail flow. Preserve shareable filter state and accessibility.

### Personal-use hardening

Use repeated owner operation to decide source cadence, edit handling, recovery,
and operational tooling.

### Source expansion

Add sources only when they improve coverage and the existing workflow can
support their access, provenance, and interpretation needs without duplicating
business rules.

### Public readiness and deployment

Define measurable readiness thresholds and the rollout plan before choosing
production hosting and operations.

## 7. Progress rules

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

## 8. Task completion standard

An implementation task is complete when its behavior is reproducible, relevant
checks pass, schema changes have migrations, and material decisions or
limitations are documented in the appropriate authoritative file.
