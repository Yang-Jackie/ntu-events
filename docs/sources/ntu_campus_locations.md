# NTU Campus Location Seed

**Status:** Initial reviewed domain seed  
**Scope:** NTU main campus and adjacent NIE building-level locations

## Sources

- [NTU Maps](https://maps.ntu.edu.sg/) is the current official interactive map
  entry point. It embeds a MazeMap campus configuration.
- [NTU Facilities Booking](https://wis.ntu.edu.sg/pls/webexe88/FBSDOCU.FBSLOCATN)
  provides current room codes, facility names, capacities, and building
  associations.
- [NTU Discover](https://www.ntu.edu.sg/about-us/discover-ntu) identifies current
  major landmarks.
- [NTU Hall Orientation](https://www.ntu.edu.sg/orientation/hall-orientation)
  identifies the current undergraduate hall set.
- [NTU Campus Art Trail 2026](https://www.ntu.edu.sg/media/docs/default-source/life-at-ntu/museum/ntu-campus-art-trailef0626a3-2f02-49b6-9629-6376d8d0c580.pdf)
  provides a current campus overview and landmark cross-check.

## Seed behavior

Migration `venues.0002_seed_core_locations` creates 51 reviewed buildings,
halls, and landmarks across the `MAIN` and `NIE` campus areas. It creates a
building-level venue for every location so an occurrence can resolve to a
building before a room is known. It also creates only explicitly reviewed
aliases such as `NS`, `SS`, `LHS`, `LHN`, and `ABS`.

Rooms are added incrementally when production event sources require them and an
authoritative directory confirms their identity. Raw extracted location text
never creates a building, venue, or verified alias.

## Coordinate limitation

The official NTU map is an embedded interactive MazeMap application, not a
versioned public coordinate export in this repository. Seeded `map_point`
values therefore remain null. A later reviewed import may populate PostGIS
points from NTU Maps or another approved authoritative source under its access,
licensing, and attribution terms. Coordinates must not be guessed or silently
copied from an unreviewed third-party map.
