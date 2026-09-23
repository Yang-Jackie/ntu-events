from django.core.management.base import BaseCommand

from venues.geography import sync_geography


class Command(BaseCommand):
    help = "Synchronize reviewed NTU/NIE building map points and provenance."

    def handle(self, *args, **options):
        counts = sync_geography()
        self.stdout.write(
            self.style.SUCCESS(f"Synchronized {counts['buildings']} building map points.")
        )
