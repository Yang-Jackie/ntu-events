from __future__ import annotations

import argparse
import html
import json
import re
import urllib.request
from collections import Counter
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "apps" / "backend" / "venues" / "catalog.json"
FACILITIES_PATH = ROOT / "apps" / "backend" / "venues" / "facilities.json"

CENTRAL_SOURCE = "ntu_facilities"
NBS_SOURCE = "nbs_facilities"

REMOVED_ORGANIZATION_VENUES = {
    "NS_CCEB_ND",
    "NS_CCDS",
    "NS_CEE",
    "NS_MAE",
    "NS_MSE",
}

ROOM_PARENT_OVERRIDES = {
    # NTU's official facilities page identifies this as the Block N4.1 MSE lab
    # even though the retained room identifier begins with N4.
    "N4-B4B-13": "N4.1",
}

PREFIX_PARENTS = {
    "ABS": "WCYP",
    "ABN": "ABN",
    "ART": "ADM",
    "CHC": "CHC",
    "CS": "WKWSCI",
    "EMB": "EMB",
    "LHN": "LHN",
    "LHS": "LHS",
    "N1": "N1",
    "N1.2": "N1.2",
    "N1.3": "N1.3",
    "N2": "N2",
    "N3": "N3",
    "N4": "N4",
    "N4.1": "N4.1",
    "NS1": "NS1",
    "NS2": "NS2",
    "NS3": "NS3",
    "NS4": "NS4",
    "S1": "S1",
    "S2": "S2",
    "S3": "S3",
    "S3.1": "S3.1",
    "S3.2": "S3.2",
    "S4": "S4",
    "SBS": "SBS",
    "SHHK": "SHHK",
    "SPMS": "SPMS",
    "SS1": "SS1",
    "SS2": "SS2",
    "SS3": "SS3",
    "SS4": "SS4",
    "WKWSCI": "WKWSCI",
}


class TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        del attrs
        if tag.casefold() == "tr":
            self._row = []
        elif tag.casefold() in {"td", "th"} and self._row is not None:
            self._cell = []
        elif tag.casefold() == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in {"td", "th"} and self._cell is not None:
            assert self._row is not None
            self._row.append(_clean_text("".join(self._cell)))
            self._cell = None
        elif tag.casefold() == "tr" and self._row is not None:
            if any(self._row):
                self.rows.append(self._row)
            self._row = None


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Refresh the reviewed NTU public facilities snapshot."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate that regeneration produces no diff instead of writing files.",
    )
    args = parser.parse_args()

    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    _normalize_catalog(catalog)

    central_rows = _fetch_rows(catalog["sources"][CENTRAL_SOURCE]["url"])
    nbs_rows = _fetch_rows(catalog["sources"][NBS_SOURCE]["url"])
    facilities = _build_facilities(central_rows, nbs_rows)

    catalog_text = _json_text(catalog)
    facilities_text = _json_text(facilities)
    if args.check:
        changed = []
        if CATALOG_PATH.read_text(encoding="utf-8") != catalog_text:
            changed.append(str(CATALOG_PATH.relative_to(ROOT)))
        if (
            not FACILITIES_PATH.exists()
            or FACILITIES_PATH.read_text(encoding="utf-8") != facilities_text
        ):
            changed.append(str(FACILITIES_PATH.relative_to(ROOT)))
        if changed:
            raise SystemExit("Venue facility snapshots are stale: " + ", ".join(changed))
        print(f"Venue facility snapshots are current ({len(facilities['venues'])} facilities).")
        return

    CATALOG_PATH.write_text(catalog_text, encoding="utf-8")
    FACILITIES_PATH.write_text(facilities_text, encoding="utf-8")
    print(
        "Updated venue catalog structure and "
        f"{len(facilities['venues'])} official facility records."
    )


def _fetch_rows(url: str) -> list[list[str]]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "ntu-events-venue-research/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        document = response.read().decode("windows-1252")
    parser = TableParser()
    parser.feed(document)
    return parser.rows


def _normalize_catalog(catalog: dict) -> None:
    catalog["venues"] = [
        venue for venue in catalog["venues"] if venue["code"] not in REMOVED_ORGANIZATION_VENUES
    ]
    for building in catalog["buildings"]:
        building.setdefault("location_kind", _location_kind(building["venue_type"]))
        if building["code"] == "NIE":
            building["location_kind"] = "COMPLEX"
        elif building["code"].startswith("NIE_") or building["code"] == "NYP":
            building.setdefault("parent_code", "NIE")
    for venue in catalog["venues"]:
        if venue["venue_type"] == "CLASSROOM" and (
            "tr+" in venue["name"].casefold() or "tutorial room" in venue["name"].casefold()
        ):
            venue["venue_type"] = "TUTORIAL_ROOM"
        room_code = venue.get("room_code")
        if not room_code:
            continue
        venue["building_code"] = _parent_code(room_code, venue["building_code"])
        level_code, floor = _level_parts(room_code)
        venue["level_code"] = level_code
        venue["floor"] = floor


def _build_facilities(central_rows: list[list[str]], nbs_rows: list[list[str]]) -> dict:
    candidates: list[dict] = []
    for row in central_rows:
        if len(row) != 6 or row[0].casefold() in {"spines", ""}:
            continue
        spine, facility, capacity, location, staff, students = row
        room_code = _room_code(location)
        if not room_code or not capacity.isdigit():
            continue
        level_code, floor = _level_parts(room_code)
        candidates.append(
            {
                "code": f"FBS_CENTRAL_{_slug(spine)}_{_slug(facility)}",
                "building_code": _parent_code(room_code, _central_fallback(spine)),
                "name": facility,
                "venue_type": _venue_type(facility),
                "floor": floor,
                "level_code": level_code,
                "room_code": room_code,
                "capacity": int(capacity),
                "bookable_by_staff": staff == "YES",
                "bookable_by_student_organisations": students == "YES",
                "source": CENTRAL_SOURCE,
                "aliases": [
                    {
                        "value": f"{_spine_label(spine)} {facility}",
                        "match_type": "OBSERVED",
                    }
                ],
            }
        )

    for row in nbs_rows:
        if len(row) != 8 or row[0].casefold() in {"spine", ""}:
            continue
        spine, short_name, capacity, address, full_name, *_charges = row
        room_code = _room_code(address)
        if not room_code or not capacity.isdigit():
            continue
        level_code, floor = _level_parts(room_code)
        display_name = _display_name(full_name or short_name)
        aliases = [
            {"value": short_name, "match_type": "ABBREVIATION"},
        ]
        if full_name and _clean_text(full_name).casefold() != display_name.casefold():
            aliases.append({"value": full_name, "match_type": "OBSERVED"})
        candidates.append(
            {
                "code": f"FBS_NBS_{_slug(spine)}_{_slug(short_name)}",
                "building_code": _parent_code(room_code, spine),
                "name": display_name,
                "venue_type": _venue_type(f"{short_name} {full_name}"),
                "floor": floor,
                "level_code": level_code,
                "room_code": room_code,
                "capacity": int(capacity),
                "source": NBS_SOURCE,
                "aliases": aliases,
            }
        )

    room_code_counts = Counter(item["room_code"].casefold() for item in candidates)
    alias_counts = Counter(
        _normalize(alias["value"]) for item in candidates for alias in item["aliases"]
    )
    for item in candidates:
        item["aliases"] = [
            alias for alias in item["aliases"] if alias_counts[_normalize(alias["value"])] == 1
        ]
        if room_code_counts[item["room_code"].casefold()] == 1:
            item["aliases"].append({"value": item["room_code"], "match_type": "EXACT"})

    candidates.sort(key=lambda item: (item["building_code"], item["room_code"], item["code"]))
    return {
        "snapshot_version": 1,
        "generated_on": date.today().isoformat(),
        "scope": "Official public NTU central and NBS event/teaching facilities",
        "sources": [CENTRAL_SOURCE, NBS_SOURCE],
        "venues": candidates,
    }


def _location_kind(venue_type: str) -> str:
    return {
        "AUDITORIUM": "FACILITY",
        "HALL": "HALL",
        "LIBRARY": "FACILITY",
        "OUTDOOR": "OUTDOOR",
        "SPORTS_FACILITY": "FACILITY",
    }.get(venue_type, "BUILDING")


def _parent_code(room_code: str, fallback: str) -> str:
    if room_code in ROOM_PARENT_OVERRIDES:
        return ROOM_PARENT_OVERRIDES[room_code]
    prefix = room_code.split("-", 1)[0].upper()
    if prefix.startswith("LT") and prefix.endswith("A"):
        return "NS"
    return PREFIX_PARENTS.get(prefix, fallback)


def _central_fallback(spine: str) -> str:
    return {
        "NORTH SPINE": "NS",
        "SCI BUILDING": "WKWSCI",
        "SOUTH SPINE": "SS",
        "THE ARC": "LHN",
    }.get(spine, "NS")


def _level_parts(room_code: str) -> tuple[str, str]:
    parts = room_code.split("-")
    if len(parts) < 2:
        return "", ""
    level_code = "-".join(parts[:2])
    return level_code, parts[1]


def _room_code(location: str) -> str:
    return location.strip().split(maxsplit=1)[0].rstrip(",").upper()


def _venue_type(label: str) -> str:
    value = label.casefold()
    if "lecture theatre" in value or re.search(r"(^|[- ])lt(?:$|\d)", value):
        return "LECTURE_THEATRE"
    if "tutorial" in value or "tr+" in value or re.search(r"(^|[- ])tr(?:x|\d)", value):
        return "TUTORIAL_ROOM"
    if "seminar" in value or re.search(r"(^|[- ])sr\d", value):
        return "SEMINAR_ROOM"
    if "comput" in value:
        return "COMPUTING_ROOM"
    if "laboratory" in value or " lab" in value or "collab" in value:
        return "LABORATORY"
    if "auditorium" in value or " audi" in value:
        return "AUDITORIUM"
    if "discussion" in value:
        return "DISCUSSION_ROOM"
    if "project room" in value or re.search(r"(^|\s)pr\d", value):
        return "PROJECT_ROOM"
    if "meeting" in value or "conference" in value:
        return "MEETING_ROOM"
    if "studio" in value:
        return "STUDIO"
    if "lounge" in value or "reading room" in value:
        return "FUNCTION_SPACE"
    if any(token in value for token in ("foyer", "function", "exhib", "recep")):
        return "FUNCTION_SPACE"
    return "CLASSROOM"


def _display_name(value: str) -> str:
    if not value.isupper():
        return value
    result = value.title()
    for source, target in {
        "Abs": "ABS",
        "Csi": "CSI",
        "It ": "IT ",
        "S3 ": "S3 ",
        "S4 ": "S4 ",
    }.items():
        result = result.replace(source, target)
    return result


def _spine_label(value: str) -> str:
    return {
        "NORTH SPINE": "North Spine",
        "SCI BUILDING": "WKWSCI",
        "SOUTH SPINE": "South Spine",
        "THE ARC": "The Arc",
    }.get(value, value.title())


def _slug(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", value.upper()).strip("_")


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _clean_text(value: str) -> str:
    return " ".join(html.unescape(value).replace("\xa0", " ").split())


def _json_text(value: dict) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


if __name__ == "__main__":
    main()
