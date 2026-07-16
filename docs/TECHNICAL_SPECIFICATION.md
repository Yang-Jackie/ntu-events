# NTU Map-Based Event Discovery Platform
## Technical Specification

**Document status:** Initial technical specification  
**Primary audience:** Project owner, contributors, reviewers, and AI coding assistants  
**Related document:** `BUSINESS_REQUIREMENTS.md`

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

Deployment providers, infrastructure pricing, and production hosting decisions are intentionally excluded unless they affect how the software must be designed.

---

## 2. Technical Goals

The system should:

1. Aggregate physical NTU event information from heterogeneous public sources.
2. Preserve raw source material for auditing and reprocessing.
3. Extract structured event data from unstructured content.
4. Normalize dates, organizers, categories, and NTU locations.
5. Detect duplicate representations of the same event.
6. Maintain one canonical representation of each event.
7. Support building-level geographic display and location-based queries.
8. Expose a stable API for the public frontend.
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

The normalized database is the canonical source for all public event information.

Crawlers and language models produce candidates. They do not directly determine the public event state.

### 3.3 Raw data must be preserved

The system must preserve enough source content to explain how a normalized event was produced.

Normalized event records must never be the only retained representation of a source.

### 3.4 Deterministic rules around probabilistic extraction

Language models may assist with extraction and classification, but publication decisions must also use deterministic validation rules.

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

### 4.1 Public web application

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
- Managing buildings, venues, aliases, organizers, categories, and sources

The admin interface is not part of the public product.

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

PostgreSQL with PostGIS is the primary database.

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
- Categories
- Publication decisions
- Revisions
- Crawl and processing state
- Future user interactions

### 4.6 Raw-content storage

Raw source content should be stored separately from normalized relational data.

During development, this may use a local filesystem abstraction. The code should use a storage interface so the implementation can later change without rewriting ingestion logic.

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

---

## 5. High-Level System Flow

```text
Registered source
      ↓
Scheduled crawl job
      ↓
Source-specific adapter
      ↓
Raw source document
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
Duplicate matching
      ↓
Canonical event create/update decision
      ↓
Publication decision
      ↓
Public API
      ↓
Next.js map and event interface
```

Every stage should produce an inspectable result or status.

---

## 6. Repository Structure

A monorepo is recommended.

```text
ntu-events/
├── apps/
│   ├── web/                     # Next.js public frontend
│   └── backend/                 # Django, DRF, admin, workers
├── docs/
│   ├── BUSINESS_REQUIREMENTS.md
│   └── TECHNICAL_SPECIFICATION.md
├── scripts/                     # Development and maintenance scripts
├── fixtures/                    # Saved source and parser test fixtures
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

### 7.3 RawSourceDocument

Represents a fetched page, post, item, or source payload before event extraction.

Possible fields:

- `id`
- `source_id`
- `crawl_run_id`
- `external_identifier`
- `source_url`
- `published_at`
- `fetched_at`
- `content_type`
- `storage_key`
- `content_hash`
- `language`
- `processing_status`
- `metadata`

A content hash should help avoid unnecessary reprocessing when content has not changed.

### 7.4 ExtractionRun

Represents one attempt to convert a raw document into structured event candidates.

Possible fields:

- `id`
- `raw_document_id`
- `extractor_type`
- `extractor_version`
- `model_name`
- `prompt_version`
- `started_at`
- `completed_at`
- `status`
- `input_storage_key`
- `output_storage_key`
- `error_message`

Extraction history should be retained so prompt or model changes can be evaluated.

### 7.5 EventCandidate

Represents structured information extracted from one source item before canonicalization.

Possible fields:

- `id`
- `raw_document_id`
- `extraction_run_id`
- `title`
- `description`
- `start_datetime`
- `end_datetime`
- `registration_deadline`
- `raw_location`
- `raw_organizer`
- `registration_url`
- `image_url`
- `category_predictions`
- `audience_predictions`
- `field_confidences`
- `overall_confidence`
- `validation_status`
- `validation_errors`
- `created_at`

Candidates are not automatically equivalent to public events.

### 7.6 Organizer

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

### 7.7 Event

Represents the canonical conceptual event.

Possible fields:

- `id`
- `slug`
- `title`
- `normalized_title`
- `description`
- `organizer_id`
- `publication_status`
- `verification_status`
- `primary_category_id`
- `intended_audience`
- `registration_url`
- `registration_deadline`
- `image_reference`
- `created_at`
- `updated_at`
- `last_verified_at`
- `archived_at`

The `Event` should not contain all timing and location details directly when an event may have multiple occurrences.

### 7.8 EventOccurrence

Represents one physical occurrence of an event.

Possible fields:

- `id`
- `event_id`
- `start_datetime`
- `end_datetime`
- `venue_id`
- `raw_location_text`
- `occurrence_status`
- `capacity_status`
- `created_at`
- `updated_at`

Most MVP events may have exactly one occurrence, but separating the model avoids future migration problems for multi-session or recurring events.

### 7.9 EventSourceRecord

Links a canonical event to one source representation.

Possible fields:

- `id`
- `event_id`
- `event_candidate_id`
- `source_id`
- `source_url`
- `external_identifier`
- `is_primary_source`
- `first_seen_at`
- `last_seen_at`
- `last_changed_at`
- `source_status`

One canonical event may have multiple source records.

### 7.10 Building

Represents a campus building or outdoor map location.

Possible fields:

- `id`
- `name`
- `code`
- `normalized_name`
- `map_point`
- `address`
- `campus_area`
- `indoor_map_url`
- `is_active`

`map_point` should use a PostGIS point type.

### 7.11 Venue

Represents a room, lecture theatre, area, or physical venue associated with a building.

Possible fields:

- `id`
- `building_id`
- `name`
- `normalized_name`
- `floor`
- `room_code`
- `venue_type`
- `indoor_map_identifier`
- `is_verified`

For the MVP, the map point normally comes from the building.

### 7.12 VenueAlias

Maps inconsistent raw location strings to canonical venues.

Possible fields:

- `id`
- `venue_id`
- `alias`
- `normalized_alias`
- `match_type`
- `confidence`
- `is_verified`

### 7.13 Category

Represents controlled event categories.

Possible categories include:

- Academic
- Technology
- Career
- Entrepreneurship
- Club and society
- Sports and recreation
- Arts and culture
- Volunteering
- Social
- Competition

The initial taxonomy should remain small and editable.

### 7.14 EventRevision

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

This provides auditability for event updates, cancellations, and manual corrections.

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

Each source type should implement a common adapter contract.

Conceptual interface:

```python
class SourceAdapter(Protocol):
    def fetch(self, source: Source, context: CrawlContext) -> FetchResult:
        ...

    def discover_documents(self, result: FetchResult) -> list[DiscoveredDocument]:
        ...

    def normalize_document(self, document: DiscoveredDocument) -> RawDocumentPayload:
        ...
```

An adapter is responsible for obtaining and isolating source items.

It is not responsible for:

- Creating canonical events
- Deciding publication state
- Resolving duplicates
- Silently correcting extracted information

Adapter implementations may include:

- Static HTML adapters
- Structured feed adapters
- Browser automation adapters
- Source-specific page adapters
- Future authenticated connectors

Each adapter should have saved fixtures and parser tests.

---

## 10. Raw Content Processing

Before language-model extraction, raw content may need preprocessing.

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

The LLM should receive focused event-relevant content rather than an entire unfiltered webpage.

---

## 11. Language-Model Extraction

The extraction layer should produce structured output validated against a strict schema.

Conceptual output:

```json
{
  "events": [
    {
      "title": "Example Event",
      "description": "Short source-grounded description",
      "start_datetime": "2026-08-15T14:00:00+08:00",
      "end_datetime": "2026-08-15T16:00:00+08:00",
      "raw_location": "LT19A, North Spine",
      "raw_organizer": "Example NTU Society",
      "registration_url": "https://example.com/register",
      "categories": ["Technology"],
      "audiences": ["Undergraduates"],
      "field_confidences": {
        "title": 0.99,
        "start_datetime": 0.94,
        "end_datetime": 0.70,
        "raw_location": 0.88
      },
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
- Retained raw model output
- Retry limits
- Cost and token tracking where available

The exact model provider should remain replaceable.

---

## 12. Deterministic Candidate Validation

After extraction, candidates must pass deterministic checks.

Examples:

- Title is present and non-empty.
- Start time is present.
- Start time is not invalid or impossible.
- End time is later than start time when provided.
- Time zone is normalized to Singapore time.
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

Duplicate detection should combine deterministic and similarity-based signals.

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

When a previously seen source changes, the system should determine whether the change represents:

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

A candidate or canonical event should only become public when minimum conditions are satisfied.

Suggested minimum publication conditions:

- A valid title exists.
- A valid start date and time exist.
- A physical location exists at least at building level.
- The source is known.
- The event qualifies under the physical-event definition.
- No unresolved high-severity conflict exists.
- Overall confidence exceeds a configurable threshold.

Suggested behavior:

- High-confidence, fully valid event: publish automatically.
- Valid event with minor missing fields: publish if core details are reliable.
- Unresolved location or date: pending review.
- Conflicting date, venue, or cancellation status: pending review.
- Invalid or irrelevant content: withhold.

The exact threshold should be adjusted using real extraction results rather than chosen arbitrarily.

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
- Category
- Building
- Venue aliases

Natural-language search is deferred.

A dedicated search engine should only be introduced after PostgreSQL search is measured and shown to be insufficient.

---

## 20. Map Query Design

The frontend map should request events based on:

- Current visible bounds
- Date range
- Active categories
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
- Example categories
- Representative event records
- Saved source HTML fixtures
- Example extraction outputs
- Duplicate-event test cases

Building and venue data should be reviewable and version-controlled where licensing permits.

---

## 30. Time Handling

All persisted timestamps should be timezone-aware.

Rules:

- Event source times are interpreted in Singapore time unless the source explicitly states otherwise.
- API timestamps use ISO 8601.
- Database timestamps retain timezone information.
- Date-only source information should not be silently converted into a precise time.
- Ambiguous date formats should trigger review.
- Recurring events should not be expanded until recurrence is explicitly supported.

---

## 31. API Contract Management

Django REST Framework should expose an OpenAPI schema.

The frontend should consume a generated or strongly typed API client where practical.

API changes should follow:

- Versioned endpoints
- Backward-compatible additions where possible
- Explicit deprecation
- Stable response shapes
- Integration tests between frontend and backend

Shared TypeScript and Python source files should not be used as a substitute for an API contract.

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
- Add tests when fixing parser or extraction failures.
- Use feature flags or configuration for incomplete sources.

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
- Add deterministic extraction where possible
- Add language-model extraction
- Validate candidates
- Create canonical events
- Review results through admin

### Phase 3: Public event API

- Implement event list and detail endpoints
- Add date, category, audience, and building filters
- Add keyword search
- Add map-bound queries
- Document API through OpenAPI

### Phase 4: Map-first frontend

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
- Expand parser fixtures
- Improve extraction evaluation
- Refine publication thresholds

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
- Exact language-model provider
- Exact task queue implementation
- Exact scheduler implementation
- Raw-content storage implementation beyond the storage abstraction
- Crawl frequency per source
- Exact category taxonomy
- Auto-publication thresholds
- Duplicate scoring thresholds
- Social-platform access strategy
- Whether poster OCR is required in the first source set
- Exact public event identifier format

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
7. The event appears through the public API.
8. The Next.js frontend displays it on the map and in the synchronized list.
9. The event detail page shows the precise source-provided room text.
10. The user can open the original source or registration page.
11. The internal admin can inspect and correct the event.
12. Automated tests cover the critical ingestion and retrieval path.

This vertical slice should be completed before expanding to many source types.
