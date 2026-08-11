from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from telethon import TelegramClient
from telethon.errors import FloodWaitError, ServerError, TimedOutError

SINGAPORE_TIMEZONE = timezone(timedelta(hours=8), "Asia/Singapore")


class TelegramConfigurationError(RuntimeError):
    pass


class TelegramAuthenticationRequired(RuntimeError):
    pass


class TelegramRetryableError(RuntimeError):
    def __init__(self, message: str, *, retry_after_seconds: int = 30):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class TelegramMessage:
    message_id: int
    channel_id: int
    channel_title: str
    channel_username: str | None
    source_url: str
    published_at: datetime
    edited_at: datetime | None
    text: str
    reply_to_message_id: int | None
    forwarded_from: str | None
    retrieved_at: datetime
    content_hash: str

    @property
    def identity(self) -> str:
        return str(self.message_id)

    def prompt_record(self) -> dict[str, Any]:
        return {
            "message_identity": self.identity,
            "channel_title": self.channel_title,
            "channel_username": self.channel_username,
            "published_at": self.published_at.astimezone(SINGAPORE_TIMEZONE).isoformat(),
            "source_url": self.source_url,
            "text": self.text,
        }

    def raw_bytes(self) -> bytes:
        payload = asdict(self)
        for key in ("published_at", "edited_at", "retrieved_at"):
            value = payload[key]
            payload[key] = value.isoformat() if value else None
        return json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")


@dataclass(frozen=True)
class TelegramFetchResult:
    messages: list[TelegramMessage]
    latest_message_id: int | None


@dataclass(frozen=True)
class TelegramChannel:
    channel_id: int
    title: str
    username: str


class TelegramFetcher:
    def __init__(self, *, api_id: int, api_hash: str, session_path: Path):
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_path = session_path

    async def fetch(
        self,
        *,
        source_configuration: dict[str, Any],
        message_limit: int,
        overlap: int,
    ) -> TelegramFetchResult:
        reference = source_configuration.get("username") or source_configuration.get("channel_id")
        if not reference:
            raise TelegramConfigurationError(
                "Telegram source configuration requires username or channel_id"
            )
        cursor = int(source_configuration.get("last_message_id") or 0)
        pending_ids = [int(value) for value in source_configuration.get("pending_message_ids", [])]
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        client = TelegramClient(str(self.session_path), self.api_id, self.api_hash)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                raise TelegramAuthenticationRequired(
                    "The saved Telegram session is missing or expired; run telegram_login"
                )
            entity = await client.get_entity(reference)
            if getattr(entity, "megagroup", False):
                raise TelegramConfigurationError("Configured source is a group, not a channel")
            username = getattr(entity, "username", None)
            if not username:
                raise TelegramConfigurationError("Configured Telegram channel is not public")

            raw_messages: dict[int, Any] = {}
            if pending_ids:
                for message in await client.get_messages(entity, ids=pending_ids):
                    if message is not None:
                        raw_messages[message.id] = message
            if cursor:
                async for message in client.iter_messages(
                    entity,
                    min_id=cursor,
                    reverse=True,
                    limit=message_limit,
                ):
                    raw_messages[message.id] = message
                if overlap:
                    async for message in client.iter_messages(
                        entity,
                        max_id=cursor + 1,
                        limit=overlap,
                    ):
                        raw_messages[message.id] = message
            else:
                async for message in client.iter_messages(entity, limit=message_limit):
                    raw_messages[message.id] = message

            retrieved_at = datetime.now(UTC)
            normalized = [
                _normalize_message(message, entity, username, retrieved_at)
                for message in raw_messages.values()
                if message.raw_text
            ]
            return TelegramFetchResult(
                messages=sorted(normalized, key=lambda item: item.message_id),
                latest_message_id=max(raw_messages, default=None),
            )
        except FloodWaitError as exc:
            raise TelegramRetryableError(
                f"Telegram requested a flood wait of {exc.seconds} seconds",
                retry_after_seconds=exc.seconds,
            ) from exc
        except (OSError, TimeoutError, ServerError, TimedOutError) as exc:
            raise TelegramRetryableError(str(exc)) from exc
        finally:
            await client.disconnect()

    async def list_public_channels(self, limit: int = 100) -> list[TelegramChannel]:
        self.session_path.parent.mkdir(parents=True, exist_ok=True)
        client = TelegramClient(str(self.session_path), self.api_id, self.api_hash)
        try:
            await client.connect()
            if not await client.is_user_authorized():
                raise TelegramAuthenticationRequired(
                    "The saved Telegram session is missing or expired; run telegram_login"
                )
            result: list[TelegramChannel] = []
            async for dialog in client.iter_dialogs():
                entity = dialog.entity
                username = getattr(entity, "username", None)
                if not getattr(dialog, "is_channel", False):
                    continue
                if getattr(entity, "megagroup", False) or not username:
                    continue
                result.append(
                    TelegramChannel(
                        channel_id=int(entity.id),
                        title=dialog.name,
                        username=username,
                    )
                )
                if len(result) >= limit:
                    break
            return result
        finally:
            await client.disconnect()


def _normalize_message(
    message: Any,
    entity: Any,
    username: str,
    retrieved_at: datetime,
) -> TelegramMessage:
    text = message.raw_text or ""
    reply = getattr(message, "reply_to", None)
    forwarded = getattr(message, "forward", None)
    forwarded_from = str(forwarded) if forwarded else None
    return TelegramMessage(
        message_id=int(message.id),
        channel_id=int(entity.id),
        channel_title=str(getattr(entity, "title", username)),
        channel_username=username,
        source_url=f"https://t.me/{username}/{message.id}",
        published_at=message.date,
        edited_at=getattr(message, "edit_date", None),
        text=text,
        reply_to_message_id=getattr(reply, "reply_to_msg_id", None),
        forwarded_from=forwarded_from,
        retrieved_at=retrieved_at,
        content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )
