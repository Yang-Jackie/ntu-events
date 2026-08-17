import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from ingestion.contracts import (
    EXTRACTION_SCHEMA_VERSION,
    SCREENING_SCHEMA_VERSION,
    ExtractedMessage,
    ExtractionBatch,
    ScreeningBatch,
    ScreeningItem,
    ScreeningLabel,
)
from ingestion.pipelines.telegram.adapter import TelegramLink, TelegramMessage
from ingestion.pipelines.telegram.extraction import (
    EXTRACTION_PROMPT_VERSION,
    SCREENING_PROMPT_VERSION,
    ModelOutputError,
    OpenAITelegramModels,
    prompt_cache_key,
)
from ingestion.reference_data import candidate_reference_data_hash, canonical_json


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
        links=(
            TelegramLink(
                kind="BUTTON",
                text="Register",
                url="https://example.com/register",
            ),
        ),
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
        assert prompt["messages"][0]["links"] == [
            {
                "kind": "BUTTON",
                "text": "Register",
                "url": "https://example.com/register",
            }
        ]
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


def test_extraction_prompt_keeps_reference_data_in_the_cacheable_prefix() -> None:
    reference_data = {
        "venues": [{"name": "LT1", "id": 1, "aliases": ["lt 1"]}],
        "classifications": {"formats": [{"code": "TALK", "label": "Talk"}]},
    }
    batches = ([_message(1), _message(2)], [_message(3)])
    parse = Mock(
        side_effect=[
            _response(ExtractionBatch(results=[ExtractedMessage(message_identity="1", events=[])])),
            _response(ExtractionBatch(results=[ExtractedMessage(message_identity="3", events=[])])),
        ]
    )
    models = object.__new__(OpenAITelegramModels)
    models.extraction_model = "gpt-5-mini"
    models.client = SimpleNamespace(responses=SimpleNamespace(parse=parse))

    for batch in batches:
        # Identity validation only needs the first message of each batch to be returned.
        models.extract(batch[:1], reference_data=reference_data)

    contents = [call.kwargs["input"][1]["content"] for call in parse.call_args_list]
    serialized_reference = canonical_json(reference_data)
    for content in contents:
        # The static catalog must lead the payload, byte-identically to the hashed form,
        # or it falls outside the shared prefix and is billed at full rate every call.
        assert content.startswith('{"reference_data":' + serialized_reference + ',"messages":')
    prefixes = {content.split(',"messages":')[0] for content in contents}
    assert len(prefixes) == 1

    # Distinct batches must share one cache key, otherwise every call routes to a cold cache.
    cache_keys = [call.kwargs["prompt_cache_key"] for call in parse.call_args_list]
    assert len(set(cache_keys)) == 1
    assert cache_keys[0] == prompt_cache_key(
        stage="telegram-extraction",
        model="gpt-5-mini",
        prompt_version=EXTRACTION_PROMPT_VERSION,
        schema_version=EXTRACTION_SCHEMA_VERSION,
        reference_data_hash=candidate_reference_data_hash(reference_data),
    )


def test_prompt_cache_key_tracks_the_reference_catalog() -> None:
    def key(reference_data: dict) -> str:
        return prompt_cache_key(
            stage="telegram-extraction",
            model="gpt-5-mini",
            prompt_version=EXTRACTION_PROMPT_VERSION,
            schema_version=EXTRACTION_SCHEMA_VERSION,
            reference_data_hash=candidate_reference_data_hash(reference_data),
        )

    assert key({"venues": []}) != key({"venues": [{"id": 1}]})
    assert key({"venues": [], "classifications": {}}) == key({"classifications": {}, "venues": []})
    assert (
        prompt_cache_key(
            stage="telegram-screening",
            model="gpt-5-nano",
            prompt_version=SCREENING_PROMPT_VERSION,
            schema_version=SCREENING_SCHEMA_VERSION,
        )
        == f"telegram-screening:gpt-5-nano:{SCREENING_PROMPT_VERSION}:{SCREENING_SCHEMA_VERSION}"
    )


def _message(message_id: int) -> TelegramMessage:
    return TelegramMessage(
        message_id=message_id,
        channel_id=123,
        channel_title="Test channel",
        channel_username="test_channel",
        source_url=f"https://t.me/test_channel/{message_id}",
        published_at=datetime(2026, 8, 10, 18, tzinfo=UTC),
        edited_at=None,
        text=f"Test message {message_id}",
        reply_to_message_id=None,
        forwarded_from=None,
        retrieved_at=datetime(2026, 8, 11, tzinfo=UTC),
        content_hash=str(message_id) * 64,
    )


def _response(parsed, *, status="completed", incomplete_reason=None):
    return SimpleNamespace(
        output_parsed=parsed,
        status=status,
        incomplete_details=SimpleNamespace(reason=incomplete_reason),
        id="response-1",
        usage=None,
        model_dump_json=Mock(return_value="{}"),
    )
