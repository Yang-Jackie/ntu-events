# NTU Events Architecture

**Document status:** Initial architecture direction  
**Related documents:** `TECHNICAL_SPECIFICATION.md`, `IMPLEMENTATION_PLAN.md`, `HIGH_LEVEL_TECHNICAL_NOTES.md`

## 1. Purpose

This document defines the intended repository boundaries and code ownership for the initial system. It is specific enough to guide project setup without fixing implementation details that should be decided through the first working source and vertical slice.

## 2. Repository Shape

The project uses a monorepo with separate backend, frontend, and shared-package workspaces.

```text
ntu-events/
├── apps/
│   ├── backend/                 # Django domain, API, admin, ingestion and workers
│   └── web/                     # Next.js discovery application; personal first, public later
├── packages/
│   └── api-client/              # Generated TypeScript API client
├── fixtures/                    # Shared, version-controlled test datasets
│   ├── sources/
│   ├── extraction/
│   ├── duplicates/
│   └── venues/
├── tests/
│   └── e2e/                     # Cross-application browser tests
├── docs/
├── scripts/
├── infra/                       # Local and deployment support
├── storage/                     # Local runtime raw content; ignored by Git
├── compose.yaml
├── .env.example
└── README.md
```

The repository may add root configuration files for the selected Python and JavaScript tooling. Their exact names and tools remain implementation decisions.

## 3. Application Boundaries

Personal-first delivery changes access, not architecture: the owner initially runs the complete system privately, and public deployment reuses it after a readiness gate.

### Backend

The Django backend owns:

- Canonical event and occurrence data
- Organizers, categories, audiences, buildings and venues
- Source registration and crawl history
- Ingestion and canonicalization workflows
- Publication and manual-review decisions
- Event API behavior for personal and later public access
- Internal administration

Background workers run separately when needed but use the backend's application services and models. They are not separate business services.

### Web

The Next.js application owns:

- Page rendering and discovery navigation
- Map, list and detail interfaces
- Search and filter interaction
- URL state and browser behavior
- Presentation-specific state

It must not duplicate canonical event rules, venue resolution, deduplication, or publication decisions.

### API client package

`packages/api-client` is retained as a separate workspace package from the beginning. It contains generated TypeScript types and request functions based on the backend's versioned OpenAPI schema.

```text
packages/api-client/
├── package.json
├── src/
│   ├── generated/              # Generated code; not manually edited
│   └── index.ts                # Stable exports for consumers
└── README.md
```

The package provides the contract boundary between Python and TypeScript. It must not contain copied backend business logic. The exact OpenAPI generator and publication/versioning process can be chosen during project setup.

## 4. Backend Organization

The backend is organized by domain or capability first, rather than by global `controllers`, `services`, and `repositories` directories.

```text
apps/backend/
├── manage.py
├── config/                     # Settings, root routing and runtime configuration
├── common/                     # Small, domain-neutral shared infrastructure
├── events/                     # Events, occurrences, categories and audiences
├── venues/                     # Buildings, venues, aliases and resolution
├── organizers/                 # Organizer records and relationships
├── sources/                    # Sources, crawl runs and raw-document metadata
├── ingestion/                  # Adapters, extraction and processing workflows
├── moderation/                 # Review, correction and merge workflows
└── search/                     # Public search and map-oriented queries
```

Each substantial domain may contain its own models, services, query logic, API layer, administration configuration, and tests. These internal folders should be introduced as the domain grows rather than created empty in advance.

A typical mature domain may resemble:

```text
events/
├── models/
├── services/
├── selectors/
├── api/
├── admin/
└── tests/
```

The exact split between files and folders should follow module size. Small Django applications may begin with conventional `models.py`, `admin.py`, and `tests.py` files.

### Controllers and API views

Django REST Framework views and viewsets perform the controller role. They translate HTTP requests and responses, invoke application services or selectors, and remain thin. Business workflows must not be implemented directly in views.

### Services

Services represent meaningful commands and workflows, especially operations spanning multiple models or domains. Expected examples include processing an event candidate, applying a manual correction, resolving a venue, publishing an event, and merging duplicates.

Simple model-local behavior does not require a service class. The project should avoid creating pass-through services that add no domain meaning.

### Query logic

Reusable or complex reads belong in custom querysets, managers, or selector functions. This includes public-event visibility, time-window filtering, map queries, and review-queue selection.

### Repositories

A repository layer is not required around ordinary Django ORM models. Django models, querysets and managers already provide the persistence boundary for relational data.

Repository-style interfaces are appropriate where the implementation genuinely varies, such as raw-content storage backed by the local filesystem in development and object storage later. They may also be introduced if a domain eventually needs to remain independent of Django persistence, but this is not an initial requirement.

## 5. `common` Boundary

`apps/backend/common` is limited to domain-neutral facilities used by several backend applications, such as:

- Timestamped or identifier base models
- Shared application exceptions
- Generic storage interfaces
- Common API error or pagination behavior
- Generic validation and test utilities

It must not become a general dumping ground. Logic using event, venue, organizer, source, extraction, or publication concepts belongs to the relevant domain or capability.

## 6. Ingestion Boundary

`ingestion` coordinates the conversion of source material into event candidates and canonical decisions.

Its expected internal capabilities are:

```text
ingestion/
├── adapters/                   # Small source-specific retrieval configuration and support
├── browser_agent/              # Constrained LLM-directed exploration and action traces
├── extraction/                 # LLM-first structured event extraction
├── validation/                 # Candidate schema and deterministic checks
├── matching/                   # Duplicate and venue-match analysis
└── workflows/                  # End-to-end application orchestration
```

Adapters and browser agents collect raw documents through allowlisted, read-oriented tools and retain action traces. The LLM owns semantic extraction; deterministic components own permissions, capture, validation, normalization, persistence, matching safeguards, and publication. Agents cannot canonicalize, publish, or silently correct data, and rigid source parsers require measured justification. Workers and commands must invoke shared ingestion workflows.

Whether every capability becomes a folder is left to implementation scale.

## 7. Fixtures and Runtime Data

Root `fixtures/` contains small, reviewed and version-controlled datasets shared by adapters or evaluation tooling:

- `sources/`: representative HTML, JSON, text or poster inputs
- `extraction/`: expected structured extraction results
- `duplicates/`: labeled identity and matching cases
- `venues/`: reviewed building, venue and alias seed data

Adapter-specific fixtures may instead live beside that adapter's tests. Ordinary tests should use saved or mocked model outputs rather than make live language-model calls.

`storage/` is different: it contains runtime raw documents during local personal use and is ignored by Git. A public deployment will use the same storage interface with a production implementation selected during the public-readiness phase.

## 8. Dependency Direction

The intended dependency flow is:

```text
Web application
      ↓
API client package
      ↓
Backend event API
      ↓
Application services and selectors
      ↓
Domain models, querysets and external interfaces
      ↓
Database and storage implementations
```

Within the backend:

- API views, admin actions, jobs and commands invoke shared application services.
- Domain code must not depend on API views, worker entry points, or frontend code.
- Source adapters must not own canonical-event or publication rules.
- Browser agents must not escape approved domains or perform authentication, submission, registration, purchase, CAPTCHA bypass, or other external state changes.
- Manual-review decisions must remain distinguishable from automated extraction results.
- Python and TypeScript do not share domain source files; they share the OpenAPI contract.

## 9. Deliberately Open Details

This architecture does not yet fix:

- Exact Python and JavaScript package-management tools
- Exact task queue and scheduler
- Exact OpenAPI client generator
- File-versus-folder layout inside small Django domains
- Raw-content storage provider beyond its interface
- Deployment topology
- Final event, occurrence, recurrence and taxonomy schemas

These choices should be made as the first source adapter and vertical slice reveal concrete requirements.
