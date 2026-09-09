# NTU Events Implementation Plan

**Document status:** Active implementation plan
**Current milestone:** 7 — Venue registry consolidation
**Next delivery goal:** Establish a reviewed, maintainable location registry
that supplies real building map points and resolves observed venue wording

This plan commits to delivery outcomes, sequencing, and completion evidence.
Candidate directions describe plausible starting points, not approved
implementation decisions. The active milestone should evaluate them against
real data and the current project load before selecting a mechanism.

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
| 6. Personal discovery interface | The owner can find ingested Events through a local map, list, and detail view                    | Complete    |
| 7. Venue registry consolidation | Buildings and observed venues have reviewed identities, aliases, relationships, and map points  | In progress |
| 8. Organizer registry consolidation | Known organizers resolve consistently and new organizer mentions enter an owner-reviewed flow | Not started |
| 9. Personal-use hardening       | Corrections, reruns, failures, and source changes are handled reliably                           | Not started |
| 10. Controlled source expansion | Additional approved sources reuse the shared workflow                                            | Not started |
| 11. Public-readiness gate       | The owner approves evidence, quality, security, privacy, accessibility, and rollout readiness    | Not started |
| 12. Public deployment           | The approved audience can reliably access the product                                            | Not started |

## 3. Completed milestone: deduplication hardening

The implemented baseline includes a separate, globally serial canonicalization
worker; bounded candidate matching with stored evidence; structured ADD,
UPDATE, and LINK_ONLY plans; transactional application; stale-graph detection;
and immutable observations and Event revisions. Reclaimed ingestion jobs safely
replace an earlier failed screening result while retaining invocation history.
The technical specification summarizes this implemented behavior and its trust
properties.

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

## 5. Completed milestone: personal discovery interface

The first web vertical slice now uses the generated client to render a map and
synchronized event list, URL-backed filters, and an Event detail route.
Online-only occurrences remain in the list without map markers unless a
physical-location filter is active.

The owner has accepted the implemented interface. Automated web tests cover
filter projection, URL state, and building-level marker grouping; lint and type
checks pass. Real building coordinates and catalog completeness are venue-data
responsibilities, so they do not block completion of this UI milestone.

## 6. Current milestone: venue registry consolidation

### Outcome and scope

Create a trustworthy location registry for discovery and ingestion. Aim for a
complete building inventory within the current NTU/NIE scope and sufficient
room or subvenue coverage for locations actually observed in approved sources;
enumerating every campus room is not currently a goal. Raw source wording stays
separate from normalized location data and unresolved wording is not guessed.

### Questions to resolve

1. Which buildings, facilities, outdoor places, and room types belong in the
   current catalog, and what does completeness mean for each category?
2. Which coordinate and identity sources are sufficiently authoritative,
   reviewable, and usable under their access and attribution terms?
3. Can the existing `Building`, `Venue`, and `VenueAlias` relationships express
   the observed data cleanly, including building-level fallbacks and rooms?
4. Which aliases are safe for deterministic matching, and how should ambiguous
   or unknown location wording reach the owner for review?
5. At the current project load, what is the simplest maintenance and backfill
   workflow that stays repeatable, inspectable, and safe on reruns?

### Candidate directions to evaluate

- Continue treating a Building as the ordinary map anchor and its Venues as
  attendable places. The existing representation of rooms as Venues under a
  Building is the simplest starting point, but should be validated against the
  observed location inventory before being made a durable rule.
- Prefer building points for indoor locations and distinct points for outdoor
  or independently locatable venues, subject to what the reviewed source data
  supports.
- Compare database/Admin-only curation with a version-controlled catalog and
  repeatable synchronization. The latter offers stronger reproducibility, but
  may be unnecessary if the inventory and change rate remain small.
- Start resolution with canonical names, codes, and unambiguous reviewed
  aliases. Fuzzy matching could rank review suggestions, but should not silently
  assign a location.
- Evaluate a report, management command, or Admin workflow for unresolved terms
  and backfills based on the observed review volume rather than building all
  three.

### Exit conditions

- The agreed in-scope building inventory is reviewed for identity, provenance,
  relationships, and map availability, with limitations made explicit.
- Every distinct location currently observed in source-backed Events is either
  resolved to reviewed location data or remains explicitly unresolved and
  reviewable.
- Approved aliases are unambiguous, the selected maintenance workflow is safe
  to repeat, and any backfill preserves raw source wording.
- A real published physical Event appears at its reviewed building marker and
  the map/list/detail flow remains functional.

## 7. Next milestone: organizer registry consolidation

### Outcome and scope

Create a trustworthy organizer registry and a controlled path for newly
observed organizer wording. This milestone is independent of venue data. It
does not add an organizer-facing portal, and unreviewed extracted text does not
create trusted organizer records automatically.

### Questions to resolve

1. What evidence distinguishes an organizer or co-host from a contact, speaker,
   performer, venue, sponsor, or incidental named person?
2. Should explicitly organizing individuals and informal groups share the
   existing Organizer concept with formal organizations, and are the current
   attributes sufficient for both?
3. How often do aliases, renamed groups, identical display names, and ambiguous
   mentions occur in the retained candidates?
4. What resolution outcomes and evidence need to remain inspectable when a name
   resolves, stays unknown, or matches several possible organizers?
5. What is the smallest owner workflow that can add or link an organizer and
   safely update already-created Events?

### Candidate directions to evaluate

- Audit frequent real organizer strings before changing the schema. A dedicated
  alias relationship similar to venue aliases is a likely option if the data
  demonstrates recurring name variants.
- Use one consistent resolution policy across canonicalization and manual
  maintenance. A shared domain service is a likely implementation, but the
  boundary should follow the workflows that actually need it.
- Begin with exact or reviewed-alias matches and explicit resolved, unresolved,
  and ambiguous outcomes. More approximate matching could provide review
  suggestions if the observed workload justifies it.
- Start the owner workflow with existing Django Admin capabilities or a small
  command, then add a specialized interface only if repeated use demonstrates
  the need.
- Consider previewable, owner-triggered backfills so existing Events can benefit
  from a reviewed organizer mapping without losing source provenance.

### Exit conditions

- The milestone establishes and documents a source-grounded organizer identity
  rule using representative retained candidates.
- Every distinct organizer mention in the reviewed current dataset is resolved,
  classified as a non-organizer, or explicitly unresolved with evidence.
- Repeated variants resolve consistently and ambiguous names never create or
  modify organizer relationships automatically.
- The owner can add or link a newly observed organizer and safely backfill its
  source-backed Events.
- Future canonicalization attaches known organizers consistently without
  creating unreviewed organizers.

## 8. Later milestones

After venue and organizer consolidation, work continues through personal-use
hardening, controlled source expansion, the public-readiness gate, and only then
an explicitly approved public deployment.

## 9. Progress and completion rules

- Keep one milestone active at a time.
- Complete the current vertical path before broadening coverage or polishing
  later interfaces.
- Make detailed decisions in the milestone that supplies real evidence for
  them.
- Add migrations, tests, and representative fixtures with the behavior they
  support.
- Update this plan only when milestone scope or status changes; record important
  current behavior or architecture only after it is implemented and verified.
- Complete a task only when its behavior is reproducible, relevant checks pass,
  schema changes have migrations, and material decisions or limitations are
  documented in the appropriate owning file.
