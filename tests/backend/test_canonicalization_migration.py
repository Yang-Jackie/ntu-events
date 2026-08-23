from datetime import UTC, datetime

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db(transaction=True)


def test_migration_preserves_existing_provenance_and_review_progress(request) -> None:
    def restore_latest_schema() -> None:
        restore_executor = MigrationExecutor(connection)
        restore_executor.migrate(restore_executor.loader.graph.leaf_nodes())

    request.addfinalizer(restore_latest_schema)
    executor = MigrationExecutor(connection)
    old_targets = [
        ("events", "0007_alter_eventoccurrence_occurrence_status"),
        ("ingestion", "0006_candidatereview_candidatereviewoccurrence_and_more"),
        ("sources", "0004_replace_crawl_run_with_ingestion_job"),
    ]
    executor.migrate(old_targets)
    old_apps = executor.loader.project_state(old_targets).apps

    now = datetime(2026, 8, 21, tzinfo=UTC)
    source = old_apps.get_model("sources", "Source").objects.create(
        name="Migration source",
        source_type="PUBLIC_CHANNEL",
        adapter_key="test",
    )
    representation = old_apps.get_model("sources", "SourceRepresentation").objects.create(
        source=source,
        external_identifier="message-1",
        first_seen_at=now,
        last_seen_at=now,
    )
    document = old_apps.get_model("sources", "RawSourceDocument").objects.create(
        source_representation=representation,
        fetched_at=now,
        storage_key="raw/migration/message-1.json",
        content_hash="a" * 64,
        processing_status="PROCESSED",
    )
    extraction = old_apps.get_model("ingestion", "ExtractionRun").objects.create(
        raw_source_document=document,
        extractor_type="test",
        extractor_version="1",
        started_at=now,
        status="SUCCEEDED",
    )
    old_payload = {
        "schema_version": "event-candidate-v2",
        "title": "Existing event",
        "description": "Existing useful description.",
    }
    candidate = old_apps.get_model("ingestion", "EventCandidate").objects.create(
        extraction_run=extraction,
        source_representation=representation,
        candidate_index=0,
        schema_version="event-candidate-v2",
        payload=old_payload,
        title="Existing event",
        validation_status="READY",
    )
    event = old_apps.get_model("events", "Event").objects.create(
        slug="existing-event",
        title="Existing event",
        normalized_title="existing event",
    )
    old_apps.get_model("ingestion", "CandidateReview").objects.create(
        event_candidate=candidate,
        canonical_event=event,
        effective_payload=old_payload,
        review_status="NOT_REQUIRED",
        sync_status="SYNCED",
        promotion_method="AUTOMATIC",
        review_version=1,
        synced_version=1,
    )
    old_apps.get_model("events", "EventProvenance").objects.create(
        event=event,
        event_candidate=candidate,
        source_representation=representation,
        is_primary_source=True,
    )

    executor = MigrationExecutor(connection)
    new_targets = executor.loader.graph.leaf_nodes()
    executor.migrate(new_targets)
    new_apps = executor.loader.project_state(new_targets).apps

    source_link = new_apps.get_model("events", "EventSourceLink").objects.get()
    observation = new_apps.get_model("events", "EventObservation").objects.get()
    migrated_candidate = new_apps.get_model("ingestion", "EventCandidate").objects.get()
    plan = new_apps.get_model("ingestion", "CanonicalizationPlan").objects.get()

    assert source_link.event_id == event.pk
    assert source_link.source_representation_id == representation.pk
    assert observation.source_link_id == source_link.pk
    assert observation.event_candidate_id == candidate.pk
    assert migrated_candidate.status == "PROCESSED"
    assert migrated_candidate.edit_version == 1
    assert migrated_candidate.effective_payload["schema_version"] == "event-candidate-v3"
    assert migrated_candidate.extracted_payload["observation_type"] == "UNKNOWN"
    assert plan.event_candidate_id == migrated_candidate.pk
    assert plan.status == "APPLIED"
    assert plan.action == "LINK_ONLY"
