# NTU Events Implementation Plan

**Document status:** Active implementation plan
**Current milestone:** 6 — Personal discovery interface
**Next delivery goal:** Render published Events through the generated client in
a synchronized local list, map, and detail flow

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
| 4. Processing workflow          | A reviewable candidate can become canonical event data through a safe, repeatable workflow       | Complete    |
| 4A. Deduplication hardening     | Likely duplicates and revisions are identified and resolved using reviewable evidence            | Complete    |
| 5. API contract                 | The web application can retrieve typed event data through the generated client                   | Complete    |
| 6. Personal discovery interface | The owner can find the ingested event through a local map, list, and detail view                 | In progress |
| 7. Personal-use hardening       | Corrections, reruns, failures, and source changes are handled reliably                           | Not started |
| 8. Controlled source expansion  | Additional approved sources reuse the shared workflow                                            | Not started |
| 9. Public-readiness gate        | The owner approves evidence, quality, security, privacy, accessibility, and rollout readiness    | Not started |
| 10. Public deployment           | The approved audience can reliably access the product                                            | Not started |

## 3. Completed milestone: deduplication hardening

The implemented baseline includes a separate, globally serial canonicalization
worker; bounded candidate matching with stored evidence; structured ADD,
UPDATE, and LINK_ONLY plans; transactional application; stale-graph detection;
and immutable observations and Event revisions. Reclaimed ingestion jobs safely
replace an earlier failed screening result while retaining invocation history.
The technical specification is authoritative for this behavior.

The current matching weights and threshold are accepted for the owner-operated
slice using existing focused coverage. Additional fixture calibration is not an
API milestone prerequisite; revisit it when observed duplicate or false-match
behavior provides evidence for a change.

## 4. Completed milestone: API contract

The read-only API exposes published Event list and detail resources by numeric
identifier. It includes the occurrence, venue, organizer, classification,
registration, source-link, verification, and map data required by the discovery
interface. The list supports bounded search, date, classification, attendance,
building, map-bounds, ordering, and page-number queries. OpenAPI and the
TypeScript client are generated and verified from this contract.

Docker Compose publishes Django and PostgreSQL only on host loopback during the
owner-operated local phase.

## 5. Current milestone: personal discovery interface

The first web vertical slice now uses the generated client to render a map and
synchronized event list, URL-backed filters, and an Event detail route.
Online-only occurrences remain in the list without map markers unless a
physical-location filter is active.

The milestone remains in progress until the owner can exercise the complete
flow with a real published Event, including a reviewed physical venue on the
map and an online-only or unresolved-location occurrence in the list.

## 6. Progress and completion rules

- Keep one milestone active at a time.
- Complete the current vertical path before broadening coverage or polishing
  later interfaces.
- Make detailed decisions in the milestone that supplies real evidence for
  them.
- Add migrations, tests, and representative fixtures with the behavior they
  support.
- Update this plan only when milestone scope or status changes; record durable
  behavior or architecture only after it is implemented and verified.
- Complete a task only when its behavior is reproducible, relevant checks pass,
  schema changes have migrations, and material decisions or limitations are
  documented in the appropriate authoritative file.
