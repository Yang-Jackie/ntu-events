# NTU Events Architecture

Current ownership and dependency direction. See the
[technical specification](TECHNICAL_SPECIFICATION.md) for behavior and the
[development guide](DEVELOPMENT.md) for setup and commands.

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
├── docs/                        # Product, behavior, progress, and development docs
├── scripts/
├── storage/                     # Ignored research output and source sessions
├── var/
│   └── raw/                     # Ignored application raw-content storage
├── compose.yaml
├── .env.example
├── AGENTS.md                    # Shared coding-agent instructions
└── CLAUDE.md                    # Imports AGENTS.md for Claude Code
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
- `venues`: hierarchical location anchors, attendable venues, aliases, the
  reviewed non-geographic catalog, its generated official-facility snapshot,
  the separate reviewed building-point snapshot and map provenance, repeatable
  synchronization, and future resolution behavior
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

The ingestion app keeps its Django models and migration identity while grouping
behavior by responsibility:

```text
ingestion/
├── admin/                       # Registrations, forms, and presentation
├── jobs/                        # Source-job lifecycle and ingestion worker
├── pipelines/<source>/          # Source access, screening, extraction, batching
├── candidates/                  # Candidate creation, repair, and validation
├── contracts/                   # Shared payload schemas and vocabulary
└── canonicalization/
    ├── workflow.py              # Public orchestration and optional application
    ├── worker.py                # Candidate polling and exclusive execution
    ├── decisions/               # Matching, evidence, projection, model decisions
    ├── plans/                   # Plan persistence, repair, and proposal validation
    ├── application/             # Transactional Event changes and provenance
    ├── snapshots.py             # Frozen Event graphs and stale-state hashes
    └── normalization.py         # Shared comparison normalization
```

Source pipelines stop at a persisted `EventCandidate`. Shared candidate creation
and repair live in `candidates/service.py`; their validators live under
`candidates/validation/`. Pipeline registration lives in `pipelines/registry.py`.

`canonicalization/workflow.py` coordinates decisions, plan creation or repair,
and optional application. Worker model calls run outside the plan transaction
and retain the matching snapshots used for reconciliation. Inside one transaction,
the workflow uses `plans/service.py` to lock and revalidate the candidate,
prepare its sole plan, and freeze its lifecycle. Automatic application follows
that transaction rather than running inside the plan service. Plan repairs also
commit before optional application.

`decisions/service.py` returns the proposal and retained matching/model evidence.
It accepts the source-neutral decision-provider interface and never writes a
canonical Event or finalizes a candidate. `plans/service.py` owns plan validation,
versions, review state, and candidate transitions; it does not import decision or
application services. `application/service.py` revalidates and applies a plan,
checks stale state, and records observations and revisions transactionally.
Proposal validators are shared by plan management and application without
calling either service. Both stages use the shared snapshot and normalization
modules rather than importing matching internals.

External callers use the owning modules: candidate operations from
`candidates/service.py`, enqueue operations from `jobs/service.py`, canonicalization
use cases from `canonicalization/workflow.py`, and explicit plan application from
`canonicalization/application/service.py`. Package initialization files do not
re-export workflow services. The Admin package explicitly loads its registrations
for Django discovery.

Each worker owns its polling and resource cleanup, including failed startup.
Releasing a held canonicalization lock is attempted even if provider cleanup fails.
The ingestion worker also
owns periodic stale-job recovery. The canonicalization worker owns the global
PostgreSQL advisory lock and verifies its database session before and after
candidate processing. Commands configure workers and handle terminal output and
interrupt reporting. Workers remain processes in the same modular Django app,
with the same domain data and ownership.

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

## 9. Open architecture choices

Internal package layout, provider lifetime, scheduling, production storage, and
public deployment topology should follow demonstrated needs. Institutional map
data and indoor features require approved access and scope first. The
[implementation plan](IMPLEMENTATION_PLAN.md) owns milestone decision checkpoints.
