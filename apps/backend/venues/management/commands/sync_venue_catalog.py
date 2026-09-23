from django.core.management.base import BaseCommand

from venues.catalog import sync_catalog


class Command(BaseCommand):
    help = "Synchronize the reviewed NTU/NIE venue catalog without changing map points."

    def handle(self, *args, **options):
        del args, options
        counts = sync_catalog()
        self.stdout.write(
            self.style.SUCCESS(
                "Synchronized "
                f"{counts['buildings']} buildings, "
                f"{counts['venues']} venues, and "
                f"{counts['aliases']} verified aliases."
            )
        )
