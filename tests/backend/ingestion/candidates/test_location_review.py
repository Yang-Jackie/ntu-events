import pytest
from ingestion.candidates.location_review import review_locations
from ingestion.canonicalization.workflow import canonicalize_candidate
from ingestion.contracts import AttendanceMode
from venues.models import Venue

from tests.backend.ingestion.canonicalization.canonicalization_test_support import (
    complete_payload,
    make_candidate,
)

pytestmark = pytest.mark.django_db


def test_review_lists_unknown_terms_and_links_without_changing_data():
    payload = complete_payload()
    payload.occurrences[0].attendance_mode = AttendanceMode.IN_PERSON
    payload.occurrences[0].raw_location = "Reading Room (RR)"
    payload.occurrences[0].suggested_venue_ids = [Venue.objects.get(code="HALL11").pk]
    candidate = make_candidate(payload)
    plan = canonicalize_candidate(candidate.pk, expected_version=candidate.edit_version)
    before = plan.target_event.occurrences.get().raw_location_text
    rows = review_locations(source_ids=[candidate.source_representation.source_id])
    assert len(rows) == 1
    assert rows[0]["needs_review"] is True
    assert rows[0]["resolved_venue_codes"] == []
    assert rows[0]["candidate_ids"] == [candidate.pk]
    assert rows[0]["event_ids"] == [plan.target_event_id]
    assert rows[0]["source_urls"] == [candidate.source_representation.source_url]
    assert plan.target_event.occurrences.get().raw_location_text == before
    assert review_locations(source_ids=[999999]) == []
