# NTU Events Business Requirements

**Document status:** Active product direction
**Primary audience:** Project owner, contributors, and reviewers

## 1. Product purpose

NTU Events is a map-first discovery product for publicly advertised activities
relevant to Nanyang Technological University students. Events may be attended
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

The intended audience for a later public release is NTU undergraduate students.
Postgraduate students, staff, visitors, and events outside NTU may be considered
later, but they do not drive the initial product.

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
- A synchronized event list
- Date, time, location, interest, format, and audience filtering
- Attendance-mode filtering
- Keyword search
- Event details with precise source-provided venue information where available
- Links to the original source and external registration page
- Public meeting links when supplied for an online attendance option
- Retention of past events as a historical archive
- Owner access in a local or otherwise non-public environment

The first production ingestion source is selected public Telegram broadcast
channels. Official NTU websites, including the CCDS events site already studied
during domain research, remain expected source types for later controlled
expansion.

## 5. Discovery experience

The map is the primary organizing view, supported by a list or card view.
Changing map bounds or filters should update the visible results, and selecting
a location should reveal the events associated with it.

Online-only occurrences appear in the synchronized list without a map marker.
They remain visible unless the user explicitly applies a physical-location or
map-area filter.

An event detail should communicate the useful facts without pretending that
missing or inferred information is confirmed. Typical information includes:

- Title and description
- Date and time
- Building and precise room or venue text
- In-person, online, or hybrid attendance mode and public meeting access when
  supplied
- Organizer
- Format, topic, purpose, and intended audience
- Registration and source links
- Verification or update information

Registration remains external.

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
- Keep reruns from creating accidental duplicates or silently undoing manual
  decisions
- Keep important source material linked to the resulting event
- Direct users to the original source for final verification and registration

The implementation milestone that introduces canonicalization should decide how
new, changed, conflicting, and duplicate candidates are handled. The
publication milestone should separately decide what may be shown
automatically. These behaviors should be based on observed data rather than
fixed in advance here.

## 9. Success and public-release gate

The personal phase succeeds when repeated use demonstrates:

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

The following do not belong to the personal-use MVP:

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
- Which optional user features are worth introducing after the discovery
  experience is proven
