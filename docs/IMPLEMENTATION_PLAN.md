# NTU Events Implementation Plan

**Document status:** Active implementation plan  
**Current milestone:** 3 — First-source ingestion
**Next delivery goal:** Complete production-path verification and the labelled Telegram evaluation set

## 1. Guiding Delivery Target

The first complete vertical slice will:

> Fetch one approved source, preserve its raw content, extract and review an event, resolve its venue, create one canonical event, expose it through the generated API client, and display it to the project owner in a minimal local map/list.

Re-running must not create duplicates or overwrite manual corrections. This is the first personal-use slice; public deployment follows sustained evidence of utility, coverage, and data quality.

## 2. Overall Milestones

| Milestone | Deliverable | Exit condition | Status |
| --- | --- | --- | --- |
| 0. Foundation decisions | First source, representative samples, initial identity/time/taxonomy/venue rules | Blocking domain assumptions are documented well enough to scaffold | Complete |
| 1. Repository scaffold | Backend, web, API-client package, local database and basic checks | Both applications start and automated checks run | Complete |
| 2. Domain foundation | Sources, raw documents, candidates, events, occurrences, venues and taxonomy | Initial migrations work and records are reviewable in Django Admin | Complete |
| 3. First-source ingestion | One source-appropriate workflow using structured mapping or LLM-first unstructured extraction, constrained browser exploration where needed, raw storage, provenance, fixtures and a candidate contract | The source can be retrieved and processed repeatedly, and its raw material plus applicable provider metadata or action traces are retained | In progress |
| 4. Processing workflow | Extraction, validation, venue resolution, canonicalization and review | A valid candidate becomes one canonical event without duplication | Not started |
| 5. API contract | Event endpoints, core filters, OpenAPI schema and generated client | The web application retrieves typed event data through `packages/api-client` | Not started |
| 6. Personal discovery interface | Basic event list, map synchronization and event detail | The owner can discover the ingested event through the complete local product path | Not started |
| 7. Personal-use hardening | Reprocessing, manual overrides, failure handling and regression cases | Corrections survive reprocessing and failed inputs do not corrupt data during repeated owner use | Not started |
| 8. Controlled source expansion | Additional approved sources, including harder poster or social content | Coverage is useful to the owner and new adapters reuse the existing workflow without separate business rules | Not started |
| 9. Public-readiness gate | Evidence from personal use plus security, privacy, accessibility and operational review | The owner approves explicit quality thresholds, rollout scope and deployment readiness | Not started |
| 10. Public deployment | Production configuration, hosting, monitoring and staged release | The approved public audience can reliably access the product | Not started |

## 3. Immediate Next Goals

### Goal A — Select and understand the first source

- [x] Select one accessible, approved NTU event source: the public NTU CCDS events listing.
- [x] Record why it is representative and how it may be accessed in `docs/sources/ntu_ccds_events.md`.
- [x] Preserve a reviewed JSON observation fixture covering representative
  official-source cases; assign larger regression-fixture expansion to
  Milestone 3.
- [x] Include missing-location, duplicate, all-day, multi-day, long-range,
  online-only, and off-campus cases.
- [x] Identify embedded JSON-LD and calendar metadata behind direct public HTTP
  retrieval as the preferred source path.
- [x] Define deterministic structured mapping first and LLM interpretation only
  for remaining unstructured ambiguity.
- [x] Define the approved domain, unauthenticated read-only actions, credentials
  boundary, and conditions for introducing managed or browser retrieval.

**Done when:** The source can drive concrete schema and extraction decisions without relying on imagined examples.

### Goal A2 — Compare an unstructured source

- [x] Select public Telegram club channels as a second source category.
- [x] Implement an owner-operated Telethon text research harness with a saved,
  ignored authorization session and multi-channel selection.
- [x] Preserve raw messages, model results, provisional candidates, failures,
  provenance and versions as standard JSON files.
- [x] Run it against several representative production-intent club channels.
- [x] Assign promotion of additional reviewed Telegram inputs and expected
  outputs to Milestone 3, when the candidate contract is implemented.
- [x] Compare Telegram findings with NTU CCDS observations before finalizing
  event, source-representation and occurrence boundaries.

This is Milestone 0 schema research. It does not establish the future Django
package layout, canonicalize events, publish data, or make Telegram the sole
production source.

**Done when:** Real posts expose enough event, non-event, multi-event,
relative-time and missing-field cases to refine the source-neutral core model.

### Goal B — Record initial domain rules

- [x] Define event, series, occurrence and source-representation identity; keep
  representation revisions conceptually separate while deferring content-change handling.
- [x] Define the initial treatment of exact, date-only, all-day, multi-day,
  crossing-midnight and multi-session times under a continuity-based occurrence rule.
- [x] Decide which fields belong to events and which belong to occurrences.
- [x] Confirm plural relationships for organizers, classification facets,
  venues, sources and registration options where needed.
- [x] Define series/event/occurrence registration ownership and closest-scope inheritance.
- [x] Define create-only, non-public canonicalization with candidate-level idempotency.
- [x] Record duplicate matching, source conflicts, corrections, cancellations,
  postponements and canonical updates as deferred.
- [x] Define initial format, topic, purpose, audience and organizer-type
  dimensions and their plural filter meaning.
- [x] Define the initial building/venue scope, authoritative source hierarchy,
  alias rules and incremental room-seeding policy.
- [x] Record unresolved choices explicitly rather than hiding them in model
  assumptions.

**Done when:** The first migrations can be designed without known contradictions in identity, time, cardinality or taxonomy.

### Goal C — Prepare repository scaffolding decisions

- [x] Select Python 3.13, Django 5.2 LTS, Node.js 24 LTS and Next.js 16.
- [x] Select `uv` with `uv.lock` and `pnpm` 11 with a root workspace and
  `pnpm-lock.yaml`.
- [x] Select PostgreSQL 18 with PostGIS 3.6 and GeoDjango in Docker Compose with
  a named database volume, while Next.js runs on the host.
- [x] Select `drf-spectacular`, a committed OpenAPI schema,
  `openapi-typescript`, and an `openapi-fetch` client factory with generated
  contract drift checks.
- [x] Select Ruff, pytest/pytest-django, Django system and migration checks,
  Prettier, ESLint, `tsc --noEmit`, and Vitest behind consistent root scripts.
- [x] Use ignored `.env`, complete `.env.example`, and immutable ignored
  `var/raw/` content behind a storage interface with metadata in PostgreSQL.
- [x] Define separate source-adapter, direct-retrieval, managed-job,
  constrained-browser, and event-extractor ports while leaving provider SDKs
  behind infrastructure adapters.

**Done when:** Milestone 1 can be implemented without changing the agreed repository boundaries.

## 4. Milestone 1 Result

- [x] Created the `apps/backend`, `apps/web`, and `packages/api-client` workspaces.
- [x] Added PostgreSQL 18/PostGIS 3.6 through Docker Compose and documented local environment variables.
- [x] Added minimal Django and Next.js applications with verified health endpoints.
- [x] Added root formatting, linting, type-checking, migration, contract-drift, test, and build commands.
- [x] Committed the generated OpenAPI schema and generated TypeScript contract.
- [x] Documented reproducible setup and development commands in the root README.

Milestone 1 completed with both applications starting successfully, the PostGIS
extension verified through the database integration test, and all documented
automated checks passing.

## 5. Milestone 2 Result

- [x] Added domain applications for events, organizers, venues, sources, and ingestion.
- [x] Implemented source representations, immutable raw-document metadata,
  extraction attempts, candidates, canonical events, series, occurrences,
  registrations, provenance, organizers, classifications, buildings, venues,
  aliases, and explicit association models.
- [x] Enforced candidate idempotency, exact-one registration ownership,
  occurrence time consistency, and single-primary organizer, venue, and source
  rules with database constraints.
- [x] Added real PostGIS geography points through GeoDjango in a reproducible
  Docker backend containing GDAL, GEOS, and PROJ.
- [x] Seeded editable format, topic, purpose, and audience vocabularies.
- [x] Seeded 51 reviewed core NTU/NIE buildings, halls, and landmarks,
  building-level venues, and evidence-backed aliases.
- [x] Registered all core records in Django Admin and verified representative
  change-list access.
- [x] Added model, constraint, PostGIS, migration, seed, and Admin regression tests.

Milestone 2 completed with all migrations applied successfully and 35 backend
and ingestion tests passing against PostgreSQL/PostGIS. Seeded locations remain
without map coordinates until a reviewed authoritative coordinate import is
available; coordinates were not guessed.

## 6. Milestone 3 Progress

- [x] Added the strict, source-neutral `event-candidate-v1` contract with
  occurrence, registration, organizer, classification, evidence, and ambiguity
  fields.
- [x] Selected public Telegram broadcast channels as the first production
  ingestion source; one registered source is one channel and one queued job
  processes one source.
- [x] Added `IngestionRequest` grouping for Admin, command, and scheduled
  triggers plus durable single-source `IngestionJob` records, atomic PostgreSQL
  claiming, heartbeats, periodic stale-job recovery, retry state, and per-source
  active-job deduplication.
- [x] Added the polling Django worker command and a dedicated Docker Compose
  worker service without introducing Redis, Celery, or a general task framework.
- [x] Added Telethon channel discovery/registration, one-time terminal login,
  saved ignored sessions, incremental message checkpoints, bounded backfill,
  and text/caption-only public-channel retrieval.
- [x] Added high-recall `gpt-5-nano` screening in fixed batches of 20 followed
  by `gpt-5-mini` candidate extraction in fixed batches of five, with up to ten
  concurrent OpenAI requests and structured Pydantic outputs.
- [x] Added batch-level `ModelInvocation`, per-message `MessageScreening`, and
  links to per-message extraction runs so one provider response can be audited
  across every affected message.
- [x] Added selective immutable local raw-content storage under ignored
  `var/raw/`: relevant, uncertain, and failed messages are retained; confirmed
  non-event bodies are discarded while identity, hash, decision, and versions
  remain inspectable.
- [x] Added deterministic candidate validation for missing locations,
  structured ambiguities, long timed ranges, online-only events, and explicit
  off-campus cases.
- [x] Added source Admin ingestion actions, queue and inline management commands,
  external-scheduler enqueue support, worker inspection, and candidate review
  through Django Admin.
- [x] Added JSON—not JSONL—Telegram regression fixtures and focused tests for
  request/job grouping, fixed batch sizes, selective raw retention, and unchanged
  rerun candidate idempotency.
- [x] Applied the required migrations and passed the complete repository verification
  suite against PostgreSQL/PostGIS: formatting, lint, type, Django, migration,
  OpenAPI drift, 67 backend/ingestion tests, and one web test.
- [ ] Perform one authenticated production-path Telegram run, inspect screening,
  invocation, failure, and candidate records in Django Admin, and confirm an
  unchanged rerun creates no duplicate candidates or OpenAI calls.
- [ ] Expand the reviewed labelled Telegram evaluation set toward 50–100 real,
  production-intent messages before relying on screening quality.

Milestone 3 remains in progress. Canonical event creation, venue resolution,
duplicate matching, and publication remain Milestone 4 work.

## 7. Progress Rules

- Keep one milestone active at a time.
- Complete the current vertical path before broadening source coverage or polishing the interface.
- Collect personal-use evidence before Milestone 9; local usability does not authorize public exposure.
- Add migrations, tests and representative fixtures with the behavior they support.
- Update this document when a milestone starts, completes or changes scope.
- Introduce abstractions only when the active vertical slice demonstrates the need.

## 8. Task Completion Standard

An implementation task is complete when:

- Its behavior is implemented and locally reproducible.
- Relevant automated tests pass.
- Schema changes include migrations.
- Ingestion behavior includes representative fixtures.
- API contract changes update OpenAPI and the generated API client.
- Material decisions or limitations are documented.

Time estimates are intentionally omitted until the first source and development environment reveal the actual workload.
