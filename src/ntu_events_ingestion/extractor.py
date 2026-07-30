from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Protocol

from .models import ExtractionRecord, MessageExtraction, RawTelegramMessage

PROMPT_VERSION = "telegram-event-v2"
SCHEMA_VERSION = "event-candidate-research-v1"
SYSTEM_PROMPT = """Extract event facts from this public NTU Telegram post.
Return zero, one, or multiple events. An event is a time-bounded physical
activity a student can attend. Exclude online-only events, generic
opportunities, advertisements, and standalone deadlines. Never invent facts.
Resolve relative dates against the supplied publication time in
Asia/Singapore. Keep event times separate from registration deadlines. Preserve
raw venue wording, report ambiguities, and quote short exact evidence."""


class EventExtractor(Protocol):
    model: str

    async def extract(self, message: RawTelegramMessage) -> ExtractionRecord: ...


def extraction_cache_key(message: RawTelegramMessage, model: str) -> str:
    payload = "|".join([message.content_hash, model, PROMPT_VERSION, SCHEMA_VERSION])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class OpenAIEventExtractor:
    def __init__(self, model: str, max_retries: int = 1):
        try:
            from openai import AsyncOpenAI
        except ImportError as exc:
            raise RuntimeError(
                'OpenAI is not installed. Run: python -m pip install -e ".[dev]"'
            ) from exc
        self.model = model
        self.client = AsyncOpenAI(max_retries=max_retries)

    async def extract(self, message: RawTelegramMessage) -> ExtractionRecord:
        context = {
            "message_identity": message.identity,
            "channel_title": message.channel_title,
            "channel_username": message.channel_username,
            "published_at": message.published_at.isoformat(),
            "source_url": message.message_url,
            "text": message.text,
        }
        response = await self.client.responses.parse(
            model=self.model,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
            ],
            text_format=MessageExtraction,
            reasoning={"effort": "minimal"},
            verbosity="low",
        )
        if response.output_parsed is None:
            raise ValueError("OpenAI returned no parsed extraction")
        return ExtractionRecord(
            source_message_identity=message.identity,
            source_content_hash=message.content_hash,
            model=self.model,
            prompt_version=PROMPT_VERSION,
            schema_version=SCHEMA_VERSION,
            processed_at=datetime.now(UTC),
            result=response.output_parsed,
            response_id=response.id,
            usage=response.usage.to_dict() if response.usage else None,
            cache_key=extraction_cache_key(message, self.model),
        )

    async def close(self) -> None:
        await self.client.close()
