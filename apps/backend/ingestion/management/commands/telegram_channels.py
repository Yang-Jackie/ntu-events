from __future__ import annotations

import asyncio

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser
from sources.models import Source, SourceType

from ingestion.pipelines.telegram.adapter import TelegramFetcher


class Command(BaseCommand):
    help = "List accessible public Telegram channels and optionally register selections as sources."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--limit", type=int, default=20)
        parser.add_argument("--register", nargs="*", type=int, default=[])

    def handle(self, *args, **options) -> None:
        if not settings.TELEGRAM_API_ID or not settings.TELEGRAM_API_HASH:
            raise CommandError("Set TELEGRAM_API_ID and TELEGRAM_API_HASH in .env first")
        if not 1 <= options["limit"] <= 1000:
            raise CommandError("--limit must be between 1 and 1000")
        fetcher = TelegramFetcher(
            api_id=int(settings.TELEGRAM_API_ID),
            api_hash=settings.TELEGRAM_API_HASH,
            session_path=settings.TELEGRAM_SESSION_PATH,
        )
        channels = asyncio.run(fetcher.list_public_channels(options["limit"]))
        for index, channel in enumerate(channels, 1):
            self.stdout.write(
                f"{index:>2}. {channel.title} (@{channel.username}, id={channel.channel_id})"
            )
        indexes = options["register"]
        invalid = [index for index in indexes if not 1 <= index <= len(channels)]
        if invalid:
            raise CommandError(f"Channel selection indexes are out of range: {invalid}")
        for index in dict.fromkeys(indexes):
            channel = channels[index - 1]
            existing = Source.objects.filter(
                adapter_key="telegram_text",
                configuration__channel_id=channel.channel_id,
            ).first()
            if existing:
                self.stdout.write(f"Already registered: {existing.pk} — {existing.name}")
                continue
            source = Source.objects.create(
                name=channel.title,
                source_type=SourceType.PUBLIC_CHANNEL,
                base_url=f"https://t.me/{channel.username}",
                adapter_key="telegram_text",
                configuration={
                    "channel_id": channel.channel_id,
                    "username": channel.username,
                },
            )
            self.stdout.write(self.style.SUCCESS(f"Registered source {source.pk}: {source.name}"))
