from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from django.contrib.gis.geos import Point
from django.db import DEFAULT_DB_ALIAS, transaction

from .catalog import load_catalog

GEOGRAPHY_PATH = Path(__file__).with_name("geography.json")
POSITIONING_METHODS = {
    "MAPPED_POINT",
    "GEOMETRY_CENTER",
    "PARENT_ANCHOR",
    "DERIVED_CENTER",
    "TEMPORARY_SITE",
}
NTU_BOUNDS = {
    "minimum_latitude": 1.32,
    "maximum_latitude": 1.37,
    "minimum_longitude": 103.66,
    "maximum_longitude": 103.71,
}


def load_geography(path: Path = GEOGRAPHY_PATH) -> dict[str, Any]:
    geography = json.loads(path.read_text(encoding="utf-8"))
    validate_geography(geography)
    return geography


def validate_geography(geography: dict[str, Any]) -> None:
    if geography.get("geography_version") != 1:
        raise ValueError("Unsupported venue geography version.")

    sources = geography.get("sources")
    buildings = geography.get("buildings")
    if not isinstance(sources, dict) or not isinstance(buildings, list):
        raise ValueError("Venue geography sources and buildings are required.")

    catalog_codes = {item["code"] for item in load_catalog()["buildings"]}
    geography_codes: set[str] = set()
    for item in buildings:
        code = _required_text(item, "code")
        if code in geography_codes:
            raise ValueError(f"Duplicate geography building code: {code}")
        if code not in catalog_codes:
            raise ValueError(f"Unknown geography building code: {code}")
        geography_codes.add(code)

        source = _required_text(item, "source")
        if source not in sources:
            raise ValueError(f"Unknown geography source for {code}: {source}")
        _required_text(sources[source], "url")
        _required_text(sources[source], "license_url")
        _required_text(sources[source], "attribution")
        _required_text(item, "source_identifier")
        _required_text(item, "source_url")

        method = _required_text(item, "positioning_method")
        if method not in POSITIONING_METHODS:
            raise ValueError(f"Unknown positioning method for {code}: {method}")

        latitude = _required_number(item, "latitude")
        longitude = _required_number(item, "longitude")
        if not NTU_BOUNDS["minimum_latitude"] <= latitude <= NTU_BOUNDS["maximum_latitude"]:
            raise ValueError(f"Latitude is outside the reviewed NTU/NIE bounds for {code}.")
        if not (NTU_BOUNDS["minimum_longitude"] <= longitude <= NTU_BOUNDS["maximum_longitude"]):
            raise ValueError(f"Longitude is outside the reviewed NTU/NIE bounds for {code}.")

    missing = catalog_codes - geography_codes
    if missing:
        raise ValueError(f"Venue geography is missing reviewed building codes: {sorted(missing)}")


def sync_geography(*, building_model=None, using: str = DEFAULT_DB_ALIAS) -> dict[str, int]:
    if building_model is None:
        from .models import Building

        building_model = Building

    geography = load_geography()
    verified_at = datetime.fromisoformat(geography["verified_at"])

    with transaction.atomic(using=using):
        updated = 0
        for item in geography["buildings"]:
            point = Point(item["longitude"], item["latitude"], srid=4326)
            count = (
                building_model.objects.using(using)
                .filter(code=item["code"])
                .update(
                    map_point=point,
                    map_source_identifier=item["source_identifier"],
                    map_source_url=item["source_url"],
                    map_positioning_method=item["positioning_method"],
                    map_verified_at=verified_at,
                )
            )
            if count != 1:
                raise ValueError(
                    f"Expected one catalog building for geography code {item['code']}."
                )
            updated += count

    return {"buildings": updated}


def _required_text(item: dict[str, Any], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Venue geography field {key!r} must be non-empty text.")
    return value


def _required_number(item: dict[str, Any], key: str) -> float:
    value = item.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"Venue geography field {key!r} must be a number.")
    return float(value)
