# NTU Events Implementation Plan

**Current milestone:** 8 — UI/UX and frontend consolidation (design exploration)
**Next delivery goal:** Compare desktop and mobile design concepts, then build
a small working prototype for owner feedback

This plan owns delivery order, progress, and exit conditions. The
[technical specification](TECHNICAL_SPECIFICATION.md) describes current behavior;
[architecture](ARCHITECTURE.md) describes ownership. Candidate approaches below
remain open until evaluated against source evidence or user needs.

## 1. Delivery target

The first complete personal-use slice will retrieve one approved source,
preserve its provenance, produce a reviewable candidate, resolve its location,
create canonical event data, expose it through the generated API client, and
show it in a local map/list interface.

Reruns must not create accidental duplicates or apply changes against a stale
Event graph. Manual corrections to source-derived fields may be replaced by a
later automatic update that considers the current graph and new evidence.
Public deployment remains a separate later gate.

Local application data through Milestone 9 is disposable development state.
Changes in those milestones may use a clean database instead of migrating or
backfilling rows created by an older implementation. Fresh-database setup and
current-version workflow guarantees remain required. Milestone 10 begins with a
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
| 7. Venue registry consolidation     | Buildings and observed venues have reviewed identities, aliases, relationships, and map points      | Complete    |
| 8. UI/UX and frontend consolidation | An approved fresh design works well on desktop and mobile, with clear frontend code                 | In progress |
| 9. Organizer registry consolidation | Known organizers resolve consistently and new organizer mentions enter an owner-reviewed flow       | Not started |
| 10. Retained personal-use hardening | A clean retained trial handles corrections, reruns, failures, source changes, and upgrades reliably | Not started |
| 11. Controlled source expansion     | Additional approved sources reuse the shared workflow                                               | Not started |
| 12. Public-readiness gate           | The owner approves evidence, quality, security, privacy, accessibility, and rollout readiness       | Not started |
| 13. Public deployment               | The approved audience can reliably access the product                                               | Not started |

## 3. Completed baseline

Milestones 0–6 established the domain, Telegram ingestion, candidate review,
serial canonicalization, deduplication, the published Event API, and the local
map/list/detail interface. The owner accepted the working discovery flow as a
reference prototype; its visual design and layout are not the direction for the
next version. Existing coverage includes failures, reruns, stale writes, API
filters, URL state, and building-level marker grouping. The technical specification owns the implemented
workflow and contract details.

Current matching weights and threshold are accepted for the owner-operated slice;
revisit them when observed duplicates or false matches justify calibration.
Venue-data completeness remains the responsibility of Milestone 7.

The ingestion organization and worker responsibility cleanup is verified.
[Architecture](ARCHITECTURE.md#5-ingestion-boundary) records the resulting module
boundaries. The full Python suite, Ruff, Django checks, migration-drift checks,
and OpenAPI verification pass. Venue-resolution and fresh-database discovery
acceptance are recorded in the completed Milestone 7 section below.

Repository cleanup is also verified: research and evaluation packages live under
`tools/`, Python tests follow their owners, and ignored runtime artifacts are
separated into raw evidence, evaluation runs, and audits. Database-linked evidence
and completed experiment artifacts were preserved. The development guide owns
the updated commands; this cleanup does not close additional milestone gates.

## 4. Completed milestone: venue registry consolidation

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

### Verified acceptance

- A refreshed read-only inventory covers retained approved-source location
  wording. Seventy distinct spellings, including missing wording, have reviewed
  regression expectations. Known places resolve to reviewed data; unsupported,
  off-campus, ambiguous, and unannounced places remain explicitly unresolved.
- Automatic plan creation checks venue suggestions against the reviewed
  registry, preserves original evidence, and records adjustments. Plan
  application rejects missing, unverified, or inactive references. Owner repairs
  remain explicit; unrelated updates preserve existing locations.
- One read-only location-review command lists wording, proposed matches, and
  affected records. The venue source notes own the review and repair procedure.
- Coincident reviewed points share one map marker containing every distinct
  Event. Building fallbacks retain precise source wording in list/detail labels.
- A separate database was built from all migrations. A retained real public
  workshop announcement passed through ingestion, canonicalization, local
  publication, API list/detail reads, and browser map-to-detail navigation. Its
  room, schedule, source link, and reviewed point were checked; a rerun created
  no duplicate. This was a saved-response replay, with no new Telegram fetch or
  paid provider call. The working database was not reset or republished.
- Full Python and web tests, Ruff, web lint and types, production compilation,
  Django checks, migration-drift checks, and API drift checks pass. The web build
  used a fresh temporary cache because the existing local cache had a Windows
  delete-permission error; repository build settings were restored afterward.

These checks satisfy the milestone's documented exit conditions. The completed
scope does not imply that every source fact is verified or every existing Event
has been repaired. Existing ambiguous assignments remain available for owner
review, and new source wording can extend the reviewed cases. Organizer
consolidation and retained-use hardening remain separate milestones.

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

## 5. Current milestone: UI/UX and frontend consolidation

### Focus

Build a useful, natural discovery experience around the
[business requirements](BUSINESS_REQUIREMENTS.md#5-discovery-experience).
Keep desktop and mobile equally important. Start fresh on the experience and
reuse tested behavior or code where it fits the developing design.

Treat student scenarios and reference patterns as ways to assess concepts.
Let layouts, view choices, information density, and interactions evolve through
feedback. A prominent map can work alongside other presentations; its role does
not prescribe the same arrangement on every screen.

### Working approach

1. Explore a few desktop and mobile concepts using representative event content.
   Compare ease of finding an event, understanding it, and continuing discovery.
   Consider additional features where they help, explaining their benefit and
   ongoing work before agreeing implementation scope.
2. Build a small working prototype of the most promising direction. Use clearly
   identified simulated data or behavior where needed. Include enough variation
   to assess real use, such as sparse facts, different attendance modes, and
   loading, empty, or error states.
3. Review the prototype with the owner and iterate. Agree the direction and
   feature scope before full implementation. Routine refinements can continue
   within that agreement; revisit material changes to scope or direction.
4. Implement the agreed flows against the real API and consolidate frontend code
   where useful. Prefer existing framework conventions and shared pieces that
   solve actual repetition. Let product needs justify API changes or dependencies;
   retain the ownership and generation workflow in the architecture and
   development guide.

The initial task and reference review is done; no final design is approved and
prototype implementation has not begun. Reference ideas include area/result
connections from [Google Maps](https://support.google.com/maps/answer/4610185),
date-grouped browsing from [Luma](https://luma.com/singapore), and agenda/week
views from [Google Calendar](https://support.google.com/calendar/answer/6110849).
They are optional inspiration, not templates to reproduce or evidence of student
preferences. The next deliverable is a comparison of design concepts for feedback.

The [technical specification](TECHNICAL_SPECIFICATION.md#10-current-api-and-web-behavior)
records the current API and prototype behavior; it does not restrict future
presentation choices. [Engineering concerns](TODO.md) records known result-coverage
and data-support issues to consider as the selected flows are implemented.

### Exit conditions

- The owner has reviewed a working desktop and mobile prototype, and the agreed
  design and scope are implemented with real published API data.
- The main discovery flows are clear, responsive, and usable with touch and
  keyboard. Relevant sparse-data and failure states remain understandable;
  source information and uncertainty follow the existing trust constraints.
  Check applicable [WCAG 2.2 guidance](https://www.w3.org/WAI/WCAG22/quickref/).
- Frontend responsibilities and shared styles are understandable. Obsolete code
  is removed as replacements are verified, and owning docs match the result.
- Relevant browser checks, Prettier, ESLint, TypeScript, Vitest, and a production
  build pass. API or backend changes receive their applicable checks. A prototype
  or scaffold alone does not complete the milestone.

## 6. Next milestone: organizer registry consolidation

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

## 7. Later milestones

After UI/UX and organizer consolidation, establish a clean baseline for
Milestone 10, with owner authorization before resetting the development
database. That milestone begins the retained owner-operated personal-use trial
and the obligation to preserve or explicitly migrate existing application data. Work then continues through controlled
source expansion, the public-readiness gate, and only then an explicitly
approved public deployment.

## 8. Progress and completion rules

- Keep one milestone active at a time.
- Complete the current vertical path before broadening coverage or polishing
  later interfaces.
- Make detailed decisions in the milestone that supplies real evidence for
  them.
- Add migrations, tests, and representative fixtures with the behavior they
  support.
- Through Milestone 9, do not add compatibility migrations or backfills solely
  for disposable development rows; verify changes against a fresh database and
  current-version workflows instead.
- From Milestone 10 onward, treat retained personal-use data as durable and
  verify compatible schema changes, data migrations, or explicit reviewed
  backfills when existing state is affected.
- Update this plan only when milestone scope or status changes; record important
  current behavior or architecture only after it is implemented and verified.
- Complete a task only when its behavior is reproducible, relevant checks pass,
  schema changes have migrations, and material decisions or limitations are
  documented in the appropriate owning file.
