import json
from pathlib import Path

import pytest
from ingestion.canonicalization.plans.validation.references import validate_venue_ids
from ingestion.canonicalization.workflow import canonicalize_candidate, update_canonicalization_plan
from ingestion.contracts import AttendanceMode
from ingestion.models import CanonicalizationPlanStatus
from venues.models import Venue

from tests.backend.ingestion.canonicalization.canonicalization_test_support import (
    complete_payload,
    make_candidate,
    update_description_proposal,
)

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("raw", "suggested_code", "expected"),
    [
        ("Outside LT2A & CCDS Foyer Lvl 1", "NS_LT1A", {"NS_LT2A", "N4"}),
        ("Hall 11 Reading Room", None, {"HALL11"}),
        ("RR", "HALL11", set()),
        ("the Pavilion near TCT LT", "NS_TCT_LT", set()),
    ],
)
def test_automatic_locations_correct_suggestions_without_changing_evidence(
    raw, suggested_code, expected
):
    payload = complete_payload()
    payload.occurrences[0].attendance_mode = AttendanceMode.IN_PERSON
    payload.occurrences[0].meeting_url = None
    payload.occurrences[0].raw_location = raw
    ids = [Venue.objects.get(code=suggested_code).pk] if suggested_code else []
    payload.occurrences[0].suggested_venue_ids = ids
    candidate = make_candidate(payload)
    original = candidate.extracted_payload
    plan = canonicalize_candidate(candidate.pk, expected_version=candidate.edit_version)
    assert plan.status == CanonicalizationPlanStatus.APPLIED
    occurrence = plan.target_event.occurrences.get()
    assert set(occurrence.venues.values_list("code", flat=True)) == expected
    assert occurrence.raw_location_text == raw
    candidate.refresh_from_db()
    assert candidate.extracted_payload == candidate.effective_payload == original
    assert plan.generated_proposal["add_event"]["occurrences"][0]["venue_ids"] == ids
    assert any(flag["code"] == "VENUE_RESOLUTION_CHANGED" for flag in plan.grounding_flags)


def test_description_update_preserves_the_owners_existing_location():
    candidate = make_candidate(complete_payload())
    first = canonicalize_candidate(candidate.pk, expected_version=candidate.edit_version)
    event = first.target_event
    occurrence = event.occurrences.get()
    occurrence.raw_location_text = "Owner-reviewed reading room"
    occurrence.attendance_mode = AttendanceMode.IN_PERSON
    occurrence.save()
    occurrence.venues.add(Venue.objects.get(code="HALL11"))
    next_candidate = make_candidate(complete_payload(), identity="follow-up")
    plan = canonicalize_candidate(
        next_candidate.pk,
        expected_version=next_candidate.edit_version,
        decision=update_description_proposal(event.pk, "Updated description"),
    )
    assert plan.status == CanonicalizationPlanStatus.APPLIED
    occurrence.refresh_from_db()
    assert occurrence.raw_location_text == "Owner-reviewed reading room"
    assert list(occurrence.venues.values_list("code", flat=True)) == ["HALL11"]


def test_owner_can_repair_an_unapplied_plan_without_automatic_remapping():
    payload = complete_payload()
    payload.occurrences[0].attendance_mode = AttendanceMode.IN_PERSON
    payload.occurrences[0].raw_location = "Reading Room (RR)"
    candidate = make_candidate(payload)
    plan = canonicalize_candidate(
        candidate.pk, expected_version=candidate.edit_version, apply_ready=False
    )
    repaired = plan.effective_proposal
    repaired["add_event"]["occurrences"][0]["venue_ids"] = [Venue.objects.get(code="HALL11").pk]
    plan = update_canonicalization_plan(
        plan.pk, expected_version=plan.plan_version, effective_proposal=repaired
    )
    assert plan.status == CanonicalizationPlanStatus.APPLIED
    assert list(plan.target_event.occurrences.get().venues.values_list("code", flat=True)) == [
        "HALL11"
    ]


def test_application_rejects_places_removed_from_the_reviewed_registry():
    venue = Venue.objects.get(code="HALL11")
    venue.building.is_active = False
    venue.building.save(update_fields=["is_active"])
    issues = []
    validate_venue_ids([venue.pk], issues)
    assert [issue["code"] for issue in issues] == ["VENUE_NOT_REVIEWED"]


def test_reviewed_source_inventory_preserves_each_location_without_guessing():
    fixture = Path(__file__).resolve().parents[4] / "fixtures/sources/telegram/locations.json"
    cases = json.loads(fixture.read_text(encoding="utf-8"))["cases"]
    for index, case in enumerate(cases):
        payload = complete_payload()
        payload.source_url = case["source_url"]
        occurrence = payload.occurrences[0]
        occurrence.attendance_mode = AttendanceMode.IN_PERSON
        occurrence.meeting_url = None
        occurrence.raw_location = case["location"]
        candidate = make_candidate(payload, identity=f"location-case-{index}")
        plan = canonicalize_candidate(
            candidate.pk, expected_version=candidate.edit_version, precomputed_matches=[]
        )
        assert plan.status == CanonicalizationPlanStatus.APPLIED, case["location"]
        canonical = plan.target_event.occurrences.get()
        assert canonical.raw_location_text == case["location"]
        assert set(canonical.venues.values_list("code", flat=True)) == set(
            case["expected_codes"]
        ), case["location"]
