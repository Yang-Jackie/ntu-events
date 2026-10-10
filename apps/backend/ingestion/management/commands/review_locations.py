"""List physical location wording for owner review without changing data."""

import json

from django.core.management.base import BaseCommand
from django.db import connection, transaction

from ingestion.candidates.location_review import review_locations


class Command(BaseCommand):
    help = __doc__

    def add_arguments(self, parser):
        parser.add_argument("--source", type=int, action="append", default=[])
        parser.add_argument(
            "--needs-review",
            action="store_true",
            help="Only unresolved locations or disagreements with current venue choices.",
        )
        parser.add_argument("--json", action="store_true")

    def handle(self, *args, **options):
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            rows = review_locations(source_ids=options["source"])
        if options["needs_review"]:
            rows = [row for row in rows if row["needs_review"]]
        if options["json"]:
            self.stdout.write(json.dumps(rows, ensure_ascii=False, indent=2))
            return
        for row in rows:
            names = " | ".join(row["spellings"]) or "(no location provided)"
            match = ", ".join(row["resolved_venue_codes"]) or "unresolved"
            self.stdout.write(
                f"{names} -> {match}" + (" [needs review]" if row["needs_review"] else "")
            )
            self.stdout.write(
                f"  Candidates: {row['candidate_ids']}; Events: {row['event_ids']}; "
                f"Occurrences: {row['occurrence_ids']}"
            )
        self.stdout.write(f"{len(rows)} distinct location terms. No data changed.")
