# NTU Events Implementation Plan

**Document status:** Active implementation plan
**Current milestone:** 4A — Deduplication hardening
**Next delivery goal:** Validate matching against representative cases and
prove recovery paths before exposing canonical events through the API

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
| 4A. Deduplication hardening     | Likely duplicates and revisions are identified and resolved using reviewable evidence            | In progress |
| 5. API contract                 | The web application can retrieve typed event data through the generated client                   | Not started |
| 6. Personal discovery interface | The owner can find the ingested event through a local map, list, and detail view                 | Not started |
| 7. Personal-use hardening       | Corrections, reruns, failures, and source changes are handled reliably                           | Not started |
| 8. Controlled source expansion  | Additional approved sources reuse the shared workflow                                            | Not started |
| 9. Public-readiness gate        | The owner approves evidence, quality, security, privacy, accessibility, and rollout readiness    | Not started |
| 10. Public deployment           | The approved audience can reliably access the product                                            | Not started |

## 3. Current milestone: deduplication hardening

The implemented baseline includes a separate, globally serial canonicalization
worker; bounded candidate matching with stored evidence; structured ADD,
UPDATE, and LINK_ONLY plans; transactional application; stale-graph detection;
and immutable observations and Event revisions. The technical specification is
authoritative for this behavior.

Remaining work:

- Continue evaluating the implemented matching weights and thresholds against
  representative duplicate, follow-up, separate-edition, and false-match
  fixtures; the GitHub workshop reminder is now a focused regression case.
- Exercise failed model calls, rejected-plan repair, stale-plan regeneration,
  and ingestion retry behavior in repeated owner operation.

Complete Milestone 4A when matching and recovery are repeatable, explainable,
avoid stale writes, and have focused coverage for reruns and the agreed
difficult cases.

## 4. Next milestone: API contract

Milestone 5 will define the first owner-facing event list and detail resources,
visibility rules, filters, ordering, pagination, identifiers, and map-query
semantics. Every contract change must regenerate and verify OpenAPI and the
TypeScript client.

## 5. Progress and completion rules

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
