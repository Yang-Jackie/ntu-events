from django.db import migrations


def sync_reviewed_venue_catalog(apps, schema_editor):
    from venues.catalog import sync_catalog

    sync_catalog(
        building_model=apps.get_model("venues", "Building"),
        venue_model=apps.get_model("venues", "Venue"),
        alias_model=apps.get_model("venues", "VenueAlias"),
        using=schema_editor.connection.alias,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("venues", "0005_venue_code_venuealias_source_url_and_more"),
    ]

    operations = [
        migrations.RunPython(sync_reviewed_venue_catalog, migrations.RunPython.noop),
    ]
