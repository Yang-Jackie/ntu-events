import pytest
from django.db import connection


@pytest.mark.django_db
def test_postgis_extension_is_enabled() -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT extversion FROM pg_extension WHERE extname = %s",
            ["postgis"],
        )
        row = cursor.fetchone()

    assert row is not None
    assert row[0].startswith("3.6")


@pytest.mark.django_db
def test_event_title_trigram_extension_and_index_are_enabled() -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT extversion FROM pg_extension WHERE extname = %s", ["pg_trgm"])
        extension = cursor.fetchone()
        cursor.execute(
            "SELECT indexdef FROM pg_indexes WHERE indexname = %s",
            ["event_title_trgm_gist"],
        )
        index_definition = cursor.fetchone()

    assert extension is not None
    assert index_definition is not None
    assert "gist_trgm_ops" in index_definition[0]
