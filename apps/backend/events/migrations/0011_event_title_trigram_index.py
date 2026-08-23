from django.contrib.postgres.indexes import GistIndex
from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0010_preserve_event_provenance"),
    ]

    operations = [
        TrigramExtension(),
        migrations.AddIndex(
            model_name="event",
            index=GistIndex(
                fields=["normalized_title"],
                name="event_title_trgm_gist",
                opclasses=["gist_trgm_ops"],
            ),
        ),
    ]
