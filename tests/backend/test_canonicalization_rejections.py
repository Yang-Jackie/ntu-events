import pytest
from events.models import EventOccurrence, EventOrganizer, EventRevision
from ingestion.canonicalization.plans.validation.proposal import validate_proposal
from ingestion.canonicalization.snapshots import event_snapshot_hash
from ingestion.canonicalization.workflow import canonicalize_candidate
from ingestion.contracts import (
    CandidateOccurrence,
    CanonicalOccurrenceChange,
    CanonicalOrganizerChange,
    CanonicalOrganizerValue,
    CanonicalRegistrationChange,
    ObjectOperation,
    OccurrenceField,
    OrganizerField,
    RegistrationField,
)
from ingestion.models import CandidateStatus, CanonicalizationPlan
from organizers.models import Organizer
from pydantic import ValidationError

from .canonicalization_test_support import (
    canonicalize_new_candidate,
    complete_payload,
    empty_occurrence_value,
    make_candidate,
    update_description_proposal,
)

pytestmark = pytest.mark.django_db


def setup_update():
    original = canonicalize_new_candidate(make_candidate(complete_payload(), identity="original"))
    event = original.canonicalization_plan.target_event
    candidate = make_candidate(complete_payload(), identity="follow-up")
    proposal = update_description_proposal(event.pk, "Follow-up description")
    return event, candidate, proposal


def reject_without_writes(event, candidate, proposal, expected_code):
    before = event_snapshot_hash(event)
    revisions = EventRevision.objects.count()
    plan = canonicalize_candidate(
        candidate.pk, expected_version=candidate.edit_version, decision=proposal
    )
    assert plan.status == "REJECTED"
    assert expected_code in {issue["code"] for issue in plan.validation_issues}
    candidate.refresh_from_db()
    assert candidate.status == CandidateStatus.PROCESSED
    assert event_snapshot_hash(event) == before
    assert EventRevision.objects.count() == revisions
    assert plan.generated_proposal == (
        proposal if isinstance(proposal, dict) else proposal.model_dump(mode="json")
    )
    # A rerun preserves the rejected result rather than retrying or writing twice.
    rerun = canonicalize_candidate(
        candidate.pk, expected_version=candidate.edit_version, decision=proposal
    )
    assert rerun.pk == plan.pk
    assert CanonicalizationPlan.objects.filter(event_candidate=candidate).count() == 1


@pytest.mark.parametrize("kind", ["occurrence", "organizer", "registration"])
@pytest.mark.parametrize("operation", [ObjectOperation.ADD, ObjectOperation.UPDATE])
def test_null_object_value_rejects_plan_and_preserves_event(kind, operation):
    event, candidate, proposal = setup_update()
    adding = operation == ObjectOperation.ADD
    if kind == "occurrence":
        proposal.occurrence_changes = [
            CanonicalOccurrenceChange(
                operation=operation,
                id=None if adding else event.occurrences.get().pk,
                changed_fields=[] if adding else [OccurrenceField.SEQUENCE],
                value=None,
            )
        ]
    elif kind == "organizer":
        organizer = Organizer.objects.create(
            name="Test organizer", normalized_name="test organizer"
        )
        owned = EventOrganizer.objects.create(event=event, organizer=organizer)
        proposal.organizer_changes = [
            CanonicalOrganizerChange(
                operation=operation,
                id=None if adding else owned.pk,
                changed_fields=[] if adding else [OrganizerField.ROLE],
                value=None,
            )
        ]
    else:
        proposal.registration_changes = [
            CanonicalRegistrationChange(
                operation=operation,
                id=None if adding else 999999,
                changed_fields=[] if adding else [RegistrationField.NAME],
                value=None,
            )
        ]
    reject_without_writes(event, candidate, proposal, f"{operation.value}_OBJECT_INVALID")


def test_completed_occurrence_survives_unrelated_update():
    event, candidate, proposal = setup_update()
    occurrence = event.occurrences.get()
    occurrence.occurrence_status = "COMPLETED"
    occurrence.save(update_fields=["occurrence_status"])
    proposal.occurrence_changes = [
        CanonicalOccurrenceChange(
            operation=ObjectOperation.UPDATE,
            id=occurrence.pk,
            changed_fields=[OccurrenceField.LABEL],
            value=empty_occurrence_value(label="Updated label"),
        )
    ]
    plan = canonicalize_candidate(
        candidate.pk, expected_version=candidate.edit_version, decision=proposal
    )
    assert plan.status == "APPLIED", plan.application_error
    occurrence.refresh_from_db()
    assert occurrence.label == "Updated label"
    assert occurrence.occurrence_status == "COMPLETED"


def test_extraction_statuses_are_not_expanded_to_completed():
    with pytest.raises(ValidationError):
        CandidateOccurrence(local_ref="session-1", status="COMPLETED")


def test_schema_invalid_direct_decision_is_retained_as_rejected():
    event, candidate, proposal = setup_update()
    decision = proposal.model_dump(mode="json")
    decision["action"] = "INVALID"
    reject_without_writes(event, candidate, decision, "PROPOSAL_SCHEMA_INVALID")


def test_invalid_owned_id_is_rejected_before_state_projection():
    event, candidate, proposal = setup_update()
    proposal.occurrence_changes = [
        CanonicalOccurrenceChange(
            operation=ObjectOperation.UPDATE,
            id=999999,
            changed_fields=[OccurrenceField.SEQUENCE],
            value=empty_occurrence_value(sequence=2),
        )
    ]
    reject_without_writes(event, candidate, proposal, "CHILD_NOT_FOUND_OR_WRONG_OWNER")


@pytest.mark.parametrize("operation", [ObjectOperation.ADD, ObjectOperation.UPDATE])
@pytest.mark.parametrize("position", [-1, 32768])
def test_out_of_range_organizer_position_is_rejected(operation, position):
    event, candidate, proposal = setup_update()
    organizer = Organizer.objects.create(name="Test organizer", normalized_name="test organizer")
    adding = operation == ObjectOperation.ADD
    owned = None if adding else EventOrganizer.objects.create(event=event, organizer=organizer)
    proposal.organizer_changes = [
        CanonicalOrganizerChange(
            operation=operation,
            id=None if adding else owned.pk,
            changed_fields=[] if adding else [OrganizerField.POSITION],
            value=CanonicalOrganizerValue(
                organizer_id=organizer.pk, role=None, is_primary=False, position=position
            ),
        )
    ]
    reject_without_writes(event, candidate, proposal, "ORGANIZER_POSITION_INVALID")


@pytest.mark.parametrize("operation", [ObjectOperation.ADD, ObjectOperation.UPDATE])
@pytest.mark.parametrize("sequence", [-1, 32768])
def test_out_of_range_occurrence_sequence_is_rejected(operation, sequence):
    event, candidate, proposal = setup_update()
    adding = operation == ObjectOperation.ADD
    value = empty_occurrence_value(sequence=sequence)
    if adding:
        from ingestion.canonicalization.decisions.projection import automatic_add_proposal

        value = automatic_add_proposal(complete_payload()).add_event.occurrences[0]
        value.sequence = sequence
    proposal.occurrence_changes = [
        CanonicalOccurrenceChange(
            operation=operation,
            id=None if adding else event.occurrences.get().pk,
            changed_fields=[] if adding else [OccurrenceField.SEQUENCE],
            value=value,
        )
    ]
    reject_without_writes(event, candidate, proposal, "OCCURRENCE_SEQUENCE_INVALID")


@pytest.mark.parametrize("sequence", [0, 32767])
def test_storage_boundary_sequence_and_subsequent_update_apply(sequence):
    event, candidate, proposal = setup_update()
    occurrence = event.occurrences.get()
    proposal.occurrence_changes = [
        CanonicalOccurrenceChange(
            operation=ObjectOperation.UPDATE,
            id=occurrence.pk,
            changed_fields=[OccurrenceField.SEQUENCE],
            value=empty_occurrence_value(sequence=sequence),
        )
    ]
    plan = canonicalize_candidate(
        candidate.pk, expected_version=candidate.edit_version, decision=proposal
    )
    assert plan.status == "APPLIED", plan.application_error
    next_candidate = make_candidate(complete_payload(), identity="next-update")
    proposal.occurrence_changes[0].changed_fields = [OccurrenceField.LABEL]
    proposal.occurrence_changes[0].value = empty_occurrence_value(label="Updated label")
    next_plan = canonicalize_candidate(
        next_candidate.pk, expected_version=next_candidate.edit_version, decision=proposal
    )
    assert next_plan.status == "APPLIED", next_plan.application_error
    occurrence.refresh_from_db()
    assert occurrence.sequence == sequence
    assert occurrence.label == "Updated label"


def test_resulting_state_schema_errors_are_rejected_but_programming_errors_propagate(monkeypatch):
    event, candidate, proposal = setup_update()
    occurrence = event.occurrences.get()
    proposal.occurrence_changes = [
        CanonicalOccurrenceChange(
            operation=ObjectOperation.UPDATE,
            id=occurrence.pk,
            changed_fields=[OccurrenceField.LABEL],
            value=empty_occurrence_value(label="Updated label"),
        )
    ]
    occurrence.occurrence_status = "INVALID"
    occurrence.save(update_fields=["occurrence_status"])
    reject_without_writes(event, candidate, proposal, "RESULTING_STATE_SCHEMA_INVALID")

    def unexpected_error(*args):
        raise RuntimeError("Unexpected bug")

    monkeypatch.setattr(
        "ingestion.canonicalization.plans.validation.proposal.merged_occurrence_value",
        unexpected_error,
    )
    with pytest.raises(RuntimeError, match="Unexpected bug"):
        validate_proposal(candidate, proposal)


def test_occurrence_sequences_can_swap_at_storage_boundary():
    event, candidate, proposal = setup_update()
    first = event.occurrences.get()
    second = EventOccurrence.objects.create(
        event=event,
        sequence=32767,
        start_date=first.start_date,
        start_time=first.start_time,
        time_precision=first.time_precision,
        attendance_mode=first.attendance_mode,
        occurrence_status=first.occurrence_status,
    )
    proposal.occurrence_changes = [
        CanonicalOccurrenceChange(
            operation=ObjectOperation.UPDATE,
            id=item.pk,
            changed_fields=[OccurrenceField.SEQUENCE],
            value=empty_occurrence_value(sequence=sequence),
        )
        for item, sequence in ((first, 32767), (second, 1))
    ]
    plan = canonicalize_candidate(
        candidate.pk, expected_version=candidate.edit_version, decision=proposal
    )
    assert plan.status == "APPLIED", plan.application_error
    first.refresh_from_db()
    second.refresh_from_db()
    assert (first.sequence, second.sequence) == (32767, 1)


@pytest.mark.parametrize("kind", ["occurrence", "organizer"])
def test_add_event_rejects_out_of_range_ordering_values(kind):
    from ingestion.canonicalization.decisions.projection import automatic_add_proposal

    event, candidate, _proposal = setup_update()
    proposal = automatic_add_proposal(complete_payload())
    if kind == "occurrence":
        proposal.add_event.occurrences[0].sequence = -1
        expected = "OCCURRENCE_SEQUENCE_INVALID"
    else:
        organizer = Organizer.objects.create(
            name="Test organizer", normalized_name="test organizer"
        )
        proposal.add_event.organizers = [
            CanonicalOrganizerValue(
                organizer_id=organizer.pk, role=None, is_primary=False, position=-1
            )
        ]
        expected = "ORGANIZER_POSITION_INVALID"
    reject_without_writes(event, candidate, proposal, expected)
