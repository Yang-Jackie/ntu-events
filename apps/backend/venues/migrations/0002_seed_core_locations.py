from datetime import UTC, datetime

from django.db import migrations

SOURCE_URL = "https://maps.ntu.edu.sg/"
VERIFIED_AT = datetime(2026, 7, 30, tzinfo=UTC)

CORE_LOCATIONS = [
    ("NS", "North Spine", "MAIN", "BUILDING"),
    ("SS", "South Spine", "MAIN", "BUILDING"),
    ("ADMIN", "Administration Building", "MAIN", "BUILDING"),
    ("NYA", "Nanyang Auditorium", "MAIN", "AUDITORIUM"),
    ("SSC", "Student Services Centre", "MAIN", "BUILDING"),
    ("UHS", "University Health Service", "MAIN", "BUILDING"),
    ("RTP", "Research TechnoPlaza", "MAIN", "BUILDING"),
    ("EMB", "Experimental Medicine Building", "MAIN", "BUILDING"),
    ("SBS", "School of Biological Sciences", "MAIN", "BUILDING"),
    ("SPMS", "School of Physical and Mathematical Sciences", "MAIN", "BUILDING"),
    (
        "WKWSCI",
        "Wee Kim Wee School of Communication and Information",
        "MAIN",
        "BUILDING",
    ),
    ("SOH", "School of Humanities", "MAIN", "BUILDING"),
    ("SSS", "School of Social Sciences", "MAIN", "BUILDING"),
    ("ADM", "School of Art, Design and Media", "MAIN", "BUILDING"),
    ("LHS", "The Hive", "MAIN", "BUILDING"),
    ("LHN", "The Arc", "MAIN", "BUILDING"),
    ("WAVE", "The Wave", "MAIN", "SPORTS_FACILITY"),
    ("GAIA", "Gaia", "MAIN", "BUILDING"),
    ("UOBIH", "UOB Innovation Hub", "MAIN", "BUILDING"),
    ("NYP", "Nanyang Playhouse", "MAIN", "BUILDING"),
    ("NEC", "Nanyang Executive Centre", "MAIN", "BUILDING"),
    ("NYH", "Nanyang House", "MAIN", "BUILDING"),
    ("CHC", "Chinese Heritage Centre", "MAIN", "BUILDING"),
    ("SRC", "Sports and Recreation Centre", "MAIN", "SPORTS_FACILITY"),
    ("YG", "Yunnan Garden", "MAIN", "OUTDOOR"),
    ("WCYP", "Wee Cho Yaw Plaza", "MAIN", "OUTDOOR"),
    *[(f"HALL{number}", f"Hall {number}", "MAIN", "HALL") for number in range(1, 17)],
    ("CRESCENT", "Crescent Hall", "MAIN", "HALL"),
    ("PIONEER", "Pioneer Hall", "MAIN", "HALL"),
    ("BINJAI", "Binjai Hall", "MAIN", "HALL"),
    ("TANJONG", "Tanjong Hall", "MAIN", "HALL"),
    ("BANYAN", "Banyan Hall", "MAIN", "HALL"),
    ("TAMARIND", "Tamarind Hall", "MAIN", "HALL"),
    ("SARACA", "Saraca Hall", "MAIN", "HALL"),
    ("NIE", "National Institute of Education", "NIE", "BUILDING"),
    ("NIE_LIBRARY", "NIE Library", "NIE", "BUILDING"),
]

ALIASES = {
    "NS": ["NS", "North Academic Complex"],
    "SS": ["SS", "South Academic Complex"],
    "ADMIN": ["Admin Building"],
    "NYA": ["NYA"],
    "RTP": ["RTP"],
    "EMB": ["EMB"],
    "SBS": ["SBS"],
    "SPMS": ["SPMS"],
    "WKWSCI": ["WKWSCI", "SCI Building"],
    "SOH": ["SoH"],
    "SSS": ["SSS"],
    "ADM": ["ADM"],
    "LHS": ["LHS", "Learning Hub South"],
    "LHN": ["LHN", "Learning Hub North"],
    "GAIA": ["ABS", "Academic Building South"],
    "UOBIH": ["Innovation Centre", "Innovation Center"],
    "SRC": ["SRC"],
    "CHC": ["CHC"],
}


def normalize(value):
    return " ".join(value.casefold().split())


def seed_core_locations(apps, schema_editor):
    del schema_editor
    building_model = apps.get_model("venues", "Building")
    venue_model = apps.get_model("venues", "Venue")
    alias_model = apps.get_model("venues", "VenueAlias")

    venues_by_code = {}
    for code, name, campus_area, venue_type in CORE_LOCATIONS:
        building, _created = building_model.objects.update_or_create(
            code=code,
            defaults={
                "name": name,
                "normalized_name": normalize(name),
                "campus_area": campus_area,
                "official_map_url": SOURCE_URL,
                "source_url": SOURCE_URL,
                "verified_at": VERIFIED_AT,
                "is_active": True,
            },
        )
        venue, _created = venue_model.objects.update_or_create(
            building=building,
            normalized_name=normalize(name),
            defaults={
                "name": name,
                "venue_type": venue_type,
                "source_url": SOURCE_URL,
                "verified_at": VERIFIED_AT,
                "is_verified": True,
            },
        )
        venues_by_code[code] = venue

    for code, aliases in ALIASES.items():
        venue = venues_by_code[code]
        for alias in aliases:
            alias_model.objects.update_or_create(
                venue=venue,
                normalized_alias=normalize(alias),
                defaults={
                    "alias": alias,
                    "match_type": "ABBREVIATION",
                    "confidence": 1,
                    "is_verified": True,
                },
            )


def remove_core_locations(apps, schema_editor):
    del schema_editor
    codes = [code for code, _name, _area, _type in CORE_LOCATIONS]
    building_model = apps.get_model("venues", "Building")
    venue_model = apps.get_model("venues", "Venue")
    alias_model = apps.get_model("venues", "VenueAlias")

    venues = venue_model.objects.filter(building__code__in=codes)
    alias_model.objects.filter(venue__in=venues).delete()
    venues.delete()
    building_model.objects.filter(code__in=codes).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("venues", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_core_locations, remove_core_locations),
    ]
