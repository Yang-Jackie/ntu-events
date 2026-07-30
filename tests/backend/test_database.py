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
