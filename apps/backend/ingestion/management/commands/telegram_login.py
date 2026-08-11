from __future__ import annotations

import asyncio
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from telethon import TelegramClient


class Command(BaseCommand):
    help = "Perform one interactive Telegram login and save the ignored Telethon session."

    def handle(self, *args, **options) -> None:
        if not settings.TELEGRAM_API_ID or not settings.TELEGRAM_API_HASH:
            raise CommandError("Set TELEGRAM_API_ID and TELEGRAM_API_HASH in .env first")
        session_path = Path(settings.TELEGRAM_SESSION_PATH)
        session_path.parent.mkdir(parents=True, exist_ok=True)

        async def login() -> None:
            client = TelegramClient(
                str(session_path),
                int(settings.TELEGRAM_API_ID),
                settings.TELEGRAM_API_HASH,
            )
            await client.start()
            await client.disconnect()

        asyncio.run(login())
        self.stdout.write(self.style.SUCCESS(f"Telegram session saved at {session_path}.session"))
