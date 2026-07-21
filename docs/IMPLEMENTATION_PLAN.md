# NTU Events Implementation Plan

**Document status:** Active implementation plan  
**Current milestone:** 0 — Foundation decisions  
**Next delivery goal:** Ready-to-build personal-use vertical-slice foundation

## 1. Guiding Delivery Target

The first complete vertical slice will:

> Fetch one approved source, preserve its raw content, extract and review an event, resolve its venue, create one canonical event, expose it through the generated API client, and display it to the project owner in a minimal local map/list.

Re-running must not create duplicates or overwrite manual corrections. This is the first personal-use slice; public deployment follows sustained evidence of utility, coverage, and data quality.

## 2. Overall Milestones

| Milestone | Deliverable | Exit condition | Status |
| --- | --- | --- | --- |
| 0. Foundation decisions | First source, representative samples, initial identity/time/taxonomy/venue rules | Blocking domain assumptions are documented well enough to scaffold | In progress |
| 1. Repository scaffold | Backend, web, API-client package, local database and basic checks | Both applications start and automated checks run | Not started |
| 2. Domain foundation | Sources, raw documents, candidates, events, occurrences, venues and taxonomy | Initial migrations work and records are reviewable in Django Admin | Not started |
| 3. First-source ingestion | One LLM-first source workflow, constrained browser exploration where needed, raw storage, traces, fixtures and extraction contract | The source can be explored and processed repeatedly and its raw content and agent trace are retained | Not started |
| 4. Processing workflow | Extraction, validation, venue resolution, canonicalization and review | A valid candidate becomes one canonical event without duplication | Not started |
| 5. API contract | Event endpoints, core filters, OpenAPI schema and generated client | The web application retrieves typed event data through `packages/api-client` | Not started |
| 6. Personal discovery interface | Basic event list, map synchronization and event detail | The owner can discover the ingested event through the complete local product path | Not started |
| 7. Personal-use hardening | Reprocessing, manual overrides, failure handling and regression cases | Corrections survive reprocessing and failed inputs do not corrupt data during repeated owner use | Not started |
| 8. Controlled source expansion | Additional approved sources, including harder poster or social content | Coverage is useful to the owner and new adapters reuse the existing workflow without separate business rules | Not started |
| 9. Public-readiness gate | Evidence from personal use plus security, privacy, accessibility and operational review | The owner approves explicit quality thresholds, rollout scope and deployment readiness | Not started |
| 10. Public deployment | Production configuration, hosting, monitoring and staged release | The approved public audience can reliably access the product | Not started |

## 3. Immediate Next Goals

### Goal A — Select and understand the first source

- [ ] Select one accessible, approved NTU event source.
- [ ] Record why it is representative and how it may be accessed.
- [ ] Save an initial set of representative source items and grow it toward 50–100 samples.
- [ ] Include missing-field, changed, cancelled, multi-event and unusual-time cases where available.
- [ ] Identify the observations the LLM needs, any interactive exploration steps, and any stable metadata that can supplement LLM extraction.
- [ ] Define the approved domains and safe read-only browser actions for the source.

**Done when:** The source can drive concrete schema and extraction decisions without relying on imagined examples.

### Goal B — Record initial domain rules

- [ ] Define event, series, occurrence, source representation and source-update identity.
- [ ] Define the initial treatment of exact, date-only, all-day, multi-day and recurring times.
- [ ] Decide which fields belong to events and which belong to occurrences.
- [ ] Confirm plural relationships for organizers, categories, audiences, venues, sources and registration options where needed.
- [ ] Define initial category dimensions and filter meaning.
- [ ] Identify the initial building, venue and alias dataset.
- [ ] Record unresolved choices explicitly rather than hiding them in model assumptions.

**Done when:** The first migrations can be designed without known contradictions in identity, time, cardinality or taxonomy.

### Goal C — Prepare repository scaffolding decisions

- [ ] Select supported Python, Django, Node.js and Next.js versions.
- [ ] Select Python and JavaScript package-management tools.
- [ ] Confirm PostgreSQL/PostGIS local-development setup.
- [ ] Select the initial OpenAPI schema and TypeScript-client generation workflow.
- [ ] Define the minimum linting, formatting and test commands for both applications.
- [ ] Confirm environment-variable and local raw-storage conventions.
- [ ] Define provider-neutral interfaces for LLM extraction and constrained browser tools; defer the exact model provider until source evaluation.

**Done when:** Milestone 1 can be implemented without changing the agreed repository boundaries.

## 4. First Tasks After Milestone 0

When the foundation exit condition is satisfied, implement Milestone 1 in this order:

1. Create the `apps/backend`, `apps/web`, and `packages/api-client` workspaces.
2. Add PostgreSQL/PostGIS local services and environment examples.
3. Start minimal Django and Next.js applications with health checks.
4. Add baseline formatting, linting and test commands.
5. Expose a minimal OpenAPI schema and generate the first API-client package build.
6. Document reproducible local setup in the root README.

## 5. Progress Rules

- Keep one milestone active at a time.
- Complete the current vertical path before broadening source coverage or polishing the interface.
- Collect personal-use evidence before Milestone 9; local usability does not authorize public exposure.
- Add migrations, tests and representative fixtures with the behavior they support.
- Update this document when a milestone starts, completes or changes scope.
- Introduce abstractions only when the active vertical slice demonstrates the need.

## 6. Task Completion Standard

An implementation task is complete when:

- Its behavior is implemented and locally reproducible.
- Relevant automated tests pass.
- Schema changes include migrations.
- Ingestion behavior includes representative fixtures.
- API contract changes update OpenAPI and the generated API client.
- Material decisions or limitations are documented.

Time estimates are intentionally omitted until the first source and development environment reveal the actual workload.
