from copy import deepcopy

import pytest
from django.contrib.gis.geos import Point
from django.db import IntegrityError, transaction
from venues.catalog import load_catalog, sync_catalog, validate_catalog
from venues.geography import load_geography, sync_geography, validate_geography
from venues.models import (
    AliasMatchType,
    Building,
    LocationKind,
    MapPositioningMethod,
    Venue,
    VenueAlias,
    VenueType,
)

pytestmark = pytest.mark.django_db


def test_catalog_has_broad_non_geographic_coverage() -> None:
    catalog = load_catalog()

    assert len(catalog["sources"]) == 37
    assert len(catalog["buildings"]) == 89
    assert len(catalog["venues"]) == 375
    assert catalog["facility_snapshot"]["sources"] == ["ntu_facilities", "nbs_facilities"]
    assert {building["campus_area"] for building in catalog["buildings"]} == {
        "MAIN",
        "NIE",
    }

    forbidden_geo_fields = {"latitude", "longitude", "map_point", "geometry"}
    assert all(
        not forbidden_geo_fields.intersection(item)
        for item in [*catalog["buildings"], *catalog["venues"]]
    )


def test_geography_covers_every_reviewed_anchor_with_osm_provenance() -> None:
    catalog = load_catalog()
    geography = load_geography()

    assert len(geography["buildings"]) == 89
    assert {item["code"] for item in geography["buildings"]} == {
        item["code"] for item in catalog["buildings"]
    }
    assert geography["sources"]["openstreetmap"]["attribution"] == ("© OpenStreetMap contributors")
    assert all(item["source"] == "openstreetmap" for item in geography["buildings"])


def test_geography_rejects_unknown_codes_and_swapped_coordinates() -> None:
    geography = deepcopy(load_geography())
    geography["buildings"][0]["code"] = "UNKNOWN"
    with pytest.raises(ValueError, match="Unknown geography building code"):
        validate_geography(geography)

    geography = deepcopy(load_geography())
    geography["buildings"][0]["latitude"] = 103.68
    geography["buildings"][0]["longitude"] = 1.34
    with pytest.raises(ValueError, match="Latitude is outside"):
        validate_geography(geography)


def test_geography_sync_is_idempotent_and_rooms_inherit_building_points() -> None:
    first = sync_geography()
    second = sync_geography()

    ccds = Building.objects.get(code="N4")
    teaching_room = Venue.objects.get(room_code="NS4-05-79")
    hall_1 = Building.objects.get(code="HALL1")
    temporary_site = Building.objects.get(code="30_NANYANG_LINK")

    assert first == second == {"buildings": 89}
    assert Building.objects.filter(map_point__isnull=False).count() >= 89
    assert ccds.map_point.x == pytest.approx(103.6820915)
    assert ccds.map_point.y == pytest.approx(1.3461876)
    assert ccds.map_source_identifier == "way/49967883"
    assert ccds.map_source_url == "https://www.openstreetmap.org/way/49967883"
    assert ccds.map_positioning_method == MapPositioningMethod.GEOMETRY_CENTER
    assert ccds.map_verified_at is not None
    assert teaching_room.map_point is None
    assert teaching_room.building.map_point is not None
    assert hall_1.map_point.equals_exact(temporary_site.map_point)
    assert hall_1.map_positioning_method == MapPositioningMethod.TEMPORARY_SITE


def test_catalog_rejects_ambiguous_verified_aliases() -> None:
    catalog = deepcopy(load_catalog())
    catalog["venues"][1]["aliases"].append({"value": "North Spine LT1", "match_type": "OBSERVED"})

    with pytest.raises(ValueError, match="ambiguous"):
        validate_catalog(catalog)


def test_reviewed_catalog_is_seeded_with_current_relationships() -> None:
    innovation_hub = Building.objects.get(code="LHS")
    wee_cho_yaw_plaza = Building.objects.get(code="WCYP")
    shhk = Building.objects.get(code="SHHK")

    assert innovation_hub.name == "UOB Innovation Hub"
    assert VenueAlias.objects.filter(
        venue__code="LHS",
        normalized_alias="the hive",
        is_verified=True,
    ).exists()
    assert wee_cho_yaw_plaza.name == "Wee Cho Yaw Plaza"
    assert VenueAlias.objects.filter(
        venue__code="WCYP",
        normalized_alias="gaia",
        is_verified=True,
    ).exists()
    assert VenueAlias.objects.filter(
        venue__code="WCYP",
        normalized_alias="nbs",
        is_verified=True,
    ).exists()
    assert Building.objects.get(code="GAIA").is_active is False
    assert Building.objects.get(code="SSS").is_active is False
    assert Venue.objects.get(code="SHHK_SOH").building == shhk
    assert Venue.objects.get(code="SHHK_SSS").building == shhk

    north_spine = Building.objects.get(code="NS")
    ccds_block = Building.objects.get(code="N4")
    assert north_spine.location_kind == LocationKind.COMPLEX
    assert ccds_block.parent == north_spine
    assert ccds_block.location_kind == LocationKind.BLOCK
    assert VenueAlias.objects.filter(
        venue__code="N4",
        normalized_alias="ccds",
        is_verified=True,
    ).exists()

    nanyang_crescent_halls = Building.objects.get(code="NANYANG_CRESCENT_HALLS")
    north_hill = Building.objects.get(code="NORTH_HILL")
    assert nanyang_crescent_halls.location_kind == LocationKind.COMPLEX
    assert set(nanyang_crescent_halls.child_locations.values_list("code", flat=True)) == {
        "HALL7",
        "SARACA",
        "TAMARIND",
    }
    assert north_hill.location_kind == LocationKind.COMPLEX
    assert set(north_hill.child_locations.values_list("code", flat=True)) == {
        "BANYAN",
        "BINJAI",
        "TANJONG",
    }


def test_catalog_includes_observed_rooms_without_guessing_ambiguous_lt1() -> None:
    lt10 = Venue.objects.get(code="NS_LT10")
    arc_room = Venue.objects.get(code="LHN_TR01")
    abn_room = Venue.objects.get(code="ABN_CF3")
    library_outpost = Venue.objects.get(code="LHS_LIBRARY_OUTPOST")

    assert (lt10.room_code, lt10.capacity, lt10.floor) == ("NS4-04-41", 122, "04")
    assert arc_room.building.code == "LHN"
    assert abn_room.room_code == "ABN-01A-CF3"
    assert library_outpost.room_code == "LHS-01-03"
    assert not VenueAlias.objects.filter(
        normalized_alias="lt1",
        is_verified=True,
    ).exists()


def test_catalog_covers_tutorial_rooms_labs_and_standardized_levels() -> None:
    tutorial_room = Venue.objects.get(room_code="NS4-05-79")
    mse_lab = Venue.objects.get(room_code="N4-B4B-13")
    teaching_labs = Venue.objects.get(room_code="N1-B2B-13")

    assert tutorial_room.name == "TR+1"
    assert tutorial_room.building.code == "NS4"
    assert tutorial_room.level_code == "NS4-05"
    assert tutorial_room.venue_type == VenueType.TUTORIAL_ROOM
    assert tutorial_room.capacity == 36
    assert tutorial_room.bookable_by_staff is True

    # The official NTU facilities page places this room under Block N4.1 even though
    # the room identifier retains the N4 prefix.
    assert mse_lab.building.code == "N4.1"
    assert mse_lab.venue_type == VenueType.LABORATORY

    # Two named teaching labs share one official room identifier, so the catalog
    # keeps one physical venue and uses aliases instead of duplicating the room.
    assert teaching_labs.capacity == 140
    assert Venue.objects.filter(room_code="N1-B2B-13").count() == 1
    assert set(teaching_labs.aliases.values_list("normalized_alias", flat=True)) >= {
        "est lab 1",
        "est lab 2",
    }


def test_catalog_sync_is_idempotent_and_does_not_touch_map_points() -> None:
    north_spine = Building.objects.get(code="NS")
    point = Point(103.0, 1.0, srid=4326)
    north_spine.map_point = point
    north_spine.save(update_fields=("map_point",))

    first = sync_catalog()
    second = sync_catalog()
    north_spine.refresh_from_db()

    assert first == second == {"buildings": 89, "venues": 464, "aliases": 763}
    assert north_spine.map_point.equals_exact(point)
    assert Building.objects.filter(is_active=True).count() == 89
    assert Venue.objects.filter(code__isnull=False, is_verified=True).count() == 464


def test_verified_aliases_are_globally_unambiguous() -> None:
    first = Venue.objects.create(
        name="First test venue",
        normalized_name="first test venue",
        venue_type=VenueType.OTHER,
    )
    second = Venue.objects.create(
        name="Second test venue",
        normalized_name="second test venue",
        venue_type=VenueType.OTHER,
    )
    VenueAlias.objects.create(
        venue=first,
        alias="Shared test alias",
        normalized_alias="shared test alias",
        match_type=AliasMatchType.EXACT,
        is_verified=True,
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        VenueAlias.objects.create(
            venue=second,
            alias="Shared test alias",
            normalized_alias="shared test alias",
            match_type=AliasMatchType.EXACT,
            is_verified=True,
        )
