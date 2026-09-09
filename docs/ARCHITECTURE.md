# NTU Events Architecture

**Document status:** Active repository boundaries
**Related documents:** `TECHNICAL_SPECIFICATION.md`, `IMPLEMENTATION_PLAN.md`

## 1. Purpose

This document describes current responsibility boundaries and the preferred
dependency direction. These defaults help new work fit the repository without
turning today's folder structure into a permanent design. Product, safety, and
data-ownership boundaries are firm where stated; internal class structure,
algorithms, schemas, provider mechanics, and future service boundaries remain
open to evidence from the milestone that needs them.

## 2. Repository shape

The project is a monorepo:

```text
ntu-events/
├── apps/
│   ├── backend/                 # Django domain, API, admin, and workers
│   └── web/                     # Next.js discovery application
├── packages/
│   └── api-client/              # Generated TypeScript API contract and client
├── fixtures/                    # Version-controlled source and regression inputs
├── tests/                       # Backend, ingestion, and cross-cutting tests
├── src/                         # Host-operated research tooling
├── docs/
├── scripts/
├── storage/                     # Ignored research output and source sessions
├── var/
│   └── raw/                     # Ignored application raw-content storage
├── compose.yaml
├── .env.example
└── README.md
```

New top-level directories should be added only when they have a clear owner and
current use.

## 3. Current application boundaries

### Backend

The Django backend owns:

- Canonical event and occurrence data
- Sources, ingestion history, and processing workflows
- Organizers, classifications, buildings, and venues
- Internal review and publication decisions
- The event API
- Internal administration

Background workers are separate runtime processes, not separate business
services. They invoke backend-owned workflows and use the same domain data.

### Web

The Next.js application owns:

- Page rendering and discovery navigation
- Map, list, filter, and detail interactions
- URL and browser presentation state

It consumes the backend contract and must not recreate ingestion,
canonicalization, venue, duplicate, or publication rules.

### API client

`packages/api-client` is the contract boundary between Python and TypeScript.
It contains generated OpenAPI types and a small runtime client factory.

Generated artifacts are produced by the documented generation workflow.
Application-specific business behavior remains in the backend or the consuming
web feature, not in generated code.

## 4. Backend ownership

The current Django applications are organized by domain or capability:

- `events`: canonical events, occurrences, registrations, and classification
  relationships
- `venues`: buildings, venues, aliases, and future resolution behavior
- `organizers`: organizer data
- `sources`: registered sources, source representations, and raw-document
  metadata
- `ingestion`: requests, jobs, candidate processing, source pipelines,
  provider boundaries, and worker execution
- `common`: small domain-neutral infrastructure shared across applications

Add moderation, search, interaction, or other domains when implemented behavior
needs a distinct owner. Do not create empty layers or applications only to
match a speculative directory tree.

Entry points such as API views, Admin actions, workers, and management commands
should remain thin. Behavior shared by several entry points belongs to the
domain or workflow that owns it.

Django models, querysets, and managers are the ordinary relational persistence
boundary. Introduce a separate interface where implementations genuinely vary,
such as raw-content storage or an external provider.

## 5. Ingestion boundary

Ingestion coordinates the path from source material to reviewable and canonical
data.

Source-specific code may own:

- How an approved source is accessed
- How source items are identified
- How raw provider results become shared source observations
- Source-specific interpretation support

Source-neutral workflow code owns:

- Durable execution and inspection
- Storage and provenance
- Candidate contract validation
- Candidate logical gates, deterministic matching, canonicalization plans, and
  transactional plan application
- Publication decisions
- Protection against unsafe reruns

External SDK objects and provider response types should stay behind their
pipeline or infrastructure boundary. Providers and models cannot directly
publish or modify canonical event data.

`ingestion` owns `EventCandidate`, `CandidateMatch`, and `CanonicalizationPlan`
because they describe interpretation and workflow. `EventCandidate` contains
the immutable extracted observation plus the editable effective payload and
BLOCKED/READY/PROCESSED logical gate; no separate review aggregate exists.
`events` owns the current Event graph plus `EventSourceLink`,
`EventObservation`, and `EventRevision` because they describe canonical state,
its source associations, and applied history. The canonicalization workflow is
the only automated writer across that boundary.

Within the current `ingestion` implementation, source-specific access,
screening, extraction, document handling, and stage runtime live under
`pipelines/<source>/`. Their durable
handoff is a persisted `EventCandidate`; shared candidate creation and repair
rules remain source-neutral. The `canonicalization` package currently contains
the workflow from a READY candidate through matching, reconciliation context,
proposal validation, plan creation, Event application, and provenance. It
accepts a source-neutral decision-provider interface, so canonicalization model
calls do not belong to any source pipeline. Source pipelines stop after
persisting their EventCandidates. A separate source-neutral worker consumes
unplanned READY candidates, including manually repaired ones. Preserving that
source-neutral dependency is the default; another package structure would need
to demonstrate the same isolation rather than being rejected solely for
organizing files differently. The worker is currently a separate process in
the same modular Django application, not a separate service or data owner.

The first implemented pipeline, and the first intended for the retained
personal-use trial, is Telegram text ingestion. Future pipelines may use
structured mapping, model-assisted extraction, OCR, managed retrieval, or
bounded browser interaction without changing the worker's general ownership.
Each source may split its adapter, documents, model client, screening,
extraction, and orchestration as its implemented complexity requires without
moving shared candidate or canonicalization policy into the source package.

## 6. Data and fixtures

`fixtures/` contains small version-controlled inputs needed for repeatable
tests or source research. A fixture should live near its owning adapter when it
is not meaningfully shared.

`var/raw/` contains ignored application evidence during local use.
`storage/` contains ignored research-harness output and source authorization
sessions. Neither directory is canonical product data.

PostgreSQL/PostGIS owns normalized product state and metadata that links it to
raw evidence.

Through Milestone 8, the local database and `var/raw/` are disposable
development state and may be rebuilt instead of migrated or backfilled across
implementation changes. Required catalogs and setup cannot rely on those stores
as their only copy; they must be reconstructible through repository-owned
migrations, catalogs or fixtures plus documented configuration and repeatable
source setup. Milestone 9 establishes a clean retained personal-use state. From
that boundary onward, PostgreSQL and its linked evidence are durable product
state that later changes must preserve or deliberately transform.

## 7. Dependency direction

```text
Web application
    ↓
Generated API client
    ↓
Backend API
    ↓
Application workflows and query logic
    ↓
Domain models and external interfaces
    ↓
Database, storage, and provider implementations
```

Within the backend:

- Domain behavior should not depend on API views, commands, workers, or frontend
  code without a demonstrated reason to revise the boundary.
- Entry points invoke shared owning workflows.
- Source and provider adapters do not own canonical-event or publication
  policy.
- Automated workflows may update source-derived Event fields but cannot change
  owner-controlled publication or verification state.
- Python and TypeScript share an API contract, not domain source files.

## 8. Runtime boundaries

Docker Compose provides PostgreSQL/PostGIS, the Django backend, and the
ingestion and canonicalization workers. The backend and workers share the same
image and dependency configuration. The web application runs on the host during
development.

The current worker uses database-backed jobs. Scheduler, concurrency, provider
resource lifetime, and future queue infrastructure should be changed only in
response to measured workflow or operational needs.

## 9. Deliberately open architecture details

- Internal file-versus-folder layout as domains grow
- Matching evaluation thresholds and broader source-update policy
- Search and map-query organization
- Production raw-content storage
- Scheduler and queue evolution
- Public deployment topology
- New application boundaries justified by implemented features
