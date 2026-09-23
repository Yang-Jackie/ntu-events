from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from django.db import DEFAULT_DB_ALIAS, transaction

CATALOG_PATH = Path(__file__).with_name("catalog.json")
FACILITIES_PATH = Path(__file__).with_name("facilities.json")

LOCATION_KINDS = {"COMPLEX", "BUILDING", "BLOCK", "HALL", "FACILITY", "OUTDOOR"}
VENUE_TYPES = {
    "BUILDING",
    "LECTURE_THEATRE",
    "SEMINAR_ROOM",
    "CLASSROOM",
    "AUDITORIUM",
    "LABORATORY",
    "HALL",
    "SPORTS_FACILITY",
    "LIBRARY",
    "GALLERY",
    "MEETING_ROOM",
    "FUNCTION_SPACE",
    "TUTORIAL_ROOM",
    "DISCUSSION_ROOM",
    "PROJECT_ROOM",
    "COMPUTING_ROOM",
    "STUDIO",
    "OUTDOOR",
    "OTHER",
}


def normalize_venue_text(value: str) -> str:
    return " ".join(value.casefold().split())


def load_catalog(path: Path = CATALOG_PATH) -> dict[str, Any]:
    catalog = json.loads(path.read_text(encoding="utf-8"))
    facilities_path = path.with_name(FACILITIES_PATH.name)
    if facilities_path.exists():
        facilities = json.loads(facilities_path.read_text(encoding="utf-8"))
        manual_room_codes = {
            venue.get("room_code") for venue in catalog["venues"] if venue.get("room_code")
        }
        catalog["venues"].extend(
            venue
            for venue in facilities["venues"]
            if venue.get("room_code") not in manual_room_codes
        )
        catalog["facility_snapshot"] = {
            key: value for key, value in facilities.items() if key != "venues"
        }
    validate_catalog(catalog)
    return catalog


def validate_catalog(catalog: dict[str, Any]) -> None:
    if catalog.get("catalog_version") != 1:
        raise ValueError("Unsupported venue catalog version.")

    sources = catalog.get("sources")
    buildings = catalog.get("buildings")
    venues = catalog.get("venues")
    if (
        not isinstance(sources, dict)
        or not isinstance(buildings, list)
        or not isinstance(venues, list)
    ):
        raise ValueError("Venue catalog sources, buildings, and venues are required.")

    building_codes: set[str] = set()
    building_names: set[str] = set()
    venue_codes: set[str] = set()
    verified_aliases: dict[str, str] = {}

    for building in buildings:
        code = _required_text(building, "code")
        name = _required_text(building, "name")
        _require_source(building, sources)
        location_kind = building.get("location_kind", "BUILDING")
        if location_kind not in LOCATION_KINDS:
            raise ValueError(f"Unknown location kind for {code}: {location_kind}")
        if code in building_codes:
            raise ValueError(f"Duplicate building code: {code}")
        normalized_name = normalize_venue_text(name)
        if normalized_name in building_names:
            raise ValueError(f"Duplicate building name: {name}")
        building_codes.add(code)
        building_names.add(normalized_name)
        _validate_aliases(building.get("aliases", []), code, verified_aliases)

    for building in buildings:
        parent_code = building.get("parent_code")
        if parent_code is not None and parent_code not in building_codes:
            raise ValueError(f"Unknown parent building code for {building['code']}: {parent_code}")
        if parent_code == building["code"]:
            raise ValueError(f"Location {building['code']} cannot be its own parent.")

    for venue in venues:
        code = _required_text(venue, "code")
        _required_text(venue, "name")
        parent_code = _required_text(venue, "building_code")
        _require_source(venue, sources)
        venue_type = _required_text(venue, "venue_type")
        if venue_type not in VENUE_TYPES:
            raise ValueError(f"Unknown venue type for {code}: {venue_type}")
        if code in venue_codes or code in building_codes:
            raise ValueError(f"Duplicate venue code: {code}")
        if parent_code not in building_codes:
            raise ValueError(f"Unknown building code for venue {code}: {parent_code}")
        venue_codes.add(code)
        _validate_aliases(venue.get("aliases", []), code, verified_aliases)
        level_code = venue.get("level_code", "")
        room_code = venue.get("room_code", "")
        if level_code and room_code and not room_code.casefold().startswith(level_code.casefold()):
            raise ValueError(f"Venue level code is inconsistent with room code: {code}")
        for field in ("bookable_by_staff", "bookable_by_student_organisations"):
            if field in venue and not isinstance(venue[field], bool):
                raise ValueError(f"Venue catalog field {field!r} must be boolean for {code}.")

    retired = set(catalog.get("retired_building_codes", []))
    if retired & building_codes:
        raise ValueError("A building cannot be active and retired in the same catalog.")

    for rename in catalog.get("building_code_renames", []):
        target = _required_text(rename, "to")
        if target not in building_codes:
            raise ValueError(f"Building code rename target is not active: {target}")

    forbidden_geo_fields = {"latitude", "longitude", "map_point", "geometry"}
    for item in [*buildings, *venues]:
        if forbidden_geo_fields & item.keys():
            raise ValueError("Geographic data does not belong in venue catalog version 1.")


def sync_catalog(
    *,
    building_model=None,
    venue_model=None,
    alias_model=None,
    using: str = DEFAULT_DB_ALIAS,
) -> dict[str, int]:
    if building_model is None or venue_model is None or alias_model is None:
        from .models import Building, Venue, VenueAlias

        building_model = Building
        venue_model = Venue
        alias_model = VenueAlias

    catalog = load_catalog()
    sources = catalog["sources"]
    verified_at = datetime.fromisoformat(catalog["verified_at"])
    source_urls = [source["url"] for source in sources.values()]
    active_venue_codes = {
        *(building["code"] for building in catalog["buildings"]),
        *(venue["code"] for venue in catalog["venues"]),
    }

    with transaction.atomic(using=using):
        _apply_building_code_renames(
            catalog,
            building_model=building_model,
            venue_model=venue_model,
            using=using,
        )
        _retire_buildings(
            catalog,
            building_model=building_model,
            venue_model=venue_model,
            alias_model=alias_model,
            using=using,
        )
        removed_venues = (
            venue_model.objects.using(using)
            .filter(source_url__in=source_urls, code__isnull=False)
            .exclude(code__in=active_venue_codes)
        )
        removed_venues.update(is_verified=False)
        alias_model.objects.using(using).filter(venue__in=removed_venues).update(is_verified=False)
        alias_model.objects.using(using).filter(
            source_url__in=source_urls,
            is_verified=True,
        ).update(is_verified=False)

        buildings_by_code: dict[str, Any] = {}
        for item in catalog["buildings"]:
            source_url = sources[item["source"]]["url"]
            existing = building_model.objects.using(using).filter(code=item["code"]).first()
            defaults = {
                "name": item["name"],
                "normalized_name": normalize_venue_text(item["name"]),
                "address": item.get("address", ""),
                "postal_code": item.get("postal_code", ""),
                "campus_area": item["campus_area"],
                "official_map_url": item.get("official_map_url", "https://maps.ntu.edu.sg/"),
                "source_url": source_url,
                "verified_at": verified_at,
                "is_active": True,
            }
            if _model_has_field(building_model, "location_kind"):
                defaults["location_kind"] = item.get("location_kind", "BUILDING")
            building, _created = building_model.objects.using(using).update_or_create(
                code=item["code"],
                defaults=defaults,
            )
            buildings_by_code[item["code"]] = building

        if _model_has_field(building_model, "parent"):
            for item in catalog["buildings"]:
                building = buildings_by_code[item["code"]]
                parent = buildings_by_code.get(item.get("parent_code"))
                if building.parent_id != (parent.pk if parent else None):
                    building.parent = parent
                    building.save(using=using, update_fields=("parent",))

        synced_venues: list[Any] = []
        for item in catalog["buildings"]:
            building = buildings_by_code[item["code"]]
            source_url = sources[item["source"]]["url"]
            existing = building_model.objects.using(using).filter(code=item["code"]).first()
            previous_name = existing.name if existing else item["name"]
            venue = _upsert_venue(
                item={
                    "code": item["code"],
                    "name": item["name"],
                    "building_code": item["code"],
                    "venue_type": item["venue_type"],
                    "aliases": item.get("aliases", []),
                },
                building=building,
                previous_name=previous_name,
                source_url=source_url,
                verified_at=verified_at,
                venue_model=venue_model,
                alias_model=alias_model,
                using=using,
            )
            synced_venues.append(venue)

        for item in catalog["venues"]:
            source_url = sources[item["source"]]["url"]
            venue = _upsert_venue(
                item=item,
                building=buildings_by_code[item["building_code"]],
                previous_name=item["name"],
                source_url=source_url,
                verified_at=verified_at,
                venue_model=venue_model,
                alias_model=alias_model,
                using=using,
            )
            synced_venues.append(venue)

    return {
        "buildings": len(buildings_by_code),
        "venues": len(synced_venues),
        "aliases": alias_model.objects.using(using)
        .filter(
            venue__in=synced_venues,
            is_verified=True,
        )
        .count(),
    }


def _apply_building_code_renames(catalog, *, building_model, venue_model, using: str) -> None:
    active_by_code = {item["code"]: item for item in catalog["buildings"]}
    for rename in catalog.get("building_code_renames", []):
        source = building_model.objects.using(using).filter(code=rename["from"]).first()
        target = building_model.objects.using(using).filter(code=rename["to"]).first()
        if source is None or target is not None:
            continue
        target_item = active_by_code[rename["to"]]
        building_venue = (
            venue_model.objects.using(using)
            .filter(building=source, venue_type="BUILDING")
            .order_by("pk")
            .first()
        )
        if building_venue is not None:
            building_venue.code = rename["to"]
            building_venue.save(using=using, update_fields=("code",))
        source.code = rename["to"]
        source.name = target_item["name"]
        source.normalized_name = normalize_venue_text(target_item["name"])
        source.save(using=using, update_fields=("code", "name", "normalized_name"))
        venue_model.objects.using(using).filter(building=source, code=rename["from"]).update(
            code=rename["to"]
        )


def _retire_buildings(
    catalog,
    *,
    building_model,
    venue_model,
    alias_model,
    using: str,
) -> None:
    retired = building_model.objects.using(using).filter(
        code__in=catalog.get("retired_building_codes", [])
    )
    retired.update(is_active=False)
    retired_venues = venue_model.objects.using(using).filter(building__in=retired)
    retired_venues.update(is_verified=False)
    alias_model.objects.using(using).filter(venue__in=retired_venues).update(is_verified=False)


def _upsert_venue(
    *,
    item,
    building,
    previous_name: str,
    source_url: str,
    verified_at,
    venue_model,
    alias_model,
    using: str,
):
    venue = venue_model.objects.using(using).filter(code=item["code"]).first()
    if venue is None and item.get("room_code"):
        venue = (
            venue_model.objects.using(using)
            .filter(building=building, room_code__iexact=item["room_code"])
            .order_by("pk")
            .first()
        )
    if venue is None:
        candidate_names = {
            normalize_venue_text(previous_name),
            normalize_venue_text(item["name"]),
        }
        venue = (
            venue_model.objects.using(using)
            .filter(
                building=building,
                code__isnull=True,
                normalized_name__in=candidate_names,
            )
            .order_by("pk")
            .first()
        )
    if venue is None:
        venue = venue_model(building=building)

    venue.code = item["code"]
    venue.building = building
    venue.name = item["name"]
    venue.normalized_name = normalize_venue_text(item["name"])
    venue.floor = item.get("floor", "")
    venue.room_code = item.get("room_code", "")
    venue.venue_type = item["venue_type"]
    venue.capacity = item.get("capacity")
    venue.source_url = source_url
    venue.verified_at = verified_at
    venue.is_verified = True
    if _model_has_field(venue_model, "level_code"):
        venue.level_code = item.get("level_code", "")
    if _model_has_field(venue_model, "bookable_by_staff"):
        venue.bookable_by_staff = item.get("bookable_by_staff")
        venue.bookable_by_student_organisations = item.get("bookable_by_student_organisations")
    venue.save(using=using)

    desired_aliases = {
        normalize_venue_text(alias["value"]): alias for alias in item.get("aliases", [])
    }
    alias_model.objects.using(using).filter(venue=venue, is_verified=True).exclude(
        normalized_alias__in=desired_aliases
    ).update(is_verified=False)
    for normalized_alias, alias in desired_aliases.items():
        # The reviewed catalog is globally unambiguous. Retire a legacy seed's
        # previous owner before assigning the alias to its current canonical venue.
        alias_model.objects.using(using).filter(
            normalized_alias=normalized_alias,
            is_verified=True,
        ).exclude(venue=venue).update(is_verified=False)
        alias_model.objects.using(using).update_or_create(
            venue=venue,
            normalized_alias=normalized_alias,
            defaults={
                "alias": alias["value"],
                "match_type": alias["match_type"],
                "confidence": 1,
                "is_verified": True,
                "source_url": source_url,
                "verified_at": verified_at,
            },
        )
    return venue


def _validate_aliases(aliases, owner_code: str, verified_aliases: dict[str, str]) -> None:
    for alias in aliases:
        value = _required_text(alias, "value")
        _required_text(alias, "match_type")
        normalized = normalize_venue_text(value)
        previous_owner = verified_aliases.get(normalized)
        if previous_owner is not None and previous_owner != owner_code:
            raise ValueError(
                f"Verified alias {value!r} is ambiguous between {previous_owner} and {owner_code}."
            )
        verified_aliases[normalized] = owner_code


def _require_source(item: dict[str, Any], sources: dict[str, Any]) -> None:
    source = _required_text(item, "source")
    if source not in sources:
        raise ValueError(f"Unknown venue catalog source: {source}")
    _required_text(sources[source], "url")


def _required_text(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Venue catalog field {key!r} must be non-empty text.")
    return value


def _model_has_field(model, field_name: str) -> bool:
    # Historical migration models can omit newer catalog fields.
    return any(field.name == field_name for field in model._meta.get_fields())
