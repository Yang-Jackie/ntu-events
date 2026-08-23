from django.db import migrations


def migrate_event_provenance(apps, schema_editor):
    provenance_model = apps.get_model("events", "EventProvenance")
    source_link_model = apps.get_model("events", "EventSourceLink")
    observation_model = apps.get_model("events", "EventObservation")
    for provenance in provenance_model.objects.order_by("pk").iterator():
        source_link, created = source_link_model.objects.get_or_create(
            event_id=provenance.event_id,
            source_representation_id=provenance.source_representation_id,
            defaults={"is_primary_source": provenance.is_primary_source},
        )
        if not created and provenance.is_primary_source and not source_link.is_primary_source:
            source_link.is_primary_source = True
            source_link.save(update_fields=("is_primary_source",))
        observation_model.objects.get_or_create(
            event_candidate_id=provenance.event_candidate_id,
            defaults={
                "source_link_id": source_link.pk,
                "observation_type": "UNKNOWN",
            },
        )


def restore_event_provenance(apps, schema_editor):
    provenance_model = apps.get_model("events", "EventProvenance")
    observation_model = apps.get_model("events", "EventObservation")
    for observation in observation_model.objects.select_related("source_link").iterator():
        provenance_model.objects.get_or_create(
            event_candidate_id=observation.event_candidate_id,
            defaults={
                "event_id": observation.source_link.event_id,
                "source_representation_id": observation.source_link.source_representation_id,
                "is_primary_source": observation.source_link.is_primary_source,
            },
        )


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("events", "0009_eventrevision_canonicalization_plan_and_more"),
    ]

    operations = [
        migrations.RunPython(migrate_event_provenance, restore_event_provenance),
        migrations.DeleteModel(name="EventProvenance"),
    ]
