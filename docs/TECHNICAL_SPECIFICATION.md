# NTU Events Technical Direction

**Document status:** Active high-level technical direction
**Related documents:** `BUSINESS_REQUIREMENTS.md`, `ARCHITECTURE.md`,
`IMPLEMENTATION_PLAN.md`

## 1. Purpose and level of detail

This document translates the product direction into durable technical goals and
system boundaries. It intentionally avoids deciding field lists, exact schemas,
matching algorithms, status machines, endpoint parameters, provider settings,
and workflow thresholds before the relevant feature is implemented.

Those details should be decided during the owning milestone using real inputs,
tests, and the existing implementation. Once verified, durable behavior may be
recorded here at the level needed to guide later work.

The implementation plan is authoritative for progress and sequencing. The
architecture document is authoritative for repository ownership and dependency
direction.

## 2. Technical goals

The system should:

- Collect event information from heterogeneous approved public sources
- Preserve provenance and enough source evidence for audit and reprocessing
- Convert source observations into reviewable event candidates
- Maintain normalized event, occurrence, organizer, classification, and
  location data
- Prevent unsafe duplicate creation and protect manual decisions
- Support building-level geographic discovery
- Expose a stable contract to the web application
- Make ingestion and processing failures inspectable
- Remain maintainable by a solo developer or small team

Correctness, traceability, and ease of change are more important than
internet-scale throughput.

## 3. Implemented baseline

The repository currently uses:

- Python 3.13 and Django 5.2
- Django REST Framework and `drf-spectacular`
- PostgreSQL 18 with PostGIS 3.6 through Docker Compose
- Next.js 16 with TypeScript
- A generated TypeScript API contract in `packages/api-client`
- Django Admin for internal operations
- A database-backed ingestion worker
- `uv` and `pnpm` with committed lockfiles
- Ruff, pytest, Prettier, ESLint, TypeScript checks, Vitest, Django checks, and
  API-contract drift checks

These are current implementation facts, not a requirement that later
capabilities must be forced into an unsuitable tool. Material changes should be
justified against an observed need and reflected in the architecture.

## 4. Engineering principles

### Modular application

Keep the backend as a modular Django application unless a demonstrated
operational need justifies another service boundary. Background processes may
run separately while using the same application workflows and domain data.

### Canonical data ownership

The normalized database is authoritative for what the product displays.
Retrieval tools and models produce observations or candidates; they do not
directly determine canonical or visible event state.

### Evidence and provenance

Retain enough immutable source evidence and processing metadata to explain an
event, diagnose failures, and support later reprocessing. Retention may differ
by source and outcome when privacy, volume, or platform constraints require it;
decide that policy with each source integration.

### Source-appropriate processing

Prefer reliable structured source data when it exists. Use model-assisted
interpretation for genuinely unstructured material. Keep permissions, schema
validation, persistence, and user-visible decisions in deterministic
application code.

### Incremental complexity

Do not add infrastructure or abstractions before the active vertical slice
demonstrates the need. In particular, the initial product does not require
microservices, Kubernetes, streaming infrastructure, a vector database, or a
dedicated search engine.

## 5. System responsibilities

The system is divided into:

- A Django backend that owns domain data, ingestion workflows, internal review,
  and the API
- A Next.js application that owns discovery presentation and browser
  interaction
- A generated API-client package that carries the backend contract into
  TypeScript
- Background ingestion execution using backend workflows
- PostgreSQL/PostGIS for relational and geographic data
- Raw-content storage behind an application interface

The initial Django backend and database run through Docker Compose. Next.js runs
on the host during development. Application raw content uses ignored
`var/raw/`; Telegram sessions and research-harness output use ignored
`storage/`.

## 6. High-level data flow

```text
Approved source
    ↓
Retrieval and preserved source observation
    ↓
Candidate interpretation
    ↓
Validation and review
    ↓
Venue and canonical-event processing
    ↓
Owner-visible event data
    ↓
Versioned API and map/list interface
```

Stages should leave enough state to inspect success, failure, and reruns. The
exact stage boundaries and state transitions should evolve with the workflow
being implemented rather than being fixed by this overview.

## 7. Core concepts

The following distinctions are important even though their exact schemas may
change:

- **Source:** an approved place from which content is collected.
- **Source representation:** one logical published item from a source, such as
  a Telegram message or webpage entry.
- **Raw source document:** a preserved retrieval observation or artifact.
- **Ingestion request and job:** durable records used to trigger, execute, and
  inspect source processing.
- **Extraction attempt and candidate:** the interpretation history and
  provisional event data produced from source material.
- **Event and occurrence:** the conceptual activity and the attendable time and
  place information presented to users. One event may have multiple labeled
  occurrences with different dates, locations, attendance modes, meeting
  access, or registration details.
- **Organizer and classification facets:** normalized discovery metadata.
- **Building and venue:** canonical location data kept separate from raw
  source wording.
- **Registration:** external participation information associated with the
  appropriate event or occurrence.
- **Provenance and revision information:** links and history needed to explain
  canonical data and later changes.

When implementing a concept, decide its fields, cardinality, constraints, and
state model from the real workflow. Preserve the distinctions above unless
implementation evidence shows that a boundary is unnecessary or incorrect.

## 8. Ingestion direction

### Current first production source

The first production ingestion source is selected public Telegram broadcast
channels accessed through the owner's authenticated Telethon session. The
current pipeline:

- Registers channels as independent sources
- Retrieves text and captions
- Uses model-assisted screening and candidate extraction
- Persists durable job, invocation, screening, extraction, candidate, and
  provenance-related records
- Retains relevant, uncertain, and failed content while keeping reduced audit
  metadata for confirmed non-events
- Exposes operations through commands, Django Admin, and a polling worker

The root README documents current commands and provider configuration. Details
such as client lifetime, retry behavior, batching, and cache keys belong to the
implementation and tests; when they affect durable behavior, document the
outcome after it is verified.

### Other sources

The NTU CCDS events site was used as structured-source research and remains a
candidate for later official-site ingestion. It is not the implemented first
production pipeline.

Each future source should choose the least complex reliable retrieval and
interpretation method. Shared workflow rules should remain source-neutral,
while access and parsing behavior may be source-specific.

### Retrieval safety

Browser or managed retrieval, when introduced, must remain bounded to approved
public content. Authentication beyond approved owner access, submissions,
purchases, CAPTCHA bypass, and other external state changes require separate
authorization and are outside ordinary ingestion.

Treat source content and provider output as untrusted.

## 9. Processing decisions

Milestone 4 owns the detailed decisions in this section. The documentation
records the questions and required outcomes, not their implementation in
advance.

### Candidate contract

The candidate contract retains complete model output even when the source facts
are incomplete, ambiguous, or internally inconsistent. Missing source facts
use explicit unknown or empty representations. Occurrences have candidate-local
references so registrations can identify their intended occurrence.

Extraction receives a snapshot of supported classification and venue values.
The model may suggest those values, while unmatched source-grounded values
remain available for review. Model suggestions do not create or modify trusted
canonical records.

Candidate schemas and extraction instructions are versioned so changed
semantics can be reprocessed safely.

### Validation

Structurally malformed, incomplete, or unassociateable provider output creates
no candidate. The source observation, failed invocation, error metadata, and
available provider response remain inspectable for diagnosis.

Once an event candidate is structurally interpretable, business-rule problems
do not discard it. Validation records structured issues and routes any affected
candidate to review. Issues may block canonicalization without blocking
storage. Product-scope eligibility is not used to reject an extracted
candidate.

### Venue resolution

Keep raw location text even when a canonical venue is found. Prefer reviewed
authoritative location data and never create trusted venue records solely from
model output.

During implementation, decide the matching order, confidence handling, and
review path from observed location strings and the seeded campus data.

### Canonicalization and duplicates

Canonical processing must be safely repeatable, preserve provenance, avoid
accidental duplicate creation, and protect manual corrections.

During implementation, decide:

- When a candidate creates a new event
- When it should be held for review
- How repeated, edited, or conflicting source content is handled
- When two representations refer to the same event
- What is committed atomically
- What history or reversal support is needed

Do not introduce automatic cross-source merging or update behavior until its
rules are supported by representative cases and focused tests.

### Publication

Canonical storage and visibility are separate concerns. The personal product
should keep automatically processed data reviewable and non-public by default.
Automatic publication, if ever introduced, requires evidence-based thresholds
and an explicit later decision.

## 10. API and web direction

The backend exposes versioned API endpoints documented through OpenAPI. The
committed schema generates the TypeScript contract used by the web
application. Generated files are changed through the repository generation
workflow rather than edited manually.

The event API should eventually support:

- Event list and detail retrieval
- Time, location, classification, and audience filtering
- Keyword search
- Map-oriented geographic queries
- Clear separation between internal and discoverable data

Exact endpoint shapes, identifiers, filter names, pagination, ordering, and map
payloads should be decided during the API milestone and captured in OpenAPI.

The web application should provide the map, synchronized list, filters, and
event details defined in the business requirements. URL state, server/client
rendering boundaries, and map-provider choice should be decided while building
that interface.

## 11. Time and location direction

The current product interprets event schedules in the NTU Singapore context.
The implementation must preserve date-only and ambiguous source information
without inventing precision. Attendance mode and public meeting access belong
to the occurrence because different sessions of one event may differ.

Detailed treatment of multi-day events, separate sessions, recurrence,
overnight events, registration windows, and timezone exceptions should be
decided with candidate and canonicalization work.

The map initially uses reviewed building-level locations. Precise venue text
can be shown before room-level geometry exists. Coordinates must come from an
approved authoritative source and must not be guessed.

## 12. Internal operations

Django Admin is the initial internal interface. It should make the current
workflow inspectable and provide review or correction actions as those
capabilities are implemented.

Prefer standard Admin behavior until a demonstrated workflow needs a custom
interface.

Long-running ingestion work belongs outside public request handlers. Job
execution should isolate failures, support safe reruns, and expose enough state
for troubleshooting. Scheduling and more advanced queue infrastructure remain
implementation decisions until required.

## 13. Security and privacy

- Keep secrets and source sessions outside version control.
- Treat raw content, extracted URLs, and model output as untrusted.
- Require authentication for internal administration.
- Expose only intended data through discovery APIs.
- Avoid collecting personal schedules, course data, or precise user location
  during the initial product.
- Review source access rules and provider terms before scheduled or public use.
- Do not expose the personal deployment publicly before the release gate.

The eventual public authentication, rate-limiting, and abuse-prevention design
should be decided during public-readiness work.

## 14. Testing and verification

Testing should follow implemented behavior and risk. Important areas include:

- Domain constraints and workflow decisions
- Ingestion reruns and failure recovery
- Source adapters using saved or mocked inputs
- Candidate interpretation and validation cases
- Venue resolution and duplicate behavior when introduced
- API visibility, filters, and spatial queries
- Web map/list synchronization and detail rendering
- Critical end-to-end discovery paths

Ordinary automated tests should not depend on live provider calls. Bugs found in
real ingestion should become reproducible fixtures or focused test cases when
the source material can be retained appropriately.

Schema changes require migrations. Public API changes require regenerated
OpenAPI and client artifacts. Repository checks should remain runnable through
the documented root commands.

## 15. Deferred capabilities

The following remain deferred until the product demonstrates a need:

- Public accounts, bookmarks, notifications, and personalization
- Calendar or timetable integration
- Natural-language search and recommendations
- Organizer portals, internal registration, and payments
- Indoor navigation
- Dedicated search or vector infrastructure
- Automatic source discovery
- Private-source ingestion
- Distributed services or streaming infrastructure
- Production hosting and public operations

## 16. Decisions to make in later milestones

- **Processing workflow:** candidate states, validation outcomes, venue
  resolution, canonicalization, duplicate handling, and review behavior
- **API:** resource shapes, filter semantics, identifiers, ordering, and map
  query behavior
- **Discovery interface:** map provider, rendering boundaries, interaction
  details, and accessibility behavior
- **Personal-use hardening:** change handling, manual override protection,
  recovery behavior, and operational cadence
- **Source expansion:** access method, retention policy, and source-specific
  quality controls
- **Public readiness:** hosting, authentication, monitoring, privacy, security,
  quality thresholds, and rollout plan
