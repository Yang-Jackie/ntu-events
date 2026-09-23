# NTU/NIE Venue Catalog

**Status:** Reviewed catalog and building-level geography implemented
**Scope:** NTU main-campus and adjacent NIE identities, relationships,
event-useful subvenues, and building-level map points

## Reviewed sources

The version-controlled catalog records its source URL on every building and
subvenue. Its current official sources include:

- [NTU Maps](https://maps.ntu.edu.sg/) and current NTU campus, hall, and art
  trail pages for campus identities and current names.
- [NTU Facility Location and Capacity](https://wis.ntu.edu.sg/pls/webexe88/FBSDOCU.FBSLOCATN)
  and the NBS facilities directory for official room names, room codes,
  capacities, and building associations.
- Current NTU library, sports, school, centre, and event pages for specialist
  spaces and recently observed venue wording.
- The official NIE institutional profile for the adjacent NIE building and
  facility inventory.

`apps/backend/venues/catalog.json` is the reviewed manual product input.
`apps/backend/venues/facilities.json` is a versioned snapshot generated from
the two official public facilities directories. Live source pages inform
catalog review but are not queried by ordinary application or test execution.

`apps/backend/venues/geography.json` is the separate reviewed WGS84 point
snapshot. It uses bounded OpenStreetMap extracts and preserves each accepted
OSM object reference, point semantics, and verification date. OpenStreetMap
data is © OpenStreetMap contributors and licensed under the
[ODbL](https://www.openstreetmap.org/copyright).

MazeMap is used only as a human-facing coverage checklist. Its records,
identifiers, and geometry are not extracted or imported. A space first noticed
there enters this catalog only after an independent NTU page or document
confirms it; the retained record cites that NTU source.

## Coverage and relationship rules

The catalog currently defines 89 active location anchors and 375 subvenues.
Every anchor also has a fallback `Venue`, producing 464 stable coded venue
records and 763 verified aliases on a clean database. The merged subvenues are
87 manually reviewed entries plus 288 non-overlapping rows from the 324-row
official facilities snapshot; 36 snapshot rows are replaced by richer manual
records with the same room code.

Coverage is broad at both the anchor and public teaching/event-facility levels:

- Main academic, administration, event, cultural, library, sports, outdoor,
  residential-hall, and major research locations are represented.
- Residential hierarchy includes Nanyang Crescent Halls (Hall 7, Tamarind and
  Saraca) and North Hill (Binjai, Tanjong and Banyan) as complexes above their
  constituent halls.
- The adjacent NIE inventory includes its institute identity, named blocks,
  library, sports hall, playhouse, and art gallery.
- The central and NBS directories contribute their complete public inventories
  of lecture theatres, tutorial and seminar rooms, computing/project rooms,
  labs, auditoriums, and function spaces, including capacity and published
  booking eligibility.
- Independently verified specialist additions cover robotics, CEE software and
  hydraulics labs, the MSE undergraduate lab, Innovation Port spaces, and
  Nanyang Auditorium spaces.
- A `Building` record is a stable location anchor. Its `location_kind` and
  optional `parent` express a shallow complex/building/block/facility hierarchy,
  such as North Spine -> Block N4 -> rooms. A `Venue` is an attendable place:
  either the anchor fallback or a room, hall, library, gallery, meeting space,
  function space, sports space, or other subvenue beneath it.
- Schools inside a larger physical complex are modeled as child venues rather
  than duplicate buildings. For example, the Schools of Humanities and Social
  Sciences are children of the Singapore Hokkien Huay Kuan Building.

Current official names remain canonical while well-supported former names are
aliases. In particular, `The Hive` and `Learning Hub South` resolve to the UOB
Innovation Hub; `Gaia`, `Academic Building South`, and `ABS` resolve to Wee Cho
Yaw Plaza. The separate NTU Innovation Centre at 71 Nanyang Drive remains its
own building. Superseded duplicate building rows from the earlier seed are
retained as inactive migration history rather than treated as current places.

Verified aliases must be globally unambiguous. Contextual forms such as
`North Spine LT1`, stable room codes such as `NS3-02-09`, and observed forms
such as `The Arc TR+1` may resolve deterministically. Ambiguous shorthand such
as plain `LT1` is deliberately not a verified alias and must remain unresolved
until source context identifies the place.

## Reproducible maintenance

Refresh and compare the official directory snapshot with:

```powershell
corepack pnpm venues:update
corepack pnpm venues:check
```

Migrations through `venues.0010_sync_reviewed_venue_geography` load the merged
catalog and reviewed building points on a clean database. The catalog and
geographic workflows remain separate and idempotent:

```powershell
corepack pnpm venues:sync
corepack pnpm venues:geography:sync
```

The loader validates stable code uniqueness, parent relationships, source
references, globally unambiguous verified aliases, and the absence of
geographic fields. Each building, venue, and verified alias stores its source
URL and verification time. Raw extracted wording never creates a trusted
catalog record or verified alias.

## Geographic coverage and limitations

The identity catalog deliberately contains no geographic fields, and catalog
synchronization never changes map points. The separate geographic snapshot
covers all 89 active anchors. Direct mapped points or mapped-geometry centres
are used where available. North and South Spine teaching wings that OSM does
not distinguish use the reviewed parent marker; Crescent and Pioneer Halls use
documented centres derived from their mapped residential blocks; Hall 1 shares
the 30 Nanyang Link point while NTU's announced 2026-2027 temporary relocation
is in effect. These semantics remain visible through `map_positioning_method`
and snapshot notes.

Rooms, floors and other indoor subvenues intentionally have no coordinates and
inherit their building marker. Entrances, polygons, indoor floor geometry and
routing remain out of scope for this stage.
