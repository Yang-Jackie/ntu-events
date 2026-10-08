from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import RawTelegramMessage, TextEntity

RETRIEVAL_VERSION = "telegram-text-v1"
URL_PATTERN = re.compile(r"https?://[^\s<>()\[\]{}\"']+")


@dataclass(frozen=True)
class ChannelChoice:
    entity: Any
    title: str
    username: str | None
    channel_id: int


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_selection(value: str, maximum: int) -> list[int]:
    selected: list[int] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        if not part.isdigit():
            raise ValueError(f"Invalid channel selection: {part!r}")
        index = int(part)
        if not 1 <= index <= maximum:
            raise ValueError(f"Channel selection {index} is outside 1-{maximum}")
        if index - 1 not in selected:
            selected.append(index - 1)
    if not selected:
        raise ValueError("Select at least one channel")
    return selected


def _entity_record(entity: Any, text: str) -> TextEntity:
    offset = int(getattr(entity, "offset", 0))
    length = int(getattr(entity, "length", 0))
    return TextEntity(
        kind=type(entity).__name__,
        offset=offset,
        length=length,
        text=text[offset : offset + length] or None,
        url=getattr(entity, "url", None),
    )


def normalize_message(
    message: Any, channel: ChannelChoice, retrieved_at: datetime
) -> RawTelegramMessage:
    text = message.raw_text or ""
    entities = [_entity_record(entity, text) for entity in (message.entities or [])]
    urls = set(URL_PATTERN.findall(text))
    urls.update(entity.url for entity in entities if entity.url)
    forward = getattr(message, "forward", None)
    forwarded_from = None
    if forward:
        forwarded_from = (
            str(getattr(forward, "from_name", None) or getattr(forward, "chat_id", None) or "")
            or None
        )
    reply = getattr(message, "reply_to", None)
    return RawTelegramMessage(
        channel_id=channel.channel_id,
        channel_username=channel.username,
        channel_title=channel.title,
        message_id=message.id,
        message_url=(f"https://t.me/{channel.username}/{message.id}" if channel.username else None),
        published_at=message.date,
        edited_at=getattr(message, "edit_date", None),
        text=text,
        text_entities=entities,
        external_urls=sorted(urls),
        reply_to_message_id=getattr(reply, "reply_to_msg_id", None),
        forwarded_from=forwarded_from,
        views=getattr(message, "views", None),
        content_hash=content_hash(text),
        retrieved_at=retrieved_at,
        retrieval_version=RETRIEVAL_VERSION,
    )


class TelegramSource:
    def __init__(self, api_id: int, api_hash: str, session_path: Path):
        try:
            from telethon import TelegramClient
        except ImportError as exc:
            raise RuntimeError(
                'Telethon is not installed. Run: python -m pip install -e ".[dev]"'
            ) from exc
        session_path.parent.mkdir(parents=True, exist_ok=True)
        self.client = TelegramClient(str(session_path), api_id, api_hash)

    async def __aenter__(self) -> TelegramSource:
        await self.client.start()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.client.disconnect()

    async def list_channels(self, limit: int = 20) -> list[ChannelChoice]:
        choices: list[ChannelChoice] = []
        async for dialog in self.client.iter_dialogs():
            if not getattr(dialog, "is_channel", False):
                continue
            entity = dialog.entity
            if getattr(entity, "megagroup", False):
                continue
            choices.append(
                ChannelChoice(
                    entity=entity,
                    title=dialog.name,
                    username=getattr(entity, "username", None),
                    channel_id=int(entity.id),
                )
            )
            if len(choices) >= limit:
                break
        return choices

    async def resolve_channel(self, value: str) -> ChannelChoice:
        entity = await self.client.get_entity(value)
        if getattr(entity, "megagroup", False):
            raise ValueError(f"{value!r} is a group, not a broadcast channel")
        return ChannelChoice(
            entity=entity,
            title=getattr(entity, "title", value),
            username=getattr(entity, "username", None),
            channel_id=int(entity.id),
        )

    async def fetch_text(
        self, channels: list[ChannelChoice], per_channel: int
    ) -> list[RawTelegramMessage]:

        retrieved_at = datetime.now(UTC)
        records: list[RawTelegramMessage] = []
        for channel in channels:
            async for message in self.client.iter_messages(channel.entity, limit=per_channel):
                if message.raw_text:
                    records.append(normalize_message(message, channel, retrieved_at))
        return records
