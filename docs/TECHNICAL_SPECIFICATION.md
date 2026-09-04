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
- Prevent unsafe duplicate creation and stale writes to canonical events
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

## 5. System boundaries

`ARCHITECTURE.md` is authoritative for repository ownership and dependency
direction. In summary, Django owns domain data, workflows, internal review, and
the API; Next.js owns presentation; the generated client carries the API
contract; and PostgreSQL/PostGIS owns normalized relational and geographic
state. Raw content remains behind an application interface rather than becoming
canonical product data.

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

Preserve these distinctions:

- A source representation identifies one logical published item; raw source
  documents preserve individual retrieval observations of it.
- An EventCandidate is a provisional interpretation, while Event and occurrence
  records are canonical product data.
- One Event may have several attendable occurrences with different schedules,
  locations, attendance modes, meeting access, or registration details.
- Raw location wording remains separate from normalized buildings and venues.
- Provenance and workflow records explain how source evidence affected the
  canonical Event graph.

Exact fields, cardinality, constraints, and state transitions follow the
implemented workflow rather than this summary.

## 8. Ingestion direction

### Current first production source

The first production ingestion source is selected public Telegram broadcast
channels accessed through the owner's authenticated Telethon session. The
current pipeline:

- Registers channels as independent sources
- Retrieves text, captions, and URL metadata attached to message entities and
  public buttons
- Uses model-assisted screening and candidate extraction
- Persists durable job, invocation, screening, extraction, candidate, and
  source-evidence records; the separate canonicalization worker persists plans
  and canonical provenance
- Retains relevant, uncertain, and failed content while keeping reduced audit
  metadata for confirmed non-events
- Exposes operations through commands, Django Admin, and a polling worker

The root README documents current commands and provider configuration. Details
such as client lifetime, retry behavior, batching, and cache keys belong to the
implementation and tests; when they affect durable behavior, document the
outcome after it is verified.

A stale RUNNING ingestion job is requeued with the same identity and a new
attempt number. For Telegram screening, a later attempt replaces the job's
per-message screening result, while each model invocation remains retained as
attempt history. This lets a reclaimed attempt continue without a uniqueness
failure after an earlier attempt persisted a failed screening result.

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

## 9. Processing workflow

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

Telegram link targets and their visible labels remain part of the raw source
observation even when Telegram stores them outside the message text. They are
untrusted evidence supplied to extraction, not URLs the ingestion workflow
follows. Candidate registration URLs represent external sign-up actions.
Occurrence meeting URLs represent direct public access to an online or hybrid
attendance option; general pages, forms, stores, and informational links are
not meeting access.

### Validation

Structurally malformed, truncated, or unassociateable provider output creates
no candidate. The source observation, failed invocation, error metadata, and
available provider response remain inspectable for diagnosis.

Once an event candidate is structurally interpretable, validation records
structured issues without discarding it. A candidate is BLOCKED only when its
title is missing, it contains only a title and no other useful event information,
occurrence references are duplicated, registration ownership references are
missing, unknown, or illegal, an occurrence ends before it starts, or a
registration closes before it opens. Other incomplete or inconsistent optional
facts remain review issues. A useful sparse candidate may still proceed without
an occurrence, date, venue, organizer, registration, or resolved classification.
Product-scope eligibility is not used to reject an extracted candidate.

A useful registration may be projected even when its source-provided display
name is missing. The canonical record receives a neutral label while the
missing name remains a candidate issue. Invalid URLs and inconsistent optional
fields remain visible in the effective payload; independently useful registration
details are preserved when they can be attached to an event or occurrence
without guessing ownership.

For an automatic no-match ADD, the candidate remains the complete evidence
record while projection omits data that cannot safely form canonical storage.
Occurrences without a start date are not projected; inconsistent optional time
precision and invalid optional URLs are cleared rather than guessed; and an
occurrence-scoped registration is omitted when its occurrence cannot be
projected. These omissions never mutate the candidate payload.

### Venue resolution

Keep raw location text even when a canonical venue is found. Prefer reviewed
authoritative location data and never create trusted venue records solely from
model output.

The initial path accepts supported venue identifiers supplied during extraction.
Unknown or unresolved locations with no proposed catalog relationship remain
in the effective payload and are flagged; they do not prevent creation of the
event. A canonicalization proposal that does supply a nonexistent venue ID is
rejected atomically. Broader location matching remains later work and should be
based on observed source wording.

### Canonicalization and duplicates

`EventCandidate` owns both the immutable extracted payload and an effective
payload initially copied from it. Its lifecycle is BLOCKED, READY, or PROCESSED.
BLOCKED includes invalid candidates and manual rejection reasons; there is no
separate candidate-level REJECTED state. A reviewer may edit only a BLOCKED
candidate's effective payload and notes. A valid repair moves it to READY and
thereby approves it for the same canonicalization queue as a newly extracted
READY candidate. Creating the candidate's sole `CanonicalizationPlan`,
regardless of that plan's status, moves the candidate to PROCESSED and freezes
candidate editing. Later corrections belong to the plan before application or
directly to the canonical Event after application.

Ingestion and canonicalization run as separate background processes. A
source-specific ingestion job succeeds once retrieval, screening, extraction,
and candidate persistence finish; canonicalization outcomes do not change that
job status. A source-neutral worker serially selects every READY candidate that
has no plan, reconstructs its raw evidence through the candidate's extraction
provenance, and runs matching and canonicalization. PostgreSQL session advisory
locking permits at most one canonicalization worker globally. Unexpected worker
errors leave the candidate READY and terminate the process visibly; broader
retry and claim state is deferred until operating evidence warrants it.

Each extracted candidate also records whether it is an event announcement,
event follow-up, or unknown. This observation classification is descriptive and
does not currently alter matching or application behavior.

A READY candidate first retrieves a bounded canonical-Event pool instead of
scanning every Event graph. PostgreSQL `pg_trgm` and a GiST index return the 10
nearest normalized titles; exact source-representation and registration-URL
matches plus bounded occurrence-date, canonical-organizer, and canonical-venue
lookups are unioned into that pool. Matching deliberately compares only the
current canonical Event graph, not payloads from its prior observations.

The pool receives a fixed additive matching score with no available-field
denominator and no identity gate. Weights are title 65%, normalized registration
URL 15%, occurrence date 10%, organizer 4%, venue 4%, and registered source 2%.
Missing and nonmatching facts contribute zero. Title uses trigram similarity, a
normalized exact registration URL gets full credit, an exact date gets full
credit, and a date within one day gets 40% date credit. When the nearest known
candidate/Event dates are at least 120 days apart, date similarity is -2 and
therefore subtracts 20 score points. Organizer and venue sets use overlap
similarity.

A possible match must score at least 30%. Only the five highest scores are
stored as `CandidateMatch` evidence. Each record explains field availability,
weight, similarity, signed contribution, retrieval reason, and evidence
signals. The score is matching evidence, not a probability. The plan snapshot
presents it as a percentage and copies the complete candidate Event snapshots
used by reconciliation.

The owner-operated slice accepts the current weights and threshold with the
existing focused coverage. Additional fixture calibration is evidence-driven,
not a prerequisite for the Event API; revisit it when observed duplicates or
false matches show that adjustment is needed.

No qualifying match creates an ADD plan automatically, including for sparse
follow-ups. When matches exist, the reconciliation model receives the candidate
payload, raw source document, current catalog, and complete snapshots of up to
five possible Events. It must choose exactly one ADD, UPDATE, or LINK_ONLY
action against at most one Event. Multiple matches are alternatives, never
several mutation targets.

`CanonicalizationPlan` preserves the immutable generated proposal separately
from its editable effective proposal. ADD carries a complete new Event graph.
UPDATE uses sparse operations: existing owned objects reference their IDs, new
owned objects use a null ID, whole-object deletion is REMOVE, unchanged fields
have no operation, and scalar clearing is explicit CLEAR. Classification updates
use explicit ADD_CODES, REMOVE_CODES, or REPLACE_CODES operations; an empty
replacement explicitly clears that classification kind. LINK_ONLY contains no
canonical mutations. Event-to-Event merging is outside this workflow.

Proposal shape, target membership, child ownership, required fields, catalog
references, and supported classification codes are hard application checks. A
failure rejects the whole plan and writes none of it. Domain-plausibility and
grounding concerns do not reject a plan. The current automatic grounding flag
detects synthesized descriptions; broader domain and grounding flag generation
remains pending. A model may synthesize a combined description; unsupported
factual claims remain grounding concerns rather than schema failures.

Application is transactional, version checked, and idempotent. UPDATE and
LINK_ONLY plans carry a hash of the complete target graph and become STALE if
the Event changes before application. Successful actions create or reuse an
`EventSourceLink`, append an immutable `EventObservation`, and ADD/UPDATE actions
record `EventRevision` before/after snapshots. Applied plans and PROCESSED
candidates are immutable through this workflow.

Reconciliation receives a snapshot of the latest committed Event graph. Manual
edits made before that snapshot are therefore visible to the decision provider,
but source-derived canonical fields are not manual overrides: a valid later
automatic UPDATE may replace them. The graph hash prevents a plan from applying
if the Event changes after its snapshot. The current owner-operated scope does
not add an application-owned manual-edit audit trail or field-level protection.
Publication and verification state remain owner-controlled and are not writable
through canonicalization proposals.

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

The read-only discovery contract exposes `GET /api/v1/events/` and
`GET /api/v1/events/{id}/`. Numeric IDs are stable API identifiers; slugs are
presentation data. Both endpoints expose only PUBLISHED Events, so draft,
pending-review, withheld, and archived records remain internal and detail
lookups for them return not found. Verification state is returned as
information and does not independently grant visibility.

The list response contains compact Event metadata, classifications, organizers,
and matching occurrences with schedule, attendance, raw location, venue,
building, and resolved map-point data. Detail adds descriptive fields, meeting
links, registrations, and public source links. It never exposes raw documents,
candidate payloads, model output, or internal workflow records. A venue's own
point is returned when present; otherwise its building point is used.

The list accepts `q`, `date_from`, `date_to`, `attendance_mode`, `format`,
`topic`, `purpose`, `audience`, `building`, `bbox`, `ordering`, and `page`.
Date bounds use occurrence overlap semantics. Occurrence-level filters restrict
the nested occurrences returned by the list, while detail always returns the
complete Event. `bbox` uses WGS84 `west,south,east,north` bounds and, like the
building filter, excludes online-only or unresolved locations. Without a
physical-location filter, those occurrences remain visible. Ordering is by the
earliest or latest matching occurrence date with undated Events last, and
page-number pagination returns 50 Events per page.

The current discovery API requires no application login because it is limited
to published data and Docker Compose binds both Django and PostgreSQL host ports
to `127.0.0.1`. This is a local network boundary, not identity authentication;
remote access requires a separate approved private-access or authentication
decision.

The web application should provide the map, synchronized list, filters, and
event details defined in the business requirements. URL state, server/client
rendering boundaries, and map-provider choice should be decided while building
that interface.

## 11. Time and location direction

The current product interprets event schedules in the NTU Singapore context.
The implementation must preserve date-only and ambiguous source information
without inventing precision. Attendance mode and public meeting access belong
to the occurrence because different sessions of one event may differ.

Extracted candidate times and canonicalization-proposal times are stored as
Singapore local wall-clock values without a UTC offset or timezone suffix. At
the model-output boundary, an exact `+08:00` offset is accepted and stripped
because it represents the same Singapore clock value without changing the
associated date. Other offsets are structurally invalid and are rejected
rather than converted without their associated date, because time-only
conversion can silently cross a date boundary. Cross-midnight activities
remain representable through their separate start and end dates.

The current model can retain multiple occurrences and registration windows.
Further edge-case behavior for recurrence, overnight events, and timezone
exceptions belongs to hardening when representative sources require it.

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
- Deduplication decisions, false matches, revisions, reruns, and stale writes
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

`BUSINESS_REQUIREMENTS.md` owns the deferred product scope. Corresponding
technical infrastructure, including dedicated search, distributed services,
streaming, and public hosting, remains deferred until an approved capability
demonstrates the need.

## 16. Pending decisions

`IMPLEMENTATION_PLAN.md` owns milestone sequencing and pending decisions.
Durable technical outcomes return here only after implementation and
verification.
