# NTU Map-Based Event Discovery Platform
## Business Requirements and Product Vision

**Document status:** Initial agreed product specification  
**Primary audience:** Project owner, collaborators, reviewers, and AI coding/research assistants

---

## 1. Project Overview

The project is a map-first event discovery platform for Nanyang Technological University undergraduate students.

Its purpose is to aggregate fragmented event information from multiple public sources, structure it into a consistent format, associate each event with a physical campus location, and allow students to discover relevant events through an interactive NTU campus map.

The platform is primarily a discovery and aggregation product. It is not initially an event registration system, organizer-management platform, social network, or recommendation engine.

The project will first run as an owner-only personal product using the complete ingestion and discovery workflow. Public release for NTU students follows only after sustained use shows useful coverage and reliable data. The same architecture should support both phases; public hosting and operations are deferred, not designed away.

The platform will be free, with no immediate commercial model.

---

## 2. Problem Being Addressed

NTU events are currently distributed across many disconnected channels, including:

- Central NTU websites
- School and faculty websites
- Student organization pages
- Instagram accounts
- Telegram channels
- LinkedIn
- Email newsletters

This creates several problems for students:

1. Students often do not know that relevant events exist.
2. Event information is fragmented across many sources.
3. Discovering useful or interesting events requires significant manual searching.
4. Students cannot easily determine whether an event is convenient based on its location and timing.
5. Existing event listings generally do not provide a comprehensive, location-first view of activity across the NTU campus.

The product hypothesis is that displaying events spatially on a campus map will make event discovery more intuitive and useful than relying only on conventional lists, calendars, social-media feeds, or individual organization pages.

---

## 3. Target Users and Release Sequence

The initial user and operator is the project owner. The target users for the first public release remain NTU undergraduate students.

The product may later expand to include:

- Postgraduate students
- Staff
- Visitors
- Events outside NTU that are relevant to NTU students

These groups are outside the initial scope.

---

## 4. Core Product Proposition

The platform provides:

> A comprehensive, reliable, map-based view of publicly advertised physical events happening across NTU.

Its main differentiator is not merely maintaining an event list. Its value comes from combining fragmented event information into a single location-oriented discovery experience.

The platform should help students answer questions such as:

- What is happening around campus today?
- What events are taking place near a particular building?
- What events are available during a selected time window?
- What events are relevant to a particular academic or personal interest?
- What hackathons, talks, workshops, or club activities are happening soon?

---

## 5. Definition of an Event

The initial definition of an event is:

> A time-bounded activity that students can physically attend at a specified venue.

Examples include:

- Talks and seminars
- Workshops
- Hackathons and competitions
- Career fairs and networking sessions
- Club activities
- Exhibitions
- Physical volunteering activities
- Sports or recreational sessions

The following rules apply initially:

- Online-only events are excluded.
- Hybrid events may be included when they have a physical NTU venue.
- General opportunities without a physical occurrence are excluded.
- Application deadlines without an associated physical event are excluded.
- Promotions, announcements, and campaigns are excluded unless they relate to a specific physical event occurrence.
- Long-running exhibitions may be included if they have a defined location and attendance period.

This definition prevents the platform from expanding prematurely into a general opportunities or announcements board.

---

## 6. Primary User Experience

The main interface consists of:

- An interactive NTU campus map
- Markers representing buildings or outdoor event locations
- A synchronized list or card view of matching events
- Conventional search and filtering controls
- Event detail views
- Links to original event or registration sources

Selecting a map marker should show events occurring at that location.

Selecting an event should display information such as:

- Event title
- Description or summary
- Date
- Start and end time
- Building
- Precise room or venue, where available
- Organizer
- Format, topic, purpose, and intended audience
- Intended audience
- Registration link
- Original source
- Last verified or updated time

Registration will not be handled internally. Users will be redirected to the original registration page or organizer source.

The map and list should remain synchronized so that changing the visible map area or active filters updates the displayed events.

---

## 7. Meaning of Convenience

Convenience will initially be evaluated through explicit user actions rather than stored personal information or automatic personalization.

The priority order is:

1. Location
2. Event category, type, or area of interest
3. Date and time

Example interactions include:

- Show events in a particular part of campus.
- Show events occurring between 2:00 PM and 4:00 PM on a selected date.
- Show events happening within the next seven days.
- Show events likely to be relevant to computing students.
- Show hackathons occurring next weekend.

The initial system will not require access to a user’s:

- Timetable
- Calendar
- Current location
- Course information
- Personal profile
- Past behavior

Possible future features include timetable integration, calendar integration, personalized recommendations, and travel-aware suggestions.

---

## 8. Personal-Use MVP Scope

The initial usable version is an owner-only product and should include:

- Physical NTU events only
- Publicly accessible sources only
- NTU official event sources
- Selected student organization sources
- Source-appropriate retrieval and interpretation: prefer reliable structured APIs, feeds, exports, or managed retrieval outputs when available; use LLM-first extraction for unstructured content, including constrained browser exploration when interaction is required
- Event normalization into a common structure
- Building-level map display
- Precise room information in event details where available
- Interactive map and synchronized event list
- Date filtering
- Time filtering
- Format, topic, purpose, and intended-audience filtering
- Intended-audience filtering
- Location filtering
- Keyword search
- Event detail pages
- Links to original sources
- External registration redirects
- Storage of past events as a historical archive
- Owner access in a local or otherwise non-public environment
- An internal review capability for maintaining data quality

Student organization sources may include public Instagram pages. Access to social-platform content must be treated as a separate product, legal, and technical concern from extracting event information after content has been obtained.

Retrieval may be performed directly or through approved third-party services such as managed scraping and browser-automation providers. Provider output remains untrusted source material: the platform must preserve provenance, validate it, and apply its own normalization, deduplication, review, and publication rules. No retrieval provider becomes the canonical source of product data.

Public hosting, accounts, multi-user behavior, and production operations are not required yet. Data boundaries, validation, provenance, and the API contract must remain suitable for later release.

---

## 9. Features Outside the Initial Scope

The following are deliberately postponed:

- Organizer dashboards
- Organizer event submission
- Organizer event claiming
- Internal event registration
- Payment processing
- Personalized recommendation models
- User timetable integration
- Google Calendar integration
- Outlook Calendar integration
- Natural-language search
- Social features
- Friend activity
- User reviews
- User-generated event discussions
- Notifications
- Indoor navigation
- Full room-level map rendering
- Events outside NTU
- Private email ingestion
- Private or authenticated-only source ingestion; an owner-authenticated client
  may retrieve content that is independently public
- Automatic discovery of new source accounts
- Advertising or monetization

Optional user accounts may be introduced later for bookmarks, notifications, saved searches, cross-device history, and personalization.

---

## 10. Location Strategy

Location is the central product dimension.

For the MVP:

- Events are displayed at building level on the campus map.
- Outdoor events may use a specific outdoor point where reliable coordinates exist.
- Exact rooms, lecture theatres, floors, or venue names are displayed inside event details.
- Room-level indoor map rendering is not required.
- Links to an existing NTU indoor map may be provided when a reliable room mapping is available.

The product must distinguish between:

- Building
- Floor
- Room or venue
- Raw location text from the source
- Normalized location
- Geographic coordinates used for map display
- Alternative building or room names
- Common abbreviations

For example, variations such as:

- LT19A
- NS LT19A
- North Spine LT19A
- Lecture Theatre 19A

should resolve to one canonical venue.

Unresolved locations should not be silently assigned to incorrect buildings.

---

## 11. Source Scope

Initial sources should be deliberately controlled rather than attempting to crawl the entire internet.

The first source categories are:

1. NTU central event websites
2. NTU school and faculty websites
3. Selected student organization webpages or public accounts
4. Selected public Telegram broadcast channels

Potential later sources include:

- LinkedIn
- Email newsletters
- Nearby external event platforms
- Organizer-submitted feeds

Each source should have an explicit reason for inclusion and should contribute events relevant to the target users.

---

## 12. Data Reliability Principles

The platform should prioritize user trust over maximum automation.

Important principles include:

- Always preserve and display source provenance.
- Do not fabricate missing event details.
- Mark ambiguous information explicitly.
- Avoid publishing events with unresolved dates or locations.
- Record when an event was last verified.
- Allow internal corrections and manual overrides.
- Preserve previous event information when important details change.
- Distinguish official sources from student-organization or automatically extracted sources.
- Avoid presenting inferred information as confirmed fact.
- Redirect users to the original source for registration and final verification.

A hybrid publication model is preferred:

- High-confidence events may be published automatically.
- Low-confidence, incomplete, or conflicting events should be withheld or queued for review.

---

## 13. Main Product and Business Challenges

The largest product risk is insufficient event coverage.

Students may stop using the platform if it repeatedly misses events they already encounter through Instagram, Telegram, or existing NTU channels.

Other important challenges include:

1. Maintaining enough source coverage for the platform to feel comprehensive
2. Preventing incorrect or outdated event information
3. Demonstrating a clear advantage over existing event calendars and social feeds
4. Handling social-platform restrictions
5. Avoiding excessive manual maintenance
6. Building trust in automatically collected information
7. Encouraging repeated use rather than one-time curiosity
8. Keeping the location experience genuinely useful
9. Managing source permissions and terms of service
10. Operating the platform sustainably as a solo developer or small team

Coverage and reliability must be improved together. A large but inaccurate index is not useful, while a highly accurate but incomplete index may not be compelling enough to retain users.

---

## 14. Success Criteria and Public-Release Gate

The personal-use phase succeeds when repeated real use demonstrates:

- Useful coverage, accurate dates and locations, and acceptably few duplicates or stale events
- Safe reruns and a manageable, traceable review workflow
- Continued use of the map, list, search, and filters across multiple discovery cycles

Public deployment requires owner-approved thresholds for observation time, coverage, extraction and location accuracy, duplicates, stale events, and unresolved reviews.

After public release, success should additionally be evaluated through adoption and engagement measures such as:

- Number of active users
- Number of returning users
- Event detail views
- Map interactions
- Search usage
- Filter usage
- Clicks to original event or registration sources
- Bookmarks or saves when introduced
- Percentage of relevant NTU events successfully indexed
- Accuracy of event dates
- Accuracy of event locations
- Number of duplicate records
- Number of outdated records
- Number of user-reported corrections when reporting is introduced

Raw event count alone should not be treated as the main success measure in either phase.

---

## 15. Longer-Term Vision

If the NTU-focused version is successful, the platform could expand to include:

- Nearby external events relevant to NTU students
- Other Singapore universities
- Personalized recommendations
- Timetable integration
- Calendar integration
- Travel-time-aware suggestions
- Event notifications
- Saved searches
- Organizer submissions
- Organizer event claiming
- Organizer analytics
- Room-level indoor maps
- Public APIs
- Private-source ingestion with explicit user consent
- A reusable event aggregation platform for other campuses

The initial product should remain narrowly focused on proving that a comprehensive, reliable, and location-first view of campus events creates meaningful value for NTU students.

---

## 16. Current Direction and Open Calls

### Agreed

The following decisions are considered agreed for the initial direction:

- The first release is owner-only; public release for NTU undergraduates requires an explicit usefulness and reliability gate.
- The platform is map-first.
- The platform is a discovery product rather than an organizer platform.
- The initial scope contains physical events only.
- The initial geographic scope is the NTU campus.
- Public sources are used first.
- Registration remains external.
- Accounts are not mandatory.
- Personalization is deferred.
- Conventional filters come before natural-language search.
- Building-level map display is sufficient for the MVP.
- Exact room information is shown in event details.
- Historical events remain stored and searchable.
- The project is a realistic portfolio system with a path toward becoming a real student product.

### Owner calls when they become blocking

- Whether the personal product must remain local-only or be privately reachable from multiple devices.
- What measurable thresholds and observation period define “good enough” for public deployment.
- Whether the first public release is an open launch, a small invited pilot, or a staged rollout.
- Which additional source types are required before the product has sufficient coverage for public use.
