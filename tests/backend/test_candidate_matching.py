from datetime import date
from decimal import Decimal

import pytest
from events.models import Event
from ingestion.canonicalization import find_candidate_matches
from ingestion.canonicalization.matching import _date_similarity, normalize_match_url
from ingestion.contracts import (
    CandidateOrganizer,
    CandidateRegistration,
    EventCandidatePayload,
    RegistrationScope,
)
from ingestion.models import CandidateMatch, CanonicalizationPlanStatus
from organizers.models import Organizer
from venues.models import Venue, VenueType

from .canonicalization_test_support import (
    canonicalize_new_candidate,
    complete_payload,
    make_candidate,
)

pytestmark = pytest.mark.django_db


def test_match_without_a_decision_creates_a_review_required_plan() -> None:
    first = canonicalize_new_candidate(make_candidate(complete_payload(), identity="message-1"))
    event = first.canonicalization_plan.target_event
    second = canonicalize_new_candidate(make_candidate(complete_payload(), identity="message-2"))

    plan = second.canonicalization_plan
    assert plan.status == CanonicalizationPlanStatus.REVIEW_REQUIRED
    assert plan.action == ""
    assert CandidateMatch.objects.get(event_candidate=second).event == event
    assert Event.objects.count() == 1


def test_sparse_follow_up_title_is_matched_by_normalized_percentage() -> None:
    announcement = complete_payload()
    announcement.title = "Introduction to Git and GitHub"
    first = canonicalize_new_candidate(make_candidate(announcement, identity="message-88"))
    event = first.canonicalization_plan.target_event
    follow_up = EventCandidatePayload(
        title="Introduction to Git and GitHub — sign-up reminder",
        description="Please sign up for the workshop.",
        registrations=[
            CandidateRegistration(
                scope=RegistrationScope.EVENT,
                name="Sign-up form",
                url="https://forms.example/github-workshop",
            )
        ],
    )

    review = canonicalize_new_candidate(make_candidate(follow_up, identity="message-89"))

    match = CandidateMatch.objects.get(event_candidate=review)
    assert match.event == event
    assert match.score >= Decimal("0.3000")
    summary = match.signals[0]
    assert summary["kind"] == "MATCH_SUMMARY"
    assert summary["match_percentage"] >= 30
    assert "TITLE_SIMILARITY" in summary["evidence_signals"]
    plan = review.canonicalization_plan
    assert plan.status == CanonicalizationPlanStatus.REVIEW_REQUIRED
    assert plan.match_snapshot[0]["match_percentage"] >= 30
    assert "score" not in plan.match_snapshot[0]


def test_match_score_is_a_fixed_sum_without_an_available_field_denominator() -> None:
    Event.objects.create(
        slug="indexed-event",
        title="Indexed event",
        normalized_title="indexed event",
        description="Canonical description",
    )
    payload = EventCandidatePayload(
        title="Indexed event",
        description="Candidate description",
        registrations=[
            CandidateRegistration(
                scope=RegistrationScope.EVENT,
                url="https://forms.example/new-only",
            )
        ],
    )
    review = make_candidate(payload, identity="indexed-candidate")

    match = find_candidate_matches(review, payload)[0]

    assert Decimal(str(match.score)) == Decimal("0.6500")
    signals = {signal["kind"]: signal for signal in match.signals}
    assert signals["TITLE"]["contribution_percentage"] == 65
    assert signals["REGISTRATION_URL"]["contribution_percentage"] == 0
    assert signals["SOURCE"]["contribution_percentage"] == 0
    assert "comparable_weight_percentage" not in signals["MATCH_SUMMARY"]


def test_moderate_title_similarity_plus_same_date_qualifies_without_an_identity_gate() -> None:
    announcement = complete_payload()
    announcement.title = "Leather workshop — make your own leather card holder"
    first = canonicalize_new_candidate(make_candidate(announcement, identity="message-1"))
    event = first.canonicalization_plan.target_event
    reminder = complete_payload()
    reminder.title = "Leather Card Holder workshop — same-day reminder"
    candidate = make_candidate(reminder, identity="message-2")

    matches = find_candidate_matches(candidate, reminder)

    assert matches
    assert matches[0].event == event
    assert matches[0].score >= Decimal("0.3000")


def test_dates_at_least_120_days_apart_contribute_negative_twenty_points() -> None:
    assert _date_similarity({date(2026, 1, 1)}, {date(2026, 5, 1)}) == -2.0
    assert _date_similarity({date(2026, 1, 1)}, {date(2026, 4, 30)}) == 0.0


def test_registration_url_normalization_ignores_scheme_www_and_trailing_slash() -> None:
    assert normalize_match_url("http://www.example.com/register/") == normalize_match_url(
        "https://example.com/register"
    )


def test_only_the_five_highest_percentage_matches_are_stored() -> None:
    for index in range(7):
        Event.objects.create(
            slug=f"indexed-event-{index}",
            title="Indexed event",
            normalized_title="indexed event",
            description=f"Canonical description {index}",
        )
    payload = EventCandidatePayload(
        title="Indexed event",
        description="Candidate description",
    )
    review = make_candidate(payload, identity="top-five")

    matches = find_candidate_matches(review, payload)

    assert len(matches) == 5
    assert [match.rank for match in matches] == [1, 2, 3, 4, 5]
    assert {Decimal(str(match.score)) for match in matches} == {Decimal("0.6500")}


def test_non_identity_fields_cannot_qualify_a_match() -> None:
    organizer = Organizer.objects.create(
        name="Shared organizer", normalized_name="shared organizer"
    )
    venue = Venue.objects.create(
        name="Shared venue",
        normalized_name="shared venue",
        venue_type=VenueType.OTHER,
        is_verified=True,
    )
    first_payload = complete_payload()
    first_payload.title = "Robotics design workshop"
    first_payload.organizers = [CandidateOrganizer(name=organizer.name, is_primary=True)]
    first_payload.occurrences[0].suggested_venue_ids = [venue.pk]
    canonicalize_new_candidate(make_candidate(first_payload, identity="robotics"))
    unrelated = complete_payload()
    unrelated.title = "Community garden planning"
    unrelated.organizers = [CandidateOrganizer(name=organizer.name, is_primary=True)]
    unrelated.occurrences[0].suggested_venue_ids = [venue.pk]
    review = make_candidate(unrelated, identity="garden")

    matches = find_candidate_matches(review, unrelated)

    assert matches == []
