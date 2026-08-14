# NTU Map-Based Event Discovery Platform
## Technical Specification

**Document status:** Initial technical specification  
**Primary audience:** Project owner, contributors, reviewers, and AI coding assistants  
**Related documents:** `BUSINESS_REQUIREMENTS.md`, `ARCHITECTURE.md`, `IMPLEMENTATION_PLAN.md`

---

## 1. Purpose

This document defines the initial technical direction for the NTU map-based event discovery platform.

It translates the product requirements into:

- System responsibilities
- Application boundaries
- Domain models
- Data flows
- API behavior
- Ingestion workflows
- Search and map behavior
- Validation and publication rules
- Testing and development standards

The first usable release is operated by the project owner for personal use. Deployment providers, infrastructure pricing, and production hosting decisions are intentionally deferred until the public-readiness gate unless they affect how the software must be designed.

---

## 2. Technical Goals

The system should:

1. Aggregate physical NTU event information from heterogeneous public sources.
2. Preserve raw source material for auditing and reprocessing.
3. Convert structured and unstructured source material into a common event-candidate contract.
4. Normalize dates, organizers, classification facets, and NTU locations.
5. Detect duplicate representations of the same event.
6. Maintain one canonical representation of each event.
7. Support building-level geographic display and location-based queries.
8. Expose a stable API for the personal-use frontend and later public frontend.
9. Provide an internal interface for reviewing and correcting data.
10. Remain maintainable by a solo developer or small team.
11. Support gradual expansion without premature microservice complexity.

---

## 3. Engineering Principles

### 3.1 Modular monolith first

The main backend should be implemented as one modular application rather than multiple business microservices.

Separate runtime processes are allowed for:

- Web/API serving
- Scheduled crawling
- Background extraction
- Data normalization
- Maintenance jobs

These processes should share the same domain models and application services where practical.

### 3.2 One canonical data model

The normalized database is the canonical source for all event information displayed by the product, whether used personally or publicly.

Retrieval providers, adapters, deterministic mappers, and language models produce candidates. They do not directly determine canonical or visible event state.

### 3.3 Raw data must be preserved

The system must preserve enough source content to explain how a normalized event was produced.

Normalized event records must never be the only retained representation of a source.

### 3.4 Source-appropriate interpretation with deterministic controls

Use the least complex reliable interpretation path for each source. Prefer structured APIs, feeds, exports, embedded metadata, or managed structured results when they provide the required facts reliably. Use language models as the primary interpretation mechanism for genuinely unstructured pages, documents, images, and mixed content. The system should avoid making brittle, source-specific field parsers the default for unstructured content.

Deterministic code owns retrieval permissions, raw capture, schema validation, normalization, persistence, duplicate safeguards, and publication rules. Retrieval providers and models may return observations, action traces, structured records, or candidates; neither directly determines canonical or public state.

### 3.5 Correctness before extreme scale

The expected initial scale is campus-level, not internet-scale.

The architecture should prioritize:

- Data correctness
- Auditability
- Clear ownership of logic
- Ease of debugging
- Maintainability

Extreme request throughput and distributed scaling are not initial design drivers.

### 3.6 Explicitly defer unnecessary infrastructure

The initial design should not require:

- Microservices
- Kubernetes
- Kafka
- A vector database
- Elasticsearch or OpenSearch
- Event sourcing
- A separate authentication service
- A recommendation model
- A custom indoor mapping engine

These may be reconsidered only when a demonstrated requirement appears.

---

## 4. Selected Application Architecture

The initial application consists of the following components:

### 4.0 Runtime and package-management baseline

- Python 3.13
- Django 5.2 LTS
- `uv` with a committed `uv.lock`
- Node.js 24 LTS, currently pinned to 24.18.0
- Next.js 16 with TypeScript and the App Router
- `pnpm` 11, currently pinned to 11.17.0, with a root workspace and committed
  `pnpm-lock.yaml`

Feature dependencies should use compatible ranges in project manifests while
lockfiles record exact resolved versions. Runtime major/minor versions are
recorded in repository version files and updated deliberately rather than
following `latest` implicitly.

### 4.1 Web application

A Next.js application is responsible for:

- Public page rendering
- Interactive map display
- Event list display
- Search and filter controls
- Event detail pages
- URL state
- Browser-side interactions
- Future bookmark and account interfaces

It must not own canonical event business logic.

### 4.2 Main application backend

A Django application with Django REST Framework is responsible for:

- Domain models
- Database access
- Public REST APIs
- Search and filtering logic
- Event publication rules
- Venue resolution
- Deduplication workflows
- Source management
- Data corrections
- Authentication and permissions when introduced
- Internal administrative operations

Django is the authoritative application backend.

### 4.3 Internal administration interface

Django Admin is used as the initial internal operations interface.

It should support:

- Reviewing event candidates
- Editing normalized events
- Resolving venues
- Inspecting source records
- Merging duplicates
- Reviewing crawl failures
- Controlling publication status
- Managing buildings, venues, aliases, organizers, classifications, and sources

The admin interface is separate from the discovery experience in both personal and public modes.

### 4.4 Background worker processes

Separate Python worker processes are responsible for:

- Scheduled source crawling
- Browser-based retrieval where necessary
- Content preprocessing
- Image or poster text extraction where introduced
- Language-model extraction
- Candidate validation
- Venue resolution jobs
- Duplicate analysis
- Event freshness checks

Workers should invoke shared Django application services or domain workflows rather than implementing independent business rules.

### 4.5 Primary database

PostgreSQL 18 with PostGIS 3.6 is the primary database. Local development runs
the database and Django backend as Docker Compose services; the database uses a
named volume, and Next.js runs on the host. The backend image supplies GDAL,
GEOS, and PROJ and uses GeoDjango's PostGIS backend. The repository is
bind-mounted for development, while Python dependencies remain isolated inside
the image-managed virtual environment. Django migrations enable and verify the
PostGIS extension.

The database service targets `linux/amd64` because the selected PostGIS image
does not provide an ARM64 variant. Docker Desktop emulates the database on
Apple Silicon, while AMD64 hosts run it natively.

It stores:

- Canonical event data
- Event occurrences
- Source definitions
- Raw-source metadata
- Extraction records
- Organizers
- Buildings
- Venues
- Venue aliases
- Classification reference values and associations
- Publication decisions
- Revisions
- Crawl and processing state
- Future user interactions

### 4.6 Raw-content storage

Raw source content is stored separately from normalized relational data.

During development, an ignored `var/raw/` directory implements the raw-content
storage interface. PostgreSQL stores retrieval metadata and the opaque storage
key, not the content itself. Stored evidence is immutable: another retrieval or
retry creates another retrieval record and object instead of overwriting prior
evidence. The interface must permit a later object-storage implementation
without rewriting ingestion workflows.

Raw content may include:

- HTML
- Plain text
- Post captions
- Structured source responses
- Image references
- Downloaded images where permitted
- Screenshots where necessary
- Language-model inputs
- Language-model outputs

### 4.7 Local environment configuration

Ignored `.env` files contain local secrets and machine-specific values.
`.env.example` documents every required setting without containing secrets.
Applications validate required configuration at startup. Repository defaults
may cover non-sensitive local values; source authorization sessions, raw
content, model credentials, and database credentials must remain ignored.

---

## 5. High-Level System Flow

```text
Registered source
      ↓
Scheduled crawl job
      ↓
Source-specific adapter
      ↓
Source representation and raw source document
      ↓
Preprocessing
      ↓
Structured event candidate extraction
      ↓
Schema and deterministic validation
      ↓
Normalization
      ↓
Venue resolution
      ↓
Create-only canonicalization with candidate idempotency
      ↓
Draft or review-required canonical event
      ↓
Internal review
      ↓
Public API
      ↓
Next.js map and event interface
```

Every stage should produce an inspectable result or status.

---

## 6. Repository Structure

A monorepo is recommended.

The detailed code-ownership and dependency rules are defined in `ARCHITECTURE.md`.

```text
ntu-events/
├── apps/
│   ├── web/                     # Next.js public frontend
│   └── backend/                 # Django, DRF, admin, workers
├── packages/
│   └── api-client/              # Generated TypeScript OpenAPI client
├── docs/
│   ├── BUSINESS_REQUIREMENTS.md
│   ├── TECHNICAL_SPECIFICATION.md
│   └── ARCHITECTURE.md
├── scripts/                     # Development and maintenance scripts
├── fixtures/                    # Saved source, agent-trace and extraction test fixtures
├── compose.yaml                 # Local development services
├── .env.example
└── README.md
```

Suggested Django application modules:

```text
apps/backend/
├── config/
├── events/
├── venues/
├── organizers/
├── sources/
├── ingestion/
├── moderation/
├── search/
├── interactions/
└── common/
```

Responsibilities should remain modular even though they run inside one Django project.

---

## 7. Core Domain Model

The precise schema may evolve, but the following concepts should remain distinct.

### 7.1 Source

Represents a registered place from which event information is collected.

Possible fields:

- `id`
- `name`
- `source_type`
- `base_url`
- `organization_id`
- `is_active`
- `crawl_frequency`
- `last_successful_crawl_at`
- `last_failed_crawl_at`
- `source_reliability`
- `adapter_key`
- `configuration`
- `created_at`
- `updated_at`

Example source types:

- NTU central webpage
- Faculty webpage
- Student organization webpage
- Public social account
- Public channel
- Manual source

Sensitive source configuration should not be stored in plaintext application records.

### 7.2 CrawlRun

Represents one attempt to fetch a source.

Possible fields:

- `id`
- `source_id`
- `started_at`
- `completed_at`
- `status`
- `http_status`
- `items_discovered`
- `items_processed`
- `error_type`
- `error_message`
- `retry_count`
- `content_hash`
- `worker_version`

A crawl run may produce zero or more raw source documents.

### 7.3 SourceRepresentation

Represents one logical published item from a source, such as one Telegram post,
one API item, or one event-listing entry. A source representation is not an
event: one representation may describe several events, and one real event may
eventually be supported by several representations.

Initial fields:

- `id`
- `source_id`
- `external_identifier`
- `source_url`
- `published_at`
- `content_type`
- `first_seen_at`
- `last_seen_at`
- `metadata`

`(source_id, external_identifier)` is the initial logical identity. For
Telegram, `external_identifier` is the message ID and the source identifies the
channel. Provider-specific identities must be preserved rather than derived
from titles or extracted event fields.

Source representation and representation revision are conceptually distinct.
A representation retains its identity when its content changes, while each
materially different content state would be an immutable revision. Revision
management, content-change detection, and canonical updates are deferred from
the first pipeline.

### 7.4 RawSourceDocument

Represents one preserved retrieval observation of a source representation
before extraction.

Initial fields:

- `id`
- `source_representation_id`
- `crawl_run_id`
- `fetched_at`
- `storage_key`
- `content_hash`
- `language`
- `processing_status`
- `metadata`

The first pipeline processes the preserved observation selected for a
representation but does not yet interpret changed content as a new revision. A
content hash avoids unnecessary reprocessing while raw observations remain
available for audit and later revision support.

### 7.5 ExtractionRun

Represents one attempt to convert a raw document into structured event candidates.

Possible fields:

- `id`
- `raw_source_document_id`
- `extractor_type`
- `extractor_version`
- `model_name`
- `prompt_version`
- `started_at`
- `completed_at`
- `status`
- `input_storage_key`
- `raw_output_storage_key`
- `token_usage`
- `error_message`

Every model attempt must be retained before candidate validation, including raw
output, response identifier where available, usage, and validation failure.
Extraction history must remain available when a prompt, model, or candidate
schema changes.

### 7.6 EventCandidate

Represents one provisional event extracted from one source representation
before canonicalization. An extraction may produce zero, one, or several
candidates.

Initial fields:

- `id`
- `extraction_run_id`
- `source_representation_id`
- `candidate_index`
- `schema_version`
- `payload`
- `title`
- `overall_confidence`
- `validation_status`
- `validation_errors`
- `created_at`

`payload` retains the complete schema-validated candidate, including proposed
occurrences, organizers, registrations, locations, classifications, evidence,
and ambiguities. Key fields may be duplicated into indexed columns only when a
demonstrated query or review need exists.

A candidate is not a public event. It may create at most one canonical event;
the unique candidate link in `EventProvenance` provides initial
canonicalization idempotency. Reprocessing an already accepted candidate must
not create another event.

### 7.7 Organizer

Represents an organization associated with an event.

Possible fields:

- `id`
- `name`
- `normalized_name`
- `organization_type`
- `school_or_unit`
- `website_url`
- `social_urls`
- `is_official`
- `created_at`
- `updated_at`

Organizer aliases may be introduced if naming inconsistency becomes significant.

`organization_type` uses this initial editable vocabulary:

- `NTU_CENTRAL_UNIT`
- `NTU_SCHOOL_COLLEGE`
- `NTU_RESEARCH_CENTRE_INSTITUTE`
- `NTU_STUDENT_ORGANISATION`
- `NTU_RESIDENTIAL_HALL`
- `EXTERNAL_COMPANY`
- `GOVERNMENT_PUBLIC_AGENCY`
- `NONPROFIT_COMMUNITY`
- `INDIVIDUAL_INFORMAL`
- `OTHER`

This facet describes what the organizer is, not the event's topic, format, or
purpose. Unknown values remain null or require review rather than being guessed.

### 7.8 Event

Represents the canonical conceptual event.

Possible fields:

- `id`
- `slug`
- `title`
- `normalized_title`
- `description`
- `series_id`
- `publication_status`
- `verification_status`
- `image_reference`
- `created_at`
- `updated_at`
- `last_verified_at`
- `archived_at`

An event is the canonical conceptual activity. It does not own occurrence
times, occurrence venues, or copied registration fields. Organizers,
formats, topics, purposes, audiences, organizers, and sources are plural
relationships implemented through association tables rather than singular
foreign keys. Every initially created event is non-public and begins in `draft`
or `review_required`.

### 7.9 EventSeries

Groups related events. A series never directly groups occurrences.

Initial fields:

- `id`
- `title`
- `description`
- `created_at`
- `updated_at`

Series membership is optional. A repeated activity that can be attended or
registered for independently should normally be represented as separate events
in a series. A single event with several required or continuous attendance
blocks instead has several occurrences.

### 7.10 EventOccurrence

Represents one continuous, independently meaningful physical attendance block
within an event.

Initial fields:

- `id`
- `event_id`
- `label`
- `sequence`
- `start_date`
- `start_time`
- `end_date`
- `end_time`
- `time_precision`
- `is_all_day`
- `raw_location_text`
- `occurrence_status`
- `capacity_status`
- `created_at`
- `updated_at`

All dates and times are interpreted as Singapore local time. The initial domain
does not store a per-occurrence timezone or perform general timezone
conversion. Explicit non-Singapore times are unsupported or held for review
rather than silently reinterpreted.

An `exact` occurrence requires a start time. A `date_only` occurrence cannot
contain start or end times. These rules are enforced both in the candidate
contract and in canonical database constraints.

Midnight and calendar-date changes do not split an occurrence. A continuous
overnight activity remains one occurrence with different start and end dates.
Create separate occurrences when the source identifies separate days,
sessions, slots, or stages; when attendance resumes after a meaningful break;
when blocks are independently attendable; or when registration is separate.
Separate registration is sufficient but not necessary for a split.

Short breaks, meals, check-in, ordinary program transitions, or continuous
movement between venues do not by themselves create new occurrences. The
domain has no agenda-item concept. Source details that do not qualify as
occurrences remain in descriptions or raw source material.

A date range without evidence of internal separation remains one approximate
occurrence spanning that range. Daily opening hours create separate
occurrences. Parallel, independently useful sessions may be separate
occurrences. An occurrence may resolve to multiple venues through an
`OccurrenceVenue` association, with at most one marked primary.

### 7.11 Registration

Represents one registration option owned by exactly one series, event, or
occurrence.

Initial fields:

- `id`
- exactly one of `series_id`, `event_id`, or `occurrence_id`
- `name`
- `registration_type`
- `url`
- `opens_date`
- `opens_time`
- `closes_date`
- `closes_time`
- `time_precision`
- `instructions`
- `status`
- `created_at`
- `updated_at`

A database constraint must require exactly one owner. Multiple registration
objects at the same scope are allowed, such as separate attendee, volunteer,
and competition registrations.

Effective registration is resolved from the closest scope: occurrence,
otherwise event, otherwise series. A registration at a closer scope initially
replaces inherited registrations rather than supplementing them. Child records
do not copy or point back to an ancestor's registration.

### 7.12 EventProvenance

Links a canonical event to the candidate and source representation that support
it.

Initial fields:

- `id`
- `event_id`
- `event_candidate_id`
- `source_representation_id`
- `is_primary_source`
- `created_at`

`event_candidate_id` is unique in the initial create-only workflow: one
candidate creates at most one event. One event may eventually have several
provenance records after cross-source matching is introduced. Field-level
provenance may be added when canonical updates and conflict resolution are
implemented.

### 7.13 Building

Represents a campus building or outdoor map location.

Possible fields:

- `id`
- `name`
- `code`
- `normalized_name`
- `map_point`
- `address`
- `postal_code`
- `campus_area`
- `official_map_identifier`
- `official_map_url`
- `source_url`
- `verified_at`
- `is_active`

`map_point` should use a PostGIS point type.

The initial mapped scope is NTU's main Yunnan Garden campus, including
residential halls, plus adjacent NIE. Novena and off-campus locations may be
retained in source data but are outside the initial map. Seed all official
buildings and major landmarks at building level. The initial campus-area
vocabulary is `MAIN`, `NIE`, `NOVENA`, and `OFF_CAMPUS`; only `MAIN` and `NIE`
are initially map-eligible.

The initial data migration seeds a reviewed core list of NTU/NIE buildings,
halls, and landmarks plus a building-level venue for each. A map point remains
null until coordinates can be imported from an authoritative source under
appropriate access and usage terms; coordinates must never be guessed merely
to satisfy the schema.

### 7.14 Venue

Represents a room, lecture theatre, area, or physical venue associated with a building.

Possible fields:

- `id`
- `building_id`
- `name`
- `normalized_name`
- `floor`
- `room_code`
- `venue_type`
- `capacity`
- `map_point`
- `indoor_map_identifier`
- `source_url`
- `verified_at`
- `is_verified`

For the MVP, a venue normally inherits its building map point. Outdoor or
otherwise independently mapped venues may have their own point and a null
`building_id`. Rooms and spaces are added when encountered in production
sources and validated against authoritative directories rather than importing
every bookable room in advance.

### 7.15 VenueAlias

Maps inconsistent raw location strings to canonical venues.

Possible fields:

- `id`
- `venue_id`
- `alias`
- `normalized_alias`
- `match_type`
- `confidence`
- `is_verified`

Aliases are evidence-backed lookup aids, not replacements for raw location
text. Common forms include campus abbreviations such as `NS`/North Spine,
`SS`/South Spine, `ABS`/Gaia, `LHS`/The Hive, and `LHN`/The Arc, plus spacing
variants such as `LT 7`/`LT7` and `TR + 12`/`TR+12`.

Canonical venue data uses this source priority:

1. current NTU Maps and official campus pages for buildings and landmarks;
2. NTU Facilities Booking for room codes, names, and capacities;
3. official school, hall, and sports-facility pages for specialist spaces;
4. Singapore Land Authority OneMap for addresses and coordinates, subject to
   its authentication, attribution, and usage requirements;
5. observed source strings only as alias candidates after validation.

An extracted `raw_location_text` must never automatically create or modify a
canonical building, venue, or verified alias. Older campus maps may support
manual cross-checking but are not authoritative when current sources disagree.

### 7.16 Event classification facets

Event classification is multi-faceted. Format, topic, purpose, and audience are
separate plural relationships on `Event`, each implemented through a reference
model and association table. Multiple values are allowed because one event can,
for example, combine a fair, workshop, and networking session. Classifications
remain nullable and reviewable; extraction must preserve supporting source
evidence and must not invent a value.

#### 7.16.1 Format

Describes how the event is delivered:

- `TALK_SEMINAR`
- `WORKSHOP_CLASS`
- `CONFERENCE`
- `COMPETITION_HACKATHON`
- `FAIR_EXHIBITION`
- `NETWORKING_MEETUP`
- `PERFORMANCE`
- `CEREMONY`
- `SOCIAL_GATHERING`
- `SPORTS_RECREATION`
- `SERVICE_ACTIVITY`
- `TOUR_OPEN_HOUSE`
- `INFORMATION_SESSION`
- `OTHER`

#### 7.16.2 Topic

Describes what the event is about:

- `COMPUTING_TECHNOLOGY`
- `SCIENCE_ENGINEERING`
- `BUSINESS_FINANCE`
- `ARTS_CULTURE`
- `SOCIAL_SCIENCES_HUMANITIES`
- `HEALTH_WELLBEING`
- `SPORTS_RECREATION`
- `SUSTAINABILITY_ENVIRONMENT`
- `COMMUNITY_STUDENT_LIFE`
- `INTERNATIONAL_EXCHANGE`
- `OTHER`

Fine-grained concepts such as artificial intelligence or cybersecurity remain
free tags or keywords until usage demonstrates a stable controlled vocabulary.

#### 7.16.3 Purpose

Describes why a person would attend:

- `LEARNING_RESEARCH`
- `CAREER_RECRUITMENT`
- `NETWORKING_COMMUNITY`
- `COMPETITION_ACHIEVEMENT`
- `SERVICE_VOLUNTEERING`
- `SOCIAL_RECREATION`
- `ORIENTATION_OUTREACH`
- `SHOWCASE_CELEBRATION`
- `INFORMATION_SUPPORT`
- `OTHER`

Career and admissions concepts belong here rather than being conflated with
topic or format.

#### 7.16.4 Audience

Describes who the event is intended for:

- `ALL_CURRENT_STUDENTS`
- `UNDERGRADUATES`
- `POSTGRADUATES`
- `STAFF_FACULTY`
- `ALUMNI`
- `PROSPECTIVE_STUDENTS`
- `INDUSTRY_ACADEMIC_PARTNERS`
- `PUBLIC`
- `RESTRICTED_NTU_COMMUNITY`
- `OTHER`

Specific hall, school, year, programme, or cohort restrictions remain in
`audience_notes` and source evidence instead of expanding the controlled
vocabulary for every local group.

These initial vocabularies are deliberately editable. They are grounded in
representative Telegram and NTU event samples, NTU's public separation of event
types, interests, and audiences, comparison with another university event
directory, and the broader Schema.org event hierarchy. Source taxonomies are
mapped into these facets rather than copied directly.

Research references:

- [NTU Events](https://www.ntu.edu.sg/events?categories=networking)
- [NUS Events](https://myaces.nus.edu.sg/CoE/jsp/leftmenu.jsp)
- [Schema.org Event](https://schema.org/Event)
- [NTU Facilities Booking locations](https://wis.ntu.edu.sg/pls/webexe88/FBSDOCU.FBSLOCATN)
- [NTU campus overview and map entry point](https://www.ntu.edu.sg/orientation/explore-our-campus)
- [Singapore Land Authority OneMap API](https://www.onemap.gov.sg/apidocs/)

### 7.17 EventRevision

Records meaningful changes to canonical event information.

Possible fields:

- `id`
- `event_id`
- `changed_at`
- `change_type`
- `before_data`
- `after_data`
- `reason`
- `source_record_id`
- `changed_by_type`
- `changed_by_identifier`

This provides auditability for event updates, cancellations, and manual
corrections. `EventRevision` behavior is deferred until canonical updates are
introduced; the first pipeline is create-only.

---

## 8. Event Status Model

At minimum, the system should distinguish:

### Publication status

- `DRAFT`
- `PENDING_REVIEW`
- `PUBLISHED`
- `WITHHELD`
- `ARCHIVED`

### Occurrence status

- `SCHEDULED`
- `POSTPONED`
- `CANCELLED`
- `COMPLETED`

### Verification status

- `UNVERIFIED`
- `AUTOMATICALLY_VERIFIED`
- `MANUALLY_VERIFIED`
- `CONFLICTING`

These concepts should not be collapsed into one status field.

---

## 9. Source Adapter Architecture

Source-specific interpretation and provider-specific retrieval are separate
boundaries. The initial conceptual ports are:

```python
class SourceAdapter(Protocol):
    async def discover(
        self, source: Source, context: RetrievalContext
    ) -> list[RetrievalRequest]:
        ...

    def to_raw_documents(
        self, attempt: RetrievalAttempt
    ) -> list[RawDocumentPayload]:
        ...


class DirectRetriever(Protocol):
    async def retrieve(self, request: RetrievalRequest) -> RetrievalAttempt:
        ...


class ManagedRetriever(Protocol):
    async def start(self, request: ManagedRetrievalRequest) -> ManagedJobReference:
        ...

    async def resume(self, job: ManagedJobReference) -> ManagedJobState:
        ...

    async def collect(self, job: ManagedJobReference) -> RetrievalAttempt:
        ...


class BrowserExplorer(Protocol):
    async def explore(
        self, request: BrowserRetrievalRequest, policy: BrowserSafetyPolicy
    ) -> BrowserRetrievalAttempt:
        ...


class EventExtractor(Protocol):
    async def extract(self, input: ExtractionInput) -> ExtractionAttempt:
        ...
```

`SourceAdapter` knows a source's discovery and raw-document mapping rules.
`DirectRetriever` covers ordinary HTTP, APIs, feeds, and file downloads.
`ManagedRetriever` preserves the asynchronous job lifecycle of services such as
managed scraping platforms. `BrowserExplorer` performs bounded, read-only
interactive retrieval and returns captured artifacts plus its action trace.
`EventExtractor` accepts source-neutral inputs and returns raw provider output,
validated candidate payloads, model/prompt/schema versions, usage, and
failures.

The workflow, not these ports or their provider adapters, owns persistence,
timeouts, retry policy, concurrency, idempotency, validation sequencing, and
canonical decisions. Attempt results expose provider identifiers, timestamps,
status, errors, usage, and trace or artifact references without leaking
provider SDK objects into domain models.

Do not collapse these ports into one universal fetcher: direct requests,
managed jobs, and interactive browser sessions have meaningfully different
lifecycles. Conversely, do not create a different core document model for each
provider. Raw documents can retain text, structured data, bytes or media
references, screenshots, and traces without assuming HTML.

Retrieval implementations may include:

- Static HTML adapters
- Structured feed adapters
- Official API and export adapters
- Managed scraping or browser-automation provider adapters
- LLM-directed browser agents
- Source-specific page adapters
- Future authenticated connectors

Prefer small source configuration around shared retrieval and candidate-processing workflows. Use deterministic mapping for reliable structured inputs and LLM-first interpretation for unstructured inputs. Add dedicated page parsers only when measured reliability or cost justifies them.

Third-party retrieval services are replaceable infrastructure behind adapter interfaces. For each run, preserve enough provider response data and metadata to audit and reprocess it, including the source URL, retrieval method, provider and tool identifier, run identifier where available, timestamps, configuration or version, and failures. Treat provider output as untrusted input. Provider credentials remain outside source records, and providers must not own canonicalization, deduplication, manual-review, or publication decisions.

The existing Telethon and OpenAI research implementations inform future
adapters but do not define these core contracts and need not be rewritten
during repository scaffolding.

Production pipeline implementations are selected by a stable `pipeline_key`.
An explicit static in-process catalog maps those keys to lightweight pipeline
instances implementing option normalization, execution, and cleanup. Pipeline
constructors perform no network or authentication work. The executing worker
initializes provider resources lazily, reuses them across compatible jobs, and
closes them on shutdown. Enqueueing consults the same catalog only for support
checks and pipeline-specific option normalization. Unsupported queued keys fail
that job without terminating the sustained worker. The catalog is not a dynamic
plugin loader, inheritance hierarchy, or general dependency-injection container.

The first production-path implementation ingests public Telegram broadcast
channels through the owner's saved, ignored Telethon session. One registered
`Source` represents one channel and one `SourceRepresentation` represents one
message. `gpt-5-nano` screens up to 20 messages per request for high-recall
`EVENT`, `UNCERTAIN`, or `NOT_EVENT` decisions. `EVENT` and `UNCERTAIN` messages
are passed to `gpt-5-mini` in batches of up to five for strict candidate
extraction. Both stages share a limit of ten concurrent OpenAI requests and use
minimal reasoning effort and low output verbosity.

Model-facing publication timestamps are converted to Singapore local time
before resolving relative expressions such as “today” and “tomorrow”. The
incremental cursor advances to the newest fetched Telegram message even when
that message is filtered out as media-only. Cached screening or extraction is
reused only when the content and applicable model, prompt, schema, and extractor
versions still match.

Provider-facing structured-output schemas must stay within OpenAI's supported
JSON Schema subset. Candidate URL fields are exposed to the model as plain
strings because the `uri` string format is unsupported; deterministic Pydantic
validation still requires valid HTTP(S) URLs before a candidate is accepted.

Full message content is retained immutably for relevant, uncertain, and failed
processing cases. Confirmed non-event content is discarded after screening;
its source/message identity, content hash, model/prompt/schema version, decision,
confidence, and short reason remain in PostgreSQL. Representative rejected
messages remain in versioned evaluation fixtures so screening false negatives
can be reviewed without permanently archiving every fetched message.

### 9.1 Agentic browser retrieval

When direct fetch is insufficient, an LLM may open allowlisted URLs, inspect text, controls, DOM/accessibility summaries and screenshots, click navigation or content-reveal controls, scroll, wait, go back, and capture content.

Every run must:

- Restrict domains, actions, steps, time, tokens, retries, and depth.
- Prohibit authentication, registration, submissions, uploads, purchases, CAPTCHA bypass, and other external state changes.
- Treat page content as untrusted; retain URLs, observations, actions, timestamps, model/prompt versions, outputs, and failures.
- On ambiguity, stop for review. The agent may collect documents but never canonicalize, deduplicate, correct, or publish events.

Test each workflow with saved fixtures, traces, or controlled browser scenarios.

---

## 10. Raw Source Processing

Before deterministic mapping or language-model extraction, raw source material may need preprocessing.

Possible steps include:

- Removing navigation and boilerplate
- Selecting relevant DOM sections
- Extracting visible text
- Extracting metadata
- Resolving relative URLs
- Detecting image-based posters
- Normalizing whitespace
- Detecting content language
- Separating multiple event items on one page

Preprocessing should be deterministic where possible.

When an LLM is used, it should receive focused event-relevant content rather than an entire unfiltered payload or webpage.

---

## 11. Candidate Interpretation and Extraction

The interpretation layer converts preserved source observations into strict structured output. Reliable structured fields may be mapped deterministically. Unstructured or ambiguous content should use LLM-first extraction, with stable source metadata supplied as supporting evidence. Dedicated page parsing requires measured justification.

Conceptual output:

```json
{
  "events": [
    {
      "title": "Example Event",
      "description": "Short source-grounded description",
      "occurrences": [
        {
          "label": null,
          "start_date": "2026-08-15",
          "start_time": "14:00",
          "end_date": "2026-08-15",
          "end_time": "16:00",
          "time_precision": "exact",
          "raw_location": "LT19A, North Spine"
        }
      ],
      "organizers": ["Example NTU Society"],
      "registrations": [
        {
          "scope": "event",
          "url": "https://example.com/register",
          "closes_at": null
        }
      ],
      "formats": ["TALK_SEMINAR"],
      "topics": ["COMPUTING_TECHNOLOGY"],
      "purposes": ["LEARNING_RESEARCH"],
      "audiences": ["UNDERGRADUATES"],
      "overall_confidence": 0.94,
      "evidence": ["15 August, 2 PM to 4 PM at LT19A"],
      "ambiguities": []
    }
  ]
}
```

Requirements:

- Structured output only
- Explicit nulls for missing values
- No invented dates or venues
- Source-grounded descriptions
- Field-level confidence or uncertainty
- Explicit ambiguity reporting
- Versioned prompts and schemas
- Retained raw model output for valid and invalid attempts
- Retry limits
- Cost and token tracking where available

The exact model and retrieval providers should remain replaceable.

---

## 12. Deterministic Candidate Validation

After extraction, candidates must pass deterministic checks.

Examples:

- Title is present and non-empty.
- At least one occurrence has a usable start date.
- Supplied dates and times are valid or explicitly approximate.
- End date and time are later than the start when both are provided.
- Unqualified times are interpreted as Singapore local time.
- Explicit non-Singapore times are held for review.
- The event is physical or hybrid with a physical venue.
- The venue is present or explicitly unresolved.
- Registration and source URLs are syntactically valid.
- Dates are not inferred from unrelated page content.
- An event does not appear to be only a deadline or announcement.
- Excessively old source items are not republished as current events.

Validation errors should be stored and visible in the admin interface.

---

## 13. Venue Resolution

Venue resolution is a core subsystem.

### 13.1 Resolution order

A practical resolution sequence is:

1. Exact canonical venue match
2. Exact verified alias match
3. Parsed building and room match
4. Fuzzy alias match above a strict threshold
5. AI-assisted suggestion
6. Manual review

Only verified or high-confidence mappings should be applied automatically.

### 13.2 Normalization examples

The following may all refer to the same venue:

- `LT19A`
- `NS LT19A`
- `North Spine LT19A`
- `Lecture Theatre 19A`

Normalization should handle:

- Case
- Punctuation
- Spacing
- Building abbreviations
- Room prefixes
- Floor labels
- Common spelling variants

### 13.3 Map behavior

For indoor rooms:

- The event occurrence references the canonical room.
- The room references a building.
- The public map uses the building’s geographic point.
- The event details show the exact room and floor.
- An indoor-map link may be shown when available.

An unresolved venue should remain unresolved rather than being assigned to a guessed building.

---

## 14. Duplicate Detection

Cross-source duplicate detection is deferred from the first create-only
pipeline. Initially, a valid candidate may create at most one canonical event,
and repeated processing of that accepted candidate reuses its canonical link.
Candidates from different source representations are not automatically merged.

When introduced, duplicate detection should combine deterministic and
similarity-based signals.

Relevant signals include:

- Exact or similar registration URL
- Exact external source identifier
- Normalized title similarity
- Organizer match
- Start-time proximity
- Venue match
- Description similarity
- Image or poster similarity when introduced

### 14.1 Duplicate outcomes

A candidate may be classified as:

- New event
- New occurrence of an existing event
- Additional source for an existing event
- Update to an existing source record
- Possible duplicate requiring review
- Irrelevant or invalid item

### 14.2 Merge behavior

Merging should:

- Preserve all source links
- Preserve source timestamps
- Select a primary source
- Avoid discarding conflicting information
- Record the merge decision
- Allow reversal through admin tooling

Deduplication thresholds should be configurable and tested using labeled examples.

---

## 15. Canonical Event Update Logic

The first canonicalization workflow only creates events. It never changes an
existing canonical event. A successful create atomically persists the event,
occurrences, registrations, relationships, and provenance. A partial failure
must roll back the whole canonicalization transaction.

Content-change processing, corrections, postponements, cancellations,
conflicting-source resolution, and automatic canonical updates are deferred.
When update behavior is introduced, the system should determine whether a
change represents:

- A textual correction
- A date or time change
- A venue change
- A registration-link change
- A postponement
- A cancellation
- A new occurrence
- A completely different event replacing the source content

Important changes should create an `EventRevision`.

Source priority may be considered, but source priority must not blindly overwrite newer or more explicit information.

Conflicting high-value fields should trigger review.

---

## 16. Publication Decision

The first pipeline does not publish automatically. Every newly created
canonical event begins as `DRAFT` or `PENDING_REVIEW`, even when extraction
confidence is high. Persistence proves the internal workflow; it does not make
model output visible to users.

A schema-valid candidate may be retained without creating an event. Initial
automatic creation requires:

- A valid, non-empty title.
- At least one usable occurrence start date.
- A known source representation and retained provenance.
- Qualification under the physical-event definition.
- Successful deterministic candidate validation.

An unresolved venue does not prevent draft creation but requires review. An
invalid, irrelevant, online-only, or date-less candidate is retained with its
validation outcome and does not create a canonical event. Public-release and
automatic-publication rules will be decided using reviewed production evidence.

---

## 17. Public API

The public API should be versioned.

Suggested base path:

```text
/api/v1/
```

### 17.1 Event list endpoint

```text
GET /api/v1/events
```

Possible query parameters:

- `q`
- `start_after`
- `start_before`
- `time_start`
- `time_end`
- `category`
- `audience`
- `building`
- `campus_area`
- `bbox`
- `page`
- `page_size`
- `ordering`

The endpoint should return only published events and public fields.

### 17.2 Event detail endpoint

```text
GET /api/v1/events/{slug-or-id}
```

Returns:

- Canonical event details
- Occurrence details
- Venue details
- Organizer
- Categories
- Source links
- Last verified time
- Relevant publication metadata

### 17.3 Map endpoint

A dedicated map endpoint may be introduced if map payload needs differ substantially from list payloads:

```text
GET /api/v1/map/events
```

Possible input:

- Bounding box
- Date range
- Active filters
- Zoom level

Possible output:

- Building point
- Event count
- Earliest upcoming event
- Minimal event summaries
- Cluster metadata

Do not create a separate endpoint unless the payload or query behavior justifies it.

### 17.4 Building endpoint

```text
GET /api/v1/buildings
GET /api/v1/buildings/{id}
```

Returns canonical location information and optionally upcoming event counts.

### 17.5 API conventions

The API should use:

- ISO 8601 timestamps
- Explicit Singapore time-zone handling
- Stable identifiers
- Pagination
- Consistent error responses
- OpenAPI documentation
- Read-only public event access initially

---

## 18. Frontend Rendering Responsibilities

Next.js should handle both server-rendered and client-rendered concerns.

### Server-rendered responsibilities

- Public event detail pages
- Initial event list data where appropriate
- Page metadata
- Search-engine-readable content
- Shareable event URLs
- Initial error and empty states

### Client-rendered responsibilities

- Interactive map
- Marker selection
- Map movement
- Map/list synchronization
- Filter controls
- Dynamic result updates
- Browser geolocation if introduced
- Future bookmark interactions

The map component should be isolated as a client component.

Search and filter state should be represented in URL query parameters so views are shareable and browser navigation works correctly.

---

## 19. Search Design

The initial search implementation should use PostgreSQL capabilities.

Supported methods may include:

- Full-text search
- Trigram similarity
- Indexed exact filters
- Date-range queries
- PostGIS bounding-box queries

Searchable fields should include:

- Event title
- Description
- Organizer
- Format, topic, and purpose
- Building
- Venue aliases

Natural-language search is deferred.

A dedicated search engine should only be introduced after PostgreSQL search is measured and shown to be insufficient.

---

## 20. Map Query Design

The frontend map should request events based on:

- Current visible bounds
- Date range
- Active format, topic, purpose, and audience filters
- Intended audience
- Time filters
- Search query

The API should avoid returning full event descriptions for every map point.

At low zoom levels:

- Results should be grouped by building or clustered.

At high zoom levels:

- Individual building markers may be shown.

Since the MVP uses building-level display, multiple events at one building should be grouped under one marker with a count and list.

PostGIS spatial indexes should support bounding-box queries.

---

## 21. Historical Archive

Past events should remain stored.

Public behavior may distinguish:

- Upcoming events
- Ongoing events
- Past events

Past events should not dominate default discovery results.

Archive support is useful for:

- Product history
- Deduplication
- Organizer history
- Source quality analysis
- Future recommendations
- Reprocessing and testing

Archived source records and raw documents should remain linked to their canonical events.

---

## 22. Background Jobs

The initial executor is a single Django worker process polling indexed queued-job
rows in PostgreSQL every two seconds. This is a project-specific ingestion queue,
not a general task framework. An `IngestionRequest` records one Admin, command,
or scheduled trigger and may group several jobs. Each `IngestionJob` belongs to
exactly one registered `Source` and records the resolved pipeline key; selecting
several sources therefore creates several independently retryable jobs under one
request. The source's adapter key selects a supported pipeline when enqueueing,
while the job retains that execution decision. For Telegram, the worker is
intentionally deployed as one process so only one process owns the saved
Telethon session. Up to ten concurrent model calls are tasks inside that worker,
not additional queue workers.

Jobs are claimed with a short row-locking transaction, record a worker identity
and heartbeat, and persist stage results incrementally. Abandoned running jobs
are returned to the queue after a stale-heartbeat threshold; the idle polling
loop checks for newly stale jobs at least once per minute. The Admin action,
queued command, inline troubleshooting command, and external scheduler command
all invoke the same enqueue and workflow services. The scheduler remains an
external concern; it only needs to invoke the scheduled-enqueue command.

Initial background job types include:

- Crawl active sources
- Retry failed crawls
- Preprocess raw documents
- Extract event candidates
- Validate candidates
- Resolve venues
- Match duplicates
- Publish eligible events
- Check upcoming events for changes
- Mark completed occurrences
- Reprocess documents after extractor updates
- Generate source-health summaries

Jobs must be idempotent where practical.

A repeated job should not create duplicate records or corrupt canonical data.

Long-running work must not execute inside public HTTP request handlers.

---

## 23. Internal Administration Workflows

The initial admin interface should support:

### Event review

- View candidate and canonical event side by side
- Inspect original source
- Inspect extraction output
- Correct fields
- Publish, withhold, or archive
- View revision history

### Venue management

- Create buildings and rooms
- Add aliases
- Review unresolved locations
- Confirm or reject suggested matches
- Bulk-apply known aliases

### Duplicate management

- Review possible duplicates
- Merge records
- Select primary source
- Undo erroneous merges

### Source management

- Enable or disable sources
- Inspect crawl history
- View failure rates
- Trigger a manual crawl
- Update source configuration
- Review last successful fetch

### Extraction management

- View extractor version
- View prompt version
- Compare extraction attempts
- Re-run extraction
- Review validation errors

Custom admin pages should only be built when standard Django Admin behavior is insufficient.

---

## 24. Authentication and Permissions

Public browsing does not require authentication.

Initial authenticated roles may include:

- Superuser
- Administrator
- Reviewer

Permissions should separate:

- Viewing internal data
- Editing canonical events
- Publishing events
- Managing sources
- Managing venues
- Merging duplicates

Future public-user accounts should not share the same permission assumptions as internal staff accounts.

---

## 25. Security and Privacy

Initial security requirements include:

- Public APIs expose only intended fields.
- Admin routes require authentication.
- Source credentials, if any, are stored outside source records.
- User-provided URLs are validated.
- Raw source content is treated as untrusted input.
- HTML content is sanitized before display.
- Worker failures must not expose secrets in logs.
- Rate limiting may be added to public APIs if abuse appears.
- Crawler behavior must respect applicable access rules and source restrictions.

The MVP should not collect personal schedules, course data, or precise user locations.

If browser geolocation is added later, it should require explicit permission and should not be stored by default.

---

## 26. Error Handling

Errors should be classified by stage.

Example categories:

- Source unavailable
- Access denied
- Page structure changed
- Fetch timeout
- Invalid raw content
- Extraction failure
- Invalid structured output
- Venue unresolved
- Duplicate conflict
- Database failure
- Publication failure

Each failed processing item should retain:

- Error category
- Human-readable message
- Relevant identifiers
- Retryability
- Attempt count
- Last attempted time

One failed source or document should not stop processing unrelated sources.

---

## 27. Logging and Observability

Development should include structured logging from the beginning.

Logs should include identifiers such as:

- Source ID
- Crawl run ID
- Raw document ID
- Extraction run ID
- Candidate ID
- Event ID
- Job ID

Useful metrics include:

- Crawl success rate
- Crawl duration
- Documents discovered
- Extraction success rate
- Extraction latency
- Validation failure rate
- Venue-resolution success rate
- Duplicate-match rate
- Auto-publication rate
- Review queue size
- Source freshness

The initial implementation does not require a particular monitoring vendor.

---

## 28. Testing Strategy

### 28.1 Backend unit tests

Test:

- Validation rules
- Normalization
- Publication decisions
- Venue matching
- Duplicate scoring
- Event update behavior
- Search filters

### 28.2 Source adapter tests

Each adapter should use saved fixtures.

Tests should verify:

- Item discovery
- Content extraction
- Relative URL handling
- Behavior when page structure is partially missing
- Detection of unchanged content

Tests should not depend entirely on live sources.

### 28.3 Extraction tests

Maintain a labeled dataset of source samples and expected structured outputs.

Evaluate:

- Title accuracy
- Date accuracy
- Time accuracy
- Venue accuracy
- Organizer accuracy
- False event extraction
- Missing-event extraction

LLM tests should use stored outputs or controlled mocks for ordinary automated test runs.

### 28.4 API tests

Test:

- Filtering
- Pagination
- Bounding-box queries
- Publication visibility
- Error responses
- Event detail retrieval

### 28.5 Integration tests

Use a real PostgreSQL/PostGIS test instance for:

- Spatial fields
- Spatial indexes
- Database constraints
- Full-text search
- Transactions
- Migrations

### 28.6 Frontend tests

Test:

- Filter behavior
- URL synchronization
- Event-card rendering
- Empty and error states
- Map/list synchronization
- Event detail rendering

### 28.7 End-to-end tests

Critical flows include:

- Open map
- Select date range
- Filter by category
- Select building marker
- Open event detail
- Follow source or registration link

---

## 29. Data Seeding and Fixtures

Development should include:

- Canonical NTU building fixtures
- Initial venue aliases
- Example organizers
- Example classification reference values
- Representative event records
- Saved source fixtures in representative formats such as HTML, JSON, feed records, text, or provider results
- Example extraction outputs
- Duplicate-event test cases

Building and venue data should be reviewable and version-controlled where licensing permits.

---

## 30. Time Handling

Event scheduling uses separate Singapore-local date and time fields. The
initial event domain has no configurable timezone and performs no general
timezone conversion. Operational timestamps such as `created_at`, `fetched_at`,
and `processed_at` remain timezone-aware audit timestamps.

Rules:

- Unqualified event-source dates and times are interpreted as Singapore local time.
- Explicit non-Singapore event times are unsupported or held for review.
- API schedule values expose ISO dates and local times rather than implying UTC.
- API and database audit timestamps retain timezone information.
- Date-only source information should not be silently converted into a precise time.
- Ambiguous date formats should trigger review.
- Repeated independently attendable activities are modeled as events in a
  series rather than expanded from an implicit recurrence rule.

---

## 31. API Contract Management

Django REST Framework uses `drf-spectacular` to generate an OpenAPI 3 schema
for versioned endpoints under `/api/v1/`. The generated schema is committed at
`packages/api-client/openapi.json`.

`openapi-typescript` generates the committed
`packages/api-client/src/generated/schema.d.ts` contract from that schema.
`openapi-fetch` provides the small runtime Fetch client. Handwritten code
outside `src/generated/` owns client construction, base-URL selection,
middleware, and any application-specific error normalization.

The shared package exposes a client factory that accepts its base URL and
optional Fetch implementation. It must not read a `NEXT_PUBLIC_*` environment
variable internally because Next.js server and browser callers may require
different configuration. Endpoint-specific wrappers are added only when they
provide reusable application behavior; the package must not recreate a
handwritten SDK around every typed endpoint.

Generated files must never be manually edited. A root generation command
regenerates both the OpenAPI schema and TypeScript contract. CI runs the
generator or `openapi-typescript --check`, TypeScript type checking with
`noUncheckedIndexedAccess`, and a clean-diff check so stale committed artifacts
fail verification.

API changes should follow:

- Versioned endpoints
- Backward-compatible additions where possible
- Explicit deprecation
- Stable response shapes
- Integration tests between frontend and backend

Shared TypeScript and Python source files should not be used as a substitute for an API contract.

Focused DRF tests cover endpoint behavior from the first API slice.
Schema-driven fuzzing with Schemathesis, breaking-change comparison with
`oasdiff`, generated React Query hooks, and broad handwritten endpoint wrappers
are deferred until demonstrated API or frontend needs justify them.

---

## 32. Development Workflow

Recommended practices:

- Use database migrations for every schema change.
- Do not edit production-like data manually outside supported admin or migration workflows.
- Keep source adapters small and source-specific.
- Keep business logic out of Django views.
- Use application services for ingestion, matching, and publication workflows.
- Keep serializers focused on API representation and validation.
- Version extraction prompts.
- Preserve reproducible fixtures for bugs.
- Add tests when fixing retrieval-agent or extraction failures.
- Use feature flags or configuration for incomplete sources.

### 32.1 Minimum automated checks

The Python toolchain uses:

- Ruff for formatting and linting;
- pytest with pytest-django for tests;
- `manage.py check` for Django system checks; and
- `makemigrations --check` to detect model changes without migrations.

The TypeScript toolchain uses:

- Prettier for formatting;
- ESLint for linting;
- `tsc --noEmit` for type checking, including
  `noUncheckedIndexedAccess`; and
- Vitest for unit and component tests.

Root `pnpm` scripts expose consistent `format`, `format:check`, `lint`,
`typecheck`, `test`, and aggregate `check` commands across the applicable
workspaces. CI runs the non-mutating checks, Django migration check, tests
against PostgreSQL/PostGIS where required, and the OpenAPI artifact drift
check. A Python static type checker and Django typing plugins are deferred
until demonstrated value justifies their configuration cost.

Example application service:

```python
class ProcessEventCandidateService:
    def execute(self, candidate_id: int) -> ProcessingResult:
        ...
```

This service may coordinate:

- Candidate validation
- Organizer normalization
- Venue resolution
- Duplicate matching
- Canonical event update
- Publication decision

---

## 33. Initial Development Phases

### Phase 1: Domain and data foundation

- Create Django project and modules
- Configure PostgreSQL/PostGIS
- Define event, occurrence, source, building, venue, and raw-document models
- Add Django Admin
- Seed core NTU buildings
- Define event status workflows

### Phase 2: First ingestion source

- Implement one NTU official source adapter
- Store raw documents
- Add source-appropriate deterministic mapping or LLM-first unstructured extraction
- Add direct, managed-provider, or constrained agentic browser retrieval as the source requires
- Preserve retrieval provenance and, where applicable, provider metadata, browser action traces, and model inputs and outputs
- Validate candidates
- Create canonical events
- Review results through admin

### Phase 3: Event API

- Implement event list and detail endpoints
- Add date, category, audience, and building filters
- Add keyword search
- Add map-bound queries
- Document API through OpenAPI

### Phase 4: Personal map-first frontend

- Build campus map
- Add synchronized event list
- Add markers grouped by building
- Add filter state in URL
- Add event detail pages
- Add source and registration redirects

### Phase 5: Data quality workflows

- Add venue aliases
- Add duplicate detection
- Add candidate review queue
- Add event revisions
- Add source-health tracking
- Add change detection

### Phase 6: Additional sources

- Add selected faculty and student organization sources
- Expand retrieval-agent and extraction fixtures
- Improve extraction evaluation
- Refine publication thresholds

### Phase 7: Public readiness and deployment

- Approve evidence thresholds and an invited, staged, or open rollout
- Verify security, privacy, accessibility, backups, recovery, monitoring, rate limits, and operational runbooks
- Configure hosting and secrets, then deploy only after owner approval

---

## 34. Explicitly Deferred Technical Features

The following should not block the MVP:

- Public user accounts
- Bookmarks
- Notifications
- Timetable integration
- Calendar synchronization
- Natural-language search
- Recommendation models
- Organizer portals
- Internal registration
- Payments
- Indoor room polygons
- Navigation routing
- Multi-campus support
- Private email ingestion
- Automatic source discovery
- Dedicated search infrastructure
- Distributed microservices
- Real-time event streaming

---

## 35. Open Technical Decisions

The following remain intentionally undecided:

- Exact map renderer and basemap provider
- LLM provider, retrieval providers, browser-agent runtime, and model/tool APIs
- Acceptable extraction accuracy, navigation success, latency, and cost
- Exact scheduler implementation
- Raw-content storage implementation beyond the storage abstraction
- Crawl frequency per source
- Rules for promoting free tags into new controlled classification values
- Auto-publication thresholds
- Duplicate scoring thresholds
- Social-platform access strategy
- Whether poster OCR is required in the first source set
- Exact public event identifier format
- Whether personal access is local-only or privately reachable from multiple devices
- Public-release evidence thresholds, observation period, and rollout type
- Exact production hosting and deployment topology

These should be decided using working prototypes and real source samples rather than abstract preference.

---

## 36. Initial Definition of Done

The first complete vertical slice is done when:

1. At least one approved NTU source can be crawled repeatedly.
2. Raw source content is preserved.
3. One or more event candidates are extracted.
4. Invalid candidates are rejected or held for review.
5. Valid candidates become canonical events.
6. A venue is resolved at building level.
7. The event appears through the versioned event API.
8. The local Next.js frontend displays it to the owner on the map and in the synchronized list.
9. The event detail page shows the precise source-provided room text.
10. The user can open the original source or registration page.
11. The internal admin can inspect and correct the event.
12. Automated tests cover the critical ingestion and retrieval path.

This vertical slice should be completed before expanding to many source types. It completes the first personal-use path; it does not by itself satisfy the public-readiness gate.
