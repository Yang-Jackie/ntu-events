# NTU Events Business Requirements

This document defines product outcomes, scope, and approved trust constraints.
It does not prescribe technical mechanisms; possible implementations belong to
the [technical specification](TECHNICAL_SPECIFICATION.md) and remain open until
evaluated in the relevant milestone. Progress and release sequencing belong in
the [implementation plan](IMPLEMENTATION_PLAN.md).

## 1. Product purpose

NTU Events helps Nanyang Technological University students discover publicly
advertised activities, with the map as its main hook. Events may be attended
in person, online, or in a hybrid format.

Event information is currently scattered across university sites, student
organization pages, Telegram channels, social platforms, and newsletters. The
product brings relevant information together, associates it with campus
locations, and helps users discover what is happening by place, time, and
interest.

The product is not initially an event-registration system, organizer portal,
social network, or recommendation engine.

## 2. Release approach and users

The project first runs as an owner-operated personal product using the complete
ingestion and discovery workflow. This phase is intended to prove usefulness,
coverage, data quality, and maintainability before public exposure.

Development through Milestone 9 uses disposable local application data. Those
milestones may reset and rebuild the database instead of preserving or
backfilling rows created by an earlier implementation. Milestone 10 starts the
retained owner-operated personal-use trial. From that boundary onward, changes
must preserve or deliberately migrate the trial's canonical data, provenance,
review decisions, and history.

Disposable development data does not weaken the behavior being built. Each
version must still enforce its current provenance, rerun, duplicate, review,
and stale-write rules, and a fresh environment must be reproducible from the
repository, documented configuration, and approved source setup. Data that is
only useful for development may be replaced by representative fixtures or
fresh ingestion.

Design the experience for NTU students broadly, including undergraduate and
postgraduate students, while the owner initially tests the product in personal
use. Staff, visitors, and events outside NTU do not drive the initial design.

Public deployment requires a separate owner decision based on sustained
personal use. Building the local product does not itself authorize public
release.

## 3. What counts as an event

The initial product covers a time-bounded activity that NTU students can
attend in person, online, or in a hybrid format.

Examples include talks, workshops, competitions, fairs, club activities,
exhibitions, volunteering activities, and sports or recreational sessions.

A named lecture, conference, or workshop with multiple advertised sessions
counts as one event. Its sessions are occurrences of that event, including
sessions with their own labels, dates, locations, or registration details.

The following boundaries apply:

- In-person, online-only, and hybrid activities may be included.
- General opportunities, promotions, campaigns, and standalone deadlines are
  excluded unless they clearly describe an event occurrence.
- Long-running activities may be included when they have a meaningful
  attendance period and location.
- Ambiguous items may be retained internally for review without becoming
  discoverable events.

The detailed rules for difficult time, recurrence, eligibility, and update
cases should be decided while the corresponding processing workflow is built
and tested against real source material.

## 4. Personal-use product scope

The personal product should provide:

- Controlled ingestion from approved public sources
- A consistent internal representation of events and their occurrences
- Source provenance and retained evidence sufficient for review
- An internal review and correction workflow
- Building-level display on an interactive campus map
- Event results connected to the campus map
- Useful ways to narrow results by time, location, interest, and other event
  attributes; choose which controls to expose as the design develops
- Keyword search
- Event details with precise source-provided venue information where available
- Links to the original source and external registration page
- Public meeting links when supplied for an online attendance option
- Retention of past events as a historical archive
- Owner access in a local or otherwise non-public environment

The first implemented ingestion source, and the first intended for the retained
personal-use trial, is selected public Telegram broadcast channels. Official
NTU websites, including the CCDS events site already studied during domain
research, remain expected source types for later controlled expansion.

## 5. Discovery experience

Design a fresh experience for NTU students, with desktop and mobile equally
important. The current UI is a functional reference; its appearance and layout
do not define the next design. A natural, smooth experience is the main criterion
for design choices.

Help students find relevant events, understand whether they can attend, and
reach the original source or registration page. Finding something ongoing or
starting soon, exploring a campus place, and planning or registering for a later
event are useful scenarios to guide evaluation. They are not a prescribed
interface structure.

Keep the map a prominent part of discovery. Explore list, calendar, and other
presentations where they help; placement, size, navigation, filters, and visual
style can evolve through the
[UI/UX milestone](IMPLEMENTATION_PLAN.md#5-current-milestone-uiux-and-frontend-consolidation).
Aim for clear active filters, understandable connections between places and
results, and easy movement between discovery and details. How map movement
changes results is a design choice to test.

Make title, schedule, place or online access, and the next useful action easy
to understand. Reveal organizer, audience, classifications, and other details
where helpful, without giving every field equal visual weight. Event timing and
registration deadlines answer different questions. Missing or uncertain facts
stay explicit, and registration remains external.

Online and unresolved-location events still need a useful discovery path.
Physical-location filters may exclude them, with that effect made clear.
The location and trust constraints below remain in force; layouts and controls
are open to iteration.

## 6. Location direction

Events are displayed at building level for the initial map. Exact rooms,
lecture theatres, floors, or venue names appear in event details when known.
Outdoor locations may use their own reviewed point.

Online-only occurrences do not require a physical venue or receive a map
marker. Hybrid occurrences may carry both a physical venue and online access.

The system must keep source-provided location text separate from normalized
buildings and venues. Common aliases may resolve to the same venue, but
unresolved locations must not be silently assigned to a guessed building.

Room-level indoor rendering and navigation are not required initially.

## 7. Source and retrieval direction

Sources should be added deliberately because they improve relevant coverage.
Early source types include public Telegram channels, official NTU event pages,
school or faculty pages, and selected student-organization public pages or
accounts.

Only independently public content is in scope. An owner-authenticated client may
retrieve public content, but private-source ingestion is deferred.

Retrieval and interpretation should suit the source. Structured interfaces or
embedded data are preferred when reliable; unstructured material may require
model-assisted interpretation or bounded browser interaction. The exact
retrieval method should be selected and justified when each source is
implemented.

External retrieval providers and models supply untrusted observations. They do
not own canonical event data, review decisions, or publication.

## 8. Trust and data quality

User trust has priority over maximum automation.

The product should:

- Preserve source provenance
- Avoid fabricating missing details
- Make ambiguity and conflicts reviewable
- Withhold unreliable items from discovery
- Support manual corrections
- Keep reruns from creating accidental duplicates or applying changes against
  stale event data
- Keep important source material linked to the resulting event
- Direct users to the original source for final verification and registration

Manual corrections to source-derived event information are immediate edits, not
durable overrides. Later source updates may replace them. Publication and
verification decisions remain owner-controlled.

The technical specification describes implemented handling of new, changed,
conflicting, and duplicate candidates. Automatic publication remains an open
later decision and must be based on observed data.

The current owner-operated workflow retains a useful sparse reference when no
existing Event match is found, rather than hiding an announced event solely
because details are incomplete. Possible duplicates and follow-up observations
remain linked to their evidence and are reconciled before changing an existing
Event.

## 9. Success and public-release gate

The retained personal-use trial that starts at Milestone 10 succeeds when
repeated use demonstrates:

- Useful event coverage
- Reliable dates and locations
- Acceptably few duplicates and stale records
- Safe reruns
- A manageable review workflow
- Continued use of the map, list, search, and filters

Before public release, the owner must approve the observation period, quality
thresholds, minimum source coverage, unresolved-review tolerance, and rollout
scope.

After public release, adoption and engagement may also be measured through
returning users, event-detail views, map and filter interactions, and clicks to
source or registration pages. Raw event count alone is not a success measure.

## 10. Deferred product scope

The following remain outside the approved personal-use scope. Additional
features may be proposed during the UI/UX milestone, but considering them does
not approve implementation. Any agreed addition must update this scope. A
calendar view of discovered events is separate from external calendar or
timetable integration.

- Public user accounts, bookmarks, notifications, or personalization
- Timetable or calendar integration
- Natural-language search
- Social features or user discussions
- Organizer submission, claiming, dashboards, or analytics
- Internal registration or payments
- Indoor navigation or detailed room maps
- Automatic source discovery
- Private email or private-account ingestion
- Events outside the NTU-focused geographic scope
- Advertising or monetization

## 11. Owner decisions to make later

- Whether personal access remains local-only or becomes privately reachable
- What evidence is sufficient for public release
- Whether public rollout is invited, staged, or open
- Which additional source types are needed for useful coverage
- Which additional user features justify their implementation and ongoing
  work, including proposals considered during the UI/UX milestone
