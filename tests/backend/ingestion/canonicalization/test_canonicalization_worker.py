from __future__ import annotations

from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock

import psycopg
import pytest
from django.core.management import call_command
from django.db import connection
from ingestion.canonicalization.worker import (
    CanonicalizationWorkerRuntime,
    release_global_lock,
    try_acquire_global_lock,
)
from ingestion.raw_storage import LocalRawContentStorage


def _worker_database():
    return SimpleNamespace(
        connection=object(), ensure_connection=Mock(), is_usable=Mock(return_value=True)
    )


def test_worker_does_not_process_without_the_global_lock(monkeypatch) -> None:
    database = _worker_database()
    monkeypatch.setattr("ingestion.canonicalization.worker.connection", database)
    monkeypatch.setattr(
        "ingestion.canonicalization.worker.try_acquire_global_lock", Mock(return_value=False)
    )
    release = Mock()
    monkeypatch.setattr("ingestion.canonicalization.worker.release_global_lock", release)
    runtime = CanonicalizationWorkerRuntime()
    runtime.run_next_candidate = Mock()
    busy = Mock()

    runtime.run(once=True, on_busy=busy)

    busy.assert_called_once_with()
    runtime.run_next_candidate.assert_not_called()
    release.assert_not_called()


@pytest.mark.parametrize("startup", ["busy", "connection_failure", "lock_failure"])
def test_worker_closes_existing_provider_when_startup_cannot_proceed(monkeypatch, startup) -> None:
    database = _worker_database()
    monkeypatch.setattr("ingestion.canonicalization.worker.connection", database)
    acquire = Mock(return_value=False)
    monkeypatch.setattr("ingestion.canonicalization.worker.try_acquire_global_lock", acquire)
    release = Mock()
    monkeypatch.setattr("ingestion.canonicalization.worker.release_global_lock", release)
    provider = Mock()
    runtime = CanonicalizationWorkerRuntime(decision_provider=provider)
    runtime.run_next_candidate = Mock()

    if startup == "busy":
        runtime.run(once=True)
    else:
        if startup == "connection_failure":
            database.ensure_connection.side_effect = RuntimeError("startup failed")
        else:
            acquire.side_effect = RuntimeError("startup failed")
        with pytest.raises(RuntimeError, match="startup failed"):
            runtime.run(once=True)

    provider.close.assert_called_once_with()
    runtime.run_next_candidate.assert_not_called()
    release.assert_not_called()


def test_worker_releases_lock_even_when_provider_cleanup_fails(monkeypatch) -> None:
    database = _worker_database()
    monkeypatch.setattr("ingestion.canonicalization.worker.connection", database)
    monkeypatch.setattr(
        "ingestion.canonicalization.worker.try_acquire_global_lock", Mock(return_value=True)
    )
    release = Mock()
    monkeypatch.setattr("ingestion.canonicalization.worker.release_global_lock", release)
    provider = Mock()
    provider.close.side_effect = RuntimeError("cleanup failed")
    runtime = CanonicalizationWorkerRuntime(decision_provider=provider)
    runtime.run_next_candidate = Mock(return_value=None)

    with pytest.raises(RuntimeError, match="cleanup failed"):
        runtime.run(once=True)

    release.assert_called_once_with(database)


@pytest.mark.parametrize("error", [None, RuntimeError("processing failed"), KeyboardInterrupt()])
def test_worker_closes_provider_and_releases_lock_on_exit(monkeypatch, error) -> None:
    database = _worker_database()
    monkeypatch.setattr("ingestion.canonicalization.worker.connection", database)
    monkeypatch.setattr(
        "ingestion.canonicalization.worker.try_acquire_global_lock", Mock(return_value=True)
    )
    release = Mock()
    monkeypatch.setattr("ingestion.canonicalization.worker.release_global_lock", release)
    provider = Mock()
    runtime = CanonicalizationWorkerRuntime(decision_provider=provider)
    runtime.run_next_candidate = Mock(return_value=None, side_effect=error)

    if error is None:
        runtime.run(once=True)
    else:
        with pytest.raises(type(error)):
            runtime.run(once=True)

    provider.close.assert_called_once_with()
    release.assert_called_once_with(database)


@pytest.mark.parametrize("lose_before_processing", [True, False])
def test_worker_stops_when_its_lock_session_is_lost(monkeypatch, lose_before_processing) -> None:
    database = _worker_database()
    monkeypatch.setattr("ingestion.canonicalization.worker.connection", database)
    monkeypatch.setattr(
        "ingestion.canonicalization.worker.try_acquire_global_lock", Mock(return_value=True)
    )
    release = Mock()
    monkeypatch.setattr("ingestion.canonicalization.worker.release_global_lock", release)
    provider = Mock()
    runtime = CanonicalizationWorkerRuntime(decision_provider=provider)

    def next_candidate(**_kwargs):
        database.connection = object()
        return None

    runtime.run_next_candidate = Mock(side_effect=next_candidate)
    if lose_before_processing:
        database.is_usable.return_value = False

    with pytest.raises(RuntimeError, match="lost its advisory-lock"):
        runtime.run(once=True)

    if lose_before_processing:
        runtime.run_next_candidate.assert_not_called()
    else:
        runtime.run_next_candidate.assert_called_once()
    provider.close.assert_called_once_with()
    release.assert_not_called()


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

    class FakeRuntime(CanonicalizationWorkerRuntime):
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
        "ingestion.canonicalization.worker.try_acquire_global_lock",
        lambda _database: True,
    )
    monkeypatch.setattr(
        "ingestion.canonicalization.worker.release_global_lock",
        lambda _database: None,
    )

    call_command("run_canonicalization_worker", "--once", stdout=output)

    assert output.getvalue().splitlines() == [
        "Canonicalization worker started with the global advisory lock.",
        "Candidate 42 processing started.",
        "Candidate 42 finished with status PROCESSED.",
    ]
