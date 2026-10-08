"""Replay frozen decisions only in the disposable evaluation database."""

import argparse
import json
from pathlib import Path

from .paths import bootstrap_django, run_directory
from .prepare import fingerprint


def require_isolation(database: str):
    if not database.startswith("ntu_events_eval_"):
        raise RuntimeError("Choose an explicitly named ntu_events_eval_ disposable database")
    bootstrap_django()
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database()")
        actual = cursor.fetchone()[0]
    if actual != database or connection.settings_dict["NAME"] != database:
        raise RuntimeError(f"Refusing evaluation writes to database {actual}")


def _restore_event(snapshot):
    from events.models import (
        Event,
        EventAudience,
        EventFormat,
        EventOccurrence,
        EventOrganizer,
        EventPurpose,
        EventTopic,
        OccurrenceVenue,
        Registration,
    )
    from ingestion.canonicalization.normalization import normalize_match_text
    from ingestion.canonicalization.snapshots import event_snapshot, event_snapshot_payload_hash

    event_id = snapshot["id"]
    event = Event.objects.get(pk=event_id)
    event.registrations.all().delete()
    event.occurrences.all().delete()
    event.eventorganizer_set.all().delete()
    fields = {
        key: value
        for key, value in snapshot.items()
        if key
        in {
            "slug",
            "title",
            "description",
            "image_reference",
            "audience_notes",
            "publication_status",
            "verification_status",
            "last_verified_at",
            "archived_at",
        }
    }
    fields["normalized_title"] = normalize_match_text(snapshot["title"])
    Event.objects.filter(pk=event_id).update(**fields)
    for name, model in [
        ("formats", EventFormat),
        ("topics", EventTopic),
        ("purposes", EventPurpose),
        ("audiences", EventAudience),
    ]:
        getattr(event, name).set(model.objects.filter(code__in=snapshot[name]))
    for value in snapshot["organizers"]:
        EventOrganizer.objects.create(event=event, **value)
    for value in snapshot["occurrences"]:
        fields = {key: value for key, value in value.items() if key != "venue_ids"}
        occurrence = EventOccurrence.objects.create(event=event, **fields)
        for position, venue_id in enumerate(value["venue_ids"]):
            OccurrenceVenue.objects.create(
                occurrence=occurrence,
                venue_id=venue_id,
                position=position,
                is_primary=position == 0,
            )
    for value in snapshot["registrations"]:
        fields = {key: value for key, value in value.items() if key != "scope"}
        if value["scope"] == "EVENT":
            fields["event_id"] = event_id
        Registration.objects.create(**fields)
    if event_snapshot_payload_hash(event_snapshot(event)) != event_snapshot_payload_hash(snapshot):
        raise RuntimeError(f"Failed to recreate historical Event {event_id} exactly")


def replay(case, proposal, *, database: str):
    require_isolation(database)
    from django.db import transaction
    from django.db.models import Max
    from events.models import Event
    from ingestion.canonicalization.snapshots import event_snapshot, event_snapshot_payload_hash
    from ingestion.canonicalization.workflow import canonicalize_candidate
    from ingestion.models import CandidateMatch, EventCandidate

    with transaction.atomic():
        context = case["context"]
        for match in context["possible_matches"]:
            _restore_event(match["event"])
        candidate = EventCandidate.objects.get(pk=case["candidate_id"])
        candidate.pk = None
        latest = EventCandidate.objects.filter(extraction_run_id=candidate.extraction_run_id)
        candidate.candidate_index = latest.aggregate(n=Max("candidate_index"))["n"] + 1
        candidate.status = "READY"
        candidate.processed_at = None
        candidate.save(force_insert=True)
        matches = [
            CandidateMatch.objects.create(
                event_candidate=candidate,
                event_id=m["event_id"],
                rank=m["rank"],
                score=m["match_percentage"] / 100,
                signals=m["signals"],
            )
            for m in context["possible_matches"]
        ]
        plan = canonicalize_candidate(
            candidate.pk,
            expected_version=candidate.edit_version,
            decision=proposal,
            precomputed_matches=matches,
            match_snapshot=context["possible_matches"],
            target_snapshot_hashes={
                m["event_id"]: event_snapshot_payload_hash(m["event"])
                for m in context["possible_matches"]
            },
        )
        result = {
            "status": plan.status,
            "issues": plan.validation_issues,
            "application_error": plan.application_error,
            "final_event": plan.applied_snapshot if plan.status == "APPLIED" else None,
        }
        result["other_matches_preserved"] = all(
            event_snapshot_payload_hash(event_snapshot(Event.objects.get(pk=m["event_id"])))
            == event_snapshot_payload_hash(m["event"])
            for m in context["possible_matches"]
            if m["event_id"] != plan.target_event_id
        )
        transaction.set_rollback(True)
    return result


def smoke(directory: Path, *, database: str):
    require_isolation(database)
    from ingestion.models import CanonicalizationPlan

    dataset = json.loads((directory / "dataset.json").read_text(encoding="utf-8"))
    before = fingerprint()
    results = []
    for case in dataset["canonicalization"]:
        baseline = CanonicalizationPlan.objects.get(event_candidate_id=case["candidate_id"])
        result = replay(case, baseline.generated_proposal, database=database)
        if result["status"] != baseline.status:
            raise RuntimeError(f"Baseline status changed for {case['id']}: {result['status']}")
        results.append({"id": case["id"], "status": result["status"]})
    if fingerprint() != before:
        raise RuntimeError("Replay did not roll back all database row changes")
    report = {
        "database": database,
        "cases": len(results),
        "results": results,
        "rollback_verified": True,
    }
    (directory / "offline_smoke.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--database", required=True)
    args = parser.parse_args()
    smoke(run_directory(args.run_dir), database=args.database)
