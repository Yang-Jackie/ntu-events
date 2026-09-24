from __future__ import annotations

from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock

import psycopg
import pytest
from django.core.management import call_command
from django.db import connection
from ingestion.management.commands.run_canonicalization_worker import (
    release_global_lock,
    try_acquire_global_lock,
)
from ingestion.raw_storage import LocalRawContentStorage


def test_local_raw_storage_loads_saved_content_and_rejects_escape(tmp_path) -> None:
    storage = LocalRawContentStorage(tmp_path)
    saved = storage.save(b'{"message": "evidence"}', suffix=".json")

    assert storage.load(saved.storage_key) == b'{"message": "evidence"}'
    with pytest.raises(ValueError, match="escaped"):
        storage.load("../outside.json")


@pytest.mark.django_db(transaction=True)
def test_postgres_advisory_lock_allows_only_one_worker_session() -> None:
    params = connection.get_connection_params()
    with (
        psycopg.connect(**params) as first_connection,
        psycopg.connect(**params) as second_connection,
    ):
        first = SimpleNamespace(vendor="postgresql", cursor=first_connection.cursor)
        second = SimpleNamespace(vendor="postgresql", cursor=second_connection.cursor)

        assert try_acquire_global_lock(first) is True
        assert try_acquire_global_lock(second) is False

        release_global_lock(first)
        assert try_acquire_global_lock(second) is True
        release_global_lock(second)


@pytest.mark.django_db
def test_worker_logs_candidate_before_processing(monkeypatch) -> None:
    output = StringIO()
    candidate = SimpleNamespace(pk=42, status="PROCESSED", refresh_from_db=Mock())

    class FakeRuntime:
        def run_next_candidate(self, *, on_started):
            on_started(candidate)
            assert "Candidate 42 processing started." in output.getvalue()
            return candidate

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        "ingestion.management.commands.run_canonicalization_worker.CanonicalizationWorkerRuntime",
        FakeRuntime,
    )
    monkeypatch.setattr(
        "ingestion.management.commands.run_canonicalization_worker.try_acquire_global_lock",
        lambda _database: True,
    )
    monkeypatch.setattr(
        "ingestion.management.commands.run_canonicalization_worker.release_global_lock",
        lambda _database: None,
    )

    call_command("run_canonicalization_worker", "--once", stdout=output)

    assert output.getvalue().splitlines() == [
        "Canonicalization worker started with the global advisory lock.",
        "Candidate 42 processing started.",
        "Candidate 42 finished with status PROCESSED.",
    ]
