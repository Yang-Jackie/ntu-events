import pytest
from venues.models import Venue
from venues.resolution import VenueResolver

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("text", "codes"),
    [
        ("The Hive", {"LHS"}),
        ("Hall 11 Reading Room", {"HALL11"}),
        ("HALL 10 FUNCTION HALL", {"HALL10"}),
        ("NTU Hall 10 Function Hall", {"HALL10"}),
        ("CCDS Foyer, Levels 2 & 3", {"N4"}),
        ("CCDS L2", {"N4"}),
        ("Outside LT2A & CCDS Foyer Lvl 1", {"NS_LT2A", "N4"}),
        ("LHN-TR12 (Arc)", {"FBS_CENTRAL_THE_ARC_LHN_TR_12"}),
        ("LT17 (North Spine)", {"FBS_CENTRAL_NORTH_SPINE_LT17"}),
        ("LHN-TR+31", {"FBS_CENTRAL_THE_ARC_LHN_TR_31"}),
        ("LHN-TR+37, The Arc, NTU", {"FBS_CENTRAL_THE_ARC_LHN_TR_37"}),
        ("Innovation Port @ The Arc", {"LHN_INNOVATION_PORT"}),
        ("Gaia Innovation Port", {"WCYP_INNOVATION_PORT"}),
        ("NiCE 3, Research Techno Plaza, Level 4", {"RTP"}),
        ("MLDA@EEE (S2.1-B4-01)", set()),
        ("LT17 (The Arc)", {"LHN"}),
        ("Not at Hall 11", set()),
        ("Hall 10 or Hall 11", set()),
        ("Hall 11, room TBC", set()),
        ("LT1", set()),
        ("RR", set()),
        ("Reading Room (RR)", set()),
        ("the Pavilion near TCT LT", set()),
        ("on campus", set()),
        ("NTU", set()),
        ("TBA", set()),
        ("Marina Bay Sands", set()),
    ],
)
def test_real_source_location_wording(text, codes):
    resolver = VenueResolver()
    result = resolver.resolve(text)
    assert {resolver.venues[pk].code for pk in result.venue_ids} == codes


def test_unknown_room_code_does_not_match_another_block_prefix():
    assert VenueResolver().resolve("S2.1-B4-01").venue_ids == ()


def test_unverified_or_retired_places_cannot_resolve():
    retired = Venue.objects.get(code="WCYP")
    retired.building.is_active = False
    retired.building.save(update_fields=["is_active"])
    assert retired.pk not in VenueResolver().venues
    assert VenueResolver().resolve("Gaia").venue_ids == ()
    place = Venue.objects.get(code="HALL11")
    place.is_verified = False
    place.save(update_fields=["is_verified"])
    assert VenueResolver().resolve("Hall 11 Reading Room").venue_ids == ()
