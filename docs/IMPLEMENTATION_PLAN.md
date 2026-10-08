# NTU Events Implementation Plan

**Current milestone:** 7 — Venue registry consolidation
**Next delivery goal:** Exercise representative source-location resolution and
the fresh-database Event-to-reviewed-marker flow

This plan owns delivery order, progress, and exit conditions. The
[technical specification](TECHNICAL_SPECIFICATION.md) describes current behavior;
[architecture](ARCHITECTURE.md) describes ownership. Candidate approaches below
remain open until evaluated against source evidence.

## 1. Delivery target

The first complete personal-use slice will retrieve one approved source,
preserve its provenance, produce a reviewable candidate, resolve its location,
create canonical event data, expose it through the generated API client, and
show it in a local map/list interface.

Reruns must not create accidental duplicates or apply changes against a stale
Event graph. Manual corrections to source-derived fields may be replaced by a
later automatic update that considers the current graph and new evidence.
Public deployment remains a separate later gate.

Local application data through Milestone 8 is disposable development state.
Changes in those milestones may use a clean database instead of migrating or
backfilling rows created by an older implementation. Fresh-database setup and
current-version workflow guarantees remain required. Milestone 9 begins with a
clean baseline and is the durability boundary for the retained owner-operated
personal-use trial; changes after that point must account for its existing data.

## 2. Milestones

| Milestone                           | Outcome                                                                                             | Status      |
| ----------------------------------- | --------------------------------------------------------------------------------------------------- | ----------- |
| 0. Foundation research              | Product scope, initial source research, and domain questions are understood well enough to begin    | Complete    |
| 1. Repository scaffold              | Backend, web, API-client package, local database, and basic checks run                              | Complete    |
| 2. Domain foundation                | Core source, ingestion, event, organizer, classification, and venue records are reviewable          | Complete    |
| 3. First-source ingestion           | Telegram content can be processed repeatedly with retained provenance and inspectable results       | Complete    |
| 4. Processing workflow              | A reviewable candidate can become canonical event data through a safe, repeatable workflow          | Complete    |
| 4A. Deduplication hardening         | Likely duplicates and revisions are identified and resolved using reviewable evidence               | Complete    |
| 5. API contract                     | The web application can retrieve typed event data through the generated client                      | Complete    |
| 6. Personal discovery interface     | The owner can find ingested Events through a local map, list, and detail view                       | Complete    |
| 7. Venue registry consolidation     | Buildings and observed venues have reviewed identities, aliases, relationships, and map points      | In progress |
| 8. Organizer registry consolidation | Known organizers resolve consistently and new organizer mentions enter an owner-reviewed flow       | Not started |
| 9. Retained personal-use hardening  | A clean retained trial handles corrections, reruns, failures, source changes, and upgrades reliably | Not started |
| 10. Controlled source expansion     | Additional approved sources reuse the shared workflow                                               | Not started |
| 11. Public-readiness gate           | The owner approves evidence, quality, security, privacy, accessibility, and rollout readiness       | Not started |
| 12. Public deployment               | The approved audience can reliably access the product                                               | Not started |

## 3. Completed baseline

Milestones 0–6 established the domain, Telegram ingestion, candidate review,
serial canonicalization, deduplication, the published Event API, and the local
map/list/detail interface. The owner accepted the discovery interface. Existing
coverage includes failures, reruns, stale writes, API filters, URL state, and
building-level marker grouping. The technical specification owns the implemented
workflow and contract details.

Current matching weights and threshold are accepted for the owner-operated slice;
revisit them when observed duplicates or false matches justify calibration.
Venue-data completeness remains the responsibility of Milestone 7.

## 4. Current milestone: venue registry consolidation

### Outcome and scope

Create a trustworthy location registry for discovery and ingestion. Aim for a
complete building inventory within the current NTU/NIE scope and sufficient
room or subvenue coverage for locations actually observed in approved sources;
enumerating every campus room is not currently a goal. Raw source wording stays
separate from normalized location data and unresolved wording is not guessed.

### Questions to resolve

1. Does the reviewed inventory cover the locations in representative approved-source
   evidence, and where are the gaps?
2. Which names, codes, and reviewed aliases support deterministic matching, and
   which ambiguous or unknown terms need owner review?
3. Can the current hierarchy and bounded building fallback express these cases
   without guessing, and what is the smallest reproducible resolution workflow?

### Implemented

- Reviewed NTU/NIE identities, a shallow location hierarchy, stable codes,
  room metadata, verified aliases, and per-record provenance.
- A manual catalog merged with a generated official-facilities snapshot by
  physical room code. Migrations and idempotent commands rebuild the registry.
- A separate reviewed WGS84 snapshot for every active anchor, with OSM
  provenance and explicit positioning methods. Rooms inherit building markers.
- Model instructions permit a building-level fallback only when source evidence
  unambiguously identifies the parent of a missing room or subvenue.

The [venue source notes](sources/ntu_campus_locations.md) own coverage counts,
source details, geographic limitations, and maintenance commands.

### Remaining work

1. Select representative approved-source evidence and review every distinct
   location string, including ambiguous and unknown wording.
2. Verify which locations resolve to reviewed data and which remain visibly
   unresolved after fresh ingestion. Choose the smallest review workflow needed.
3. On a fresh database, ingest and publish a real physical Event and verify its
   reviewed marker and map/list/detail flow.

The registry and map-point foundation is implemented; these remaining checks
prevent Milestone 7 from being marked complete.

### Candidate directions to evaluate

- Continue treating a Building as the ordinary map anchor and its Venues as
  attendable places. The existing representation of rooms as Venues under a
  Building is the simplest starting point, but should be validated against the
  observed location inventory before being made a durable rule.
- Prefer building points for indoor locations and distinct points for outdoor
  or independently locatable venues, subject to what the reviewed source data
  supports.
- Start resolution with canonical names, codes, and unambiguous reviewed
  aliases. Fuzzy matching could rank review suggestions, but should not silently
  assign a location.
- Evaluate a report, management command, or Admin workflow for unresolved terms
  based on representative source evidence and observed review volume rather
  than building all three.

### Map experiments outside the exit conditions

The implemented MapLibre/OpenFreeMap map includes a local OSM raster comparison.
A small reviewed NTU overlay is a possible later experiment. Institutional map
integration depends on approved access and actual data; it adds no Milestone 7
scope. The technical specification owns map constraints and future integration
boundaries.

### Exit conditions

- The agreed in-scope building inventory is reviewed for identity, provenance,
  relationships, and map availability, with limitations made explicit.
- Every distinct location in the milestone's representative source evidence is
  either resolved to reviewed location data or remains explicitly unresolved
  and reviewable after fresh ingestion.
- Approved aliases are unambiguous, the selected maintenance workflow is safe
  to repeat, and fresh ingestion preserves raw source wording.
- On a freshly built database, a real published physical Event appears at its
  reviewed building marker and the map/list/detail flow remains functional.

## 5. Next milestone: organizer registry consolidation

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
   mentions occur in representative source evidence?
4. What resolution outcomes and evidence need to remain inspectable when a name
   resolves, stays unknown, or matches several possible organizers?
5. What is the smallest owner workflow that can add or link an organizer and
   resolve newly ingested source evidence consistently?

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
- Ensure organizer catalog and alias data needed for the retained trial can be
  reproduced after a clean rebuild; database-only exploration is not sufficient.

### Exit conditions

- The milestone establishes and documents a source-grounded organizer identity
  rule using representative source evidence.
- Every distinct organizer mention in that reviewed evidence is resolved,
  classified as a non-organizer, or explicitly unresolved after fresh
  ingestion.
- Repeated variants resolve consistently and ambiguous names never create or
  modify organizer relationships automatically.
- The owner can add or link a newly observed organizer and consistently process
  newly ingested source-backed Events.
- Future canonicalization attaches known organizers consistently without
  creating unreviewed organizers.

## 6. Later milestones

After venue and organizer consolidation, reset the development database and
establish the clean baseline for Milestone 9. That milestone begins the retained
owner-operated personal-use trial and the obligation to preserve or explicitly
migrate existing application data. Work then continues through controlled
source expansion, the public-readiness gate, and only then an explicitly
approved public deployment.

## 7. Progress and completion rules

- Keep one milestone active at a time.
- Complete the current vertical path before broadening coverage or polishing
  later interfaces.
- Make detailed decisions in the milestone that supplies real evidence for
  them.
- Add migrations, tests, and representative fixtures with the behavior they
  support.
- Through Milestone 8, do not add compatibility migrations or backfills solely
  for disposable development rows; verify changes against a fresh database and
  current-version workflows instead.
- From Milestone 9 onward, treat retained personal-use data as durable and
  verify compatible schema changes, data migrations, or explicit reviewed
  backfills when existing state is affected.
- Update this plan only when milestone scope or status changes; record important
  current behavior or architecture only after it is implemented and verified.
- Complete a task only when its behavior is reproducible, relevant checks pass,
  schema changes have migrations, and material decisions or limitations are
  documented in the appropriate owning file.
