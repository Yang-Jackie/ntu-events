from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import connection

from ingestion.canonicalization.decisions.provider import (
    CanonicalizationDecisionProvider,
    OpenAICanonicalizationDecisionProvider,
)
from ingestion.canonicalization.workflow import process_candidate
from ingestion.models import CandidateStatus, EventCandidate
from ingestion.raw_storage import LocalRawContentStorage, RawContentStorage

LOCK_NAMESPACE = 1_315_445_093
LOCK_KEY = 1


def try_acquire_global_lock(database: Any) -> bool:
    if database.vendor != "postgresql":
        raise ValueError("The canonicalization worker requires PostgreSQL advisory locks.")
    with database.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s, %s)", [LOCK_NAMESPACE, LOCK_KEY])
        return bool(cursor.fetchone()[0])


def release_global_lock(database: Any) -> None:
    with database.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_unlock(%s, %s)", [LOCK_NAMESPACE, LOCK_KEY])


class CanonicalizationWorkerRuntime:
    """Process READY candidates serially through the source-neutral workflow."""

    def __init__(
        self,
        *,
        decision_provider: CanonicalizationDecisionProvider | None = None,
        storage: RawContentStorage | None = None,
    ) -> None:
        self._decision_provider = decision_provider
        self._storage = storage

    def run_next_candidate(
        self,
        *,
        on_started: Callable[[EventCandidate], None] | None = None,
    ) -> EventCandidate | None:
        candidate = (
            EventCandidate.objects.filter(
                status=CandidateStatus.READY,
                canonicalization_plan__isnull=True,
            )
            .order_by("created_at", "pk")
            .first()
        )
        if candidate is None:
            return None
        if on_started is not None:
            on_started(candidate)
        process_candidate(
            candidate_id=candidate.pk,
            decision_provider=self._get_decision_provider(),
            storage=self._get_storage(),
        )
        return candidate

    def run(
        self,
        *,
        once: bool = False,
        poll_interval: float = 2.0,
        on_locked: Callable[[], None] | None = None,
        on_busy: Callable[[], None] | None = None,
        on_started: Callable[[EventCandidate], None] | None = None,
        on_finished: Callable[[EventCandidate], None] | None = None,
    ) -> None:
        """Own the exclusive database session and resource lifetime while polling."""
        if not 0.1 <= poll_interval <= 60:
            raise ValueError("--poll-interval must be between 0.1 and 60 seconds")
        lock_connection = None
        try:
            connection.ensure_connection()
            if not try_acquire_global_lock(connection):
                if on_busy is not None:
                    on_busy()
                return
            lock_connection = connection.connection
            if on_locked is not None:
                on_locked()
            while True:
                self._assert_lock_connection(lock_connection)
                candidate = self.run_next_candidate(on_started=on_started)
                self._assert_lock_connection(lock_connection)
                if candidate is not None:
                    candidate.refresh_from_db()
                    if on_finished is not None:
                        on_finished(candidate)
                if once:
                    return
                if candidate is None:
                    time.sleep(poll_interval)
        finally:
            try:
                self.close()
            finally:
                if (
                    lock_connection is not None
                    and connection.connection is lock_connection
                    and connection.is_usable()
                ):
                    release_global_lock(connection)

    @staticmethod
    def _assert_lock_connection(lock_connection: Any) -> None:
        if connection.connection is not lock_connection or not connection.is_usable():
            raise RuntimeError(
                "The canonicalization worker lost its advisory-lock database session."
            )

    def close(self) -> None:
        if self._decision_provider is not None:
            self._decision_provider.close()
            self._decision_provider = None

    def _get_decision_provider(self) -> CanonicalizationDecisionProvider:
        if self._decision_provider is None:
            if not getattr(settings, "OPENAI_API_KEY", ""):
                raise RuntimeError("OPENAI_API_KEY is required for canonicalization")
            self._decision_provider = OpenAICanonicalizationDecisionProvider(
                model_name=settings.OPENAI_CANONICALIZATION_MODEL,
                reasoning_effort=settings.OPENAI_CANONICALIZATION_REASONING_EFFORT,
            )
        return self._decision_provider

    def _get_storage(self) -> RawContentStorage:
        if self._storage is None:
            self._storage = LocalRawContentStorage(Path(settings.RAW_STORAGE_ROOT))
        return self._storage
