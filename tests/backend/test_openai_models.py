import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

from ingestion.adapters.telegram import TelegramMessage
from ingestion.contracts import (
    ExtractedMessage,
    ExtractionBatch,
    ScreeningBatch,
    ScreeningItem,
    ScreeningLabel,
)
from ingestion.openai_models import OpenAITelegramModels


def test_model_calls_send_verbosity_inside_text_configuration() -> None:
    message = TelegramMessage(
        message_id=1,
        channel_id=123,
        channel_title="Test channel",
        channel_username="test_channel",
        source_url="https://t.me/test_channel/1",
        published_at=datetime(2026, 8, 10, 18, tzinfo=UTC),
        edited_at=None,
        text="Test message",
        reply_to_message_id=None,
        forwarded_from=None,
        retrieved_at=datetime(2026, 8, 11, tzinfo=UTC),
        content_hash="1" * 64,
    )
    responses = (
        _response(
            ScreeningBatch(
                results=[
                    ScreeningItem(
                        message_identity="1",
                        decision=ScreeningLabel.NOT_EVENT,
                        reason="not an event",
                        confidence=0.9,
                    )
                ]
            )
        ),
        _response(ExtractionBatch(results=[ExtractedMessage(message_identity="1", events=[])])),
    )
    parse = Mock(side_effect=responses)
    models = object.__new__(OpenAITelegramModels)
    models.screening_model = "gpt-5-nano"
    models.extraction_model = "gpt-5-mini"
    models.client = SimpleNamespace(responses=SimpleNamespace(parse=parse))

    models.screen([message])
    models.extract([message])

    for call in parse.call_args_list:
        assert call.kwargs["text"] == {"verbosity": "low"}
        assert "verbosity" not in call.kwargs
        prompt = json.loads(call.kwargs["input"][1]["content"])
        assert prompt["messages"][0]["published_at"] == "2026-08-11T02:00:00+08:00"
    for response in responses:
        response.model_dump_json.assert_called_once_with(warnings=False)


def _response(parsed):
    return SimpleNamespace(
        output_parsed=parsed,
        id="response-1",
        usage=None,
        model_dump_json=Mock(return_value="{}"),
    )
