from django.db import migrations


def sync_reviewed_venue_geography(apps, schema_editor):
    from venues.geography import sync_geography

    sync_geography(
        building_model=apps.get_model("venues", "Building"),
        using=schema_editor.connection.alias,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("venues", "0009_building_map_positioning_method_and_more"),
    ]

    operations = [
        migrations.RunPython(sync_reviewed_venue_geography, migrations.RunPython.noop),
    ]
