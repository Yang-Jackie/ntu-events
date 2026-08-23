from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sources.models import ProcessingStatus, RawSourceDocument, SourceRepresentation

from ingestion.models import (
    IngestionJob,
)
from ingestion.pipelines.telegram.adapter import TelegramMessage
from ingestion.raw_storage import RawContentStorage


@dataclass
class MessageWork:
    message: TelegramMessage
    representation: SourceRepresentation
    raw_document: RawSourceDocument | None = None


def upsert_representation(job: IngestionJob, message: TelegramMessage) -> MessageWork:
    representation, _created = SourceRepresentation.objects.get_or_create(
        source=job.source,
        external_identifier=message.identity,
        defaults={
            "source_url": message.source_url,
            "published_at": message.published_at,
            "content_type": "application/vnd.telegram.message+json",
            "first_seen_at": message.retrieved_at,
            "last_seen_at": message.retrieved_at,
            "metadata": _message_metadata(message),
        },
    )
    if not _created:
        representation.source_url = message.source_url
        representation.published_at = message.published_at
        representation.last_seen_at = message.retrieved_at
        representation.metadata = _message_metadata(message)
        representation.save(
            update_fields=("source_url", "published_at", "last_seen_at", "metadata")
        )
    return MessageWork(message=message, representation=representation)


def ensure_raw_document(
    item: MessageWork,
    job: IngestionJob,
    storage: RawContentStorage,
) -> RawSourceDocument:
    existing = RawSourceDocument.objects.filter(
        source_representation=item.representation,
        metadata__message_content_hash=item.message.content_hash,
    ).first()
    if existing:
        return existing
    stored = storage.save(item.message.raw_bytes(), suffix=".json")
    return RawSourceDocument.objects.create(
        source_representation=item.representation,
        ingestion_job=job,
        fetched_at=item.message.retrieved_at,
        storage_key=stored.storage_key,
        content_hash=stored.content_hash,
        language="en",
        processing_status=ProcessingStatus.PENDING,
        metadata={
            "source_kind": "telegram_message",
            "message_content_hash": item.message.content_hash,
        },
    )


def _message_metadata(message: TelegramMessage) -> dict[str, Any]:
    return {
        "channel_id": message.channel_id,
        "channel_username": message.channel_username,
        "edited_at": message.edited_at.isoformat() if message.edited_at else None,
        "reply_to_message_id": message.reply_to_message_id,
        "forwarded_from": message.forwarded_from,
        "content_hash": message.content_hash,
    }
