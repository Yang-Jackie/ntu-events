import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from ingestion.errors import RetryableIngestionError
from ingestion.pipelines.telegram.adapter import TelegramFetcher, _normalize_message
from telethon.errors import ServerError, TimedOutError
from telethon.tl.types import MessageEntityTextUrl, MessageEntityUrl


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        ServerError(request=None, message="server unavailable"),
        TimedOutError(request=None, message="request timed out"),
    ],
)
async def test_transient_telegram_rpc_errors_are_retryable(tmp_path, error: Exception) -> None:
    client = SimpleNamespace(
        connect=AsyncMock(),
        is_user_authorized=AsyncMock(return_value=True),
        get_entity=AsyncMock(side_effect=error),
        disconnect=AsyncMock(),
    )
    fetcher = TelegramFetcher(api_id=1, api_hash="hash", session_path=tmp_path / "session")

    with (
        patch("ingestion.pipelines.telegram.adapter.TelegramClient", return_value=client),
        pytest.raises(RetryableIngestionError),
    ):
        await fetcher.fetch(
            source_configuration={"username": "test_channel"},
            message_limit=100,
            overlap=20,
        )

    client.disconnect.assert_awaited_once()


def test_telegram_message_preserves_entity_and_button_links() -> None:
    text = "Register here or visit https://example.com/info"
    hidden_link = MessageEntityTextUrl(
        offset=9,
        length=4,
        url="https://example.com/register",
    )
    visible_link = MessageEntityUrl(offset=23, length=24)
    message = SimpleNamespace(
        id=7,
        raw_text=text,
        date=datetime(2026, 8, 10, tzinfo=UTC),
        edit_date=None,
        reply_to=None,
        forward=None,
        reply_markup=SimpleNamespace(
            rows=[
                SimpleNamespace(
                    buttons=[
                        SimpleNamespace(
                            text="Join online",
                            url="https://meet.example.com/session",
                        )
                    ]
                )
            ]
        ),
        get_entities_text=Mock(
            return_value=[
                (hidden_link, "here"),
                (visible_link, "https://example.com/info"),
            ]
        ),
    )

    normalized = _normalize_message(
        message,
        SimpleNamespace(id=12345, title="Test Telegram channel"),
        "test_channel",
        datetime(2026, 8, 11, tzinfo=UTC),
    )

    assert [(link.kind, link.text, link.url) for link in normalized.links] == [
        ("TEXT_LINK", "here", "https://example.com/register"),
        ("VISIBLE_URL", "https://example.com/info", "https://example.com/info"),
        ("BUTTON", "Join online", "https://meet.example.com/session"),
    ]
    raw_payload = json.loads(normalized.raw_bytes())
    assert raw_payload["links"] == [
        {
            "kind": "TEXT_LINK",
            "text": "here",
            "url": "https://example.com/register",
        },
        {
            "kind": "VISIBLE_URL",
            "text": "https://example.com/info",
            "url": "https://example.com/info",
        },
        {
            "kind": "BUTTON",
            "text": "Join online",
            "url": "https://meet.example.com/session",
        },
    ]

    message.get_entities_text = Mock(
        return_value=[
            (
                MessageEntityTextUrl(
                    offset=9,
                    length=4,
                    url="https://example.com/updated-registration",
                ),
                "here",
            ),
            (visible_link, "https://example.com/info"),
        ]
    )
    edited = _normalize_message(
        message,
        SimpleNamespace(id=12345, title="Test Telegram channel"),
        "test_channel",
        datetime(2026, 8, 12, tzinfo=UTC),
    )

    assert edited.text == normalized.text
    assert edited.content_hash != normalized.content_hash
