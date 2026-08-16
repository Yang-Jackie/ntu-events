import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from ingestion.contracts import (
    ExtractedMessage,
    ExtractionBatch,
    ScreeningBatch,
    ScreeningItem,
    ScreeningLabel,
)
from ingestion.pipelines.telegram.adapter import TelegramMessage
from ingestion.pipelines.telegram.extraction import ModelOutputError, OpenAITelegramModels


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
    reference_data = {"classifications": {"formats": []}, "venues": []}
    models.extract([message], reference_data=reference_data)

    for call in parse.call_args_list:
        assert call.kwargs["text"] == {"verbosity": "low"}
        assert "verbosity" not in call.kwargs
        prompt = json.loads(call.kwargs["input"][1]["content"])
        assert prompt["messages"][0]["published_at"] == "2026-08-11T02:00:00+08:00"
    extraction_prompt = json.loads(parse.call_args_list[1].kwargs["input"][1]["content"])
    assert extraction_prompt["reference_data"] == reference_data
    for response in responses:
        response.model_dump_json.assert_called_once_with(warnings=False)


def test_incomplete_response_raises_error_with_raw_provider_artifact() -> None:
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
    response = _response(None, status="incomplete", incomplete_reason="max_output_tokens")
    models = object.__new__(OpenAITelegramModels)
    models.extraction_model = "gpt-5-mini"
    models.client = SimpleNamespace(responses=SimpleNamespace(parse=Mock(return_value=response)))

    with pytest.raises(ModelOutputError) as captured:
        models.extract([message], reference_data={})

    assert captured.value.raw_response == b"{}"
    assert captured.value.response_identifier == "response-1"
    assert "max_output_tokens" in str(captured.value)


def _response(parsed, *, status="completed", incomplete_reason=None):
    return SimpleNamespace(
        output_parsed=parsed,
        status=status,
        incomplete_details=SimpleNamespace(reason=incomplete_reason),
        id="response-1",
        usage=None,
        model_dump_json=Mock(return_value="{}"),
    )
