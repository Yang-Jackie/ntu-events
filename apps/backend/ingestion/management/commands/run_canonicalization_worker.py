from __future__ import annotations

from django.core.management.base import BaseCommand, CommandParser

from ingestion.canonicalization.worker import CanonicalizationWorkerRuntime


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
        runtime = CanonicalizationWorkerRuntime()
        try:
            runtime.run(
                once=options["once"],
                poll_interval=options["poll_interval"],
                on_locked=lambda: self.stdout.write(
                    "Canonicalization worker started with the global advisory lock."
                ),
                on_busy=lambda: self.stdout.write(
                    self.style.WARNING(
                        "Another canonicalization worker already holds the global lock."
                    )
                ),
                on_started=lambda candidate: self.stdout.write(
                    f"Candidate {candidate.pk} processing started."
                ),
                on_finished=lambda candidate: self.stdout.write(
                    f"Candidate {candidate.pk} finished with status {candidate.status}."
                ),
            )
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Canonicalization worker stopped."))
