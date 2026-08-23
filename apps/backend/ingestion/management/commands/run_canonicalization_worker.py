from __future__ import annotations

import time
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import connection

from ingestion.canonicalization.worker import CanonicalizationWorkerRuntime

LOCK_NAMESPACE = 1_315_445_093
LOCK_KEY = 1


def try_acquire_global_lock(database: Any) -> bool:
    if database.vendor != "postgresql":
        raise CommandError("The canonicalization worker requires PostgreSQL advisory locks.")
    with database.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s, %s)", [LOCK_NAMESPACE, LOCK_KEY])
        return bool(cursor.fetchone()[0])


def release_global_lock(database: Any) -> None:
    with database.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_unlock(%s, %s)", [LOCK_NAMESPACE, LOCK_KEY])


class Command(BaseCommand):
    help = "Process READY EventCandidates through canonicalization, one at a time."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--once",
            action="store_true",
            help="Process at most one READY candidate, then exit.",
        )
        parser.add_argument("--poll-interval", type=float, default=2.0)

    def handle(self, *args, **options) -> None:
        interval = options["poll_interval"]
        if not 0.1 <= interval <= 60:
            raise ValueError("--poll-interval must be between 0.1 and 60 seconds")

        connection.ensure_connection()
        if not try_acquire_global_lock(connection):
            self.stdout.write(
                self.style.WARNING("Another canonicalization worker already holds the global lock.")
            )
            return

        lock_connection = connection.connection
        runtime = CanonicalizationWorkerRuntime()
        self.stdout.write("Canonicalization worker started with the global advisory lock.")
        try:
            while True:
                self._assert_lock_connection(lock_connection)
                candidate = runtime.run_next_candidate()
                self._assert_lock_connection(lock_connection)
                if candidate is not None:
                    candidate.refresh_from_db()
                    self.stdout.write(
                        f"Candidate {candidate.pk} finished with status {candidate.status}."
                    )
                if options["once"]:
                    return
                if candidate is None:
                    time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Canonicalization worker stopped."))
        finally:
            runtime.close()
            if connection.connection is lock_connection and connection.is_usable():
                release_global_lock(connection)

    @staticmethod
    def _assert_lock_connection(lock_connection: Any) -> None:
        if connection.connection is not lock_connection or not connection.is_usable():
            raise RuntimeError(
                "The canonicalization worker lost its advisory-lock database session."
            )
