import hashlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from ingestion.canonicalization.decision_provider import (
    CANONICALIZATION_PROMPT,
    CANONICALIZATION_PROMPT_VERSION,
    OpenAICanonicalizationDecisionProvider,
)
from ingestion.canonicalization.worker import CanonicalizationWorkerRuntime
from ingestion.contracts import (
    CANONICALIZATION_SCHEMA_VERSION,
    CanonicalizationAction,
    CanonicalizationProposal,
)
from ingestion.model_outputs import ModelOutputError, prompt_cache_key
from ingestion.pipelines.telegram.adapter import TelegramLink, TelegramMessage
from ingestion.pipelines.telegram.contracts import (
    EXTRACTION_SCHEMA_VERSION,
    SCREENING_SCHEMA_VERSION,
    ExtractedMessage,
    ExtractionBatch,
    ScreeningBatch,
    ScreeningItem,
    ScreeningLabel,
)
from ingestion.pipelines.telegram.model_client import (
    EXTRACTION_PROMPT,
    EXTRACTION_PROMPT_VERSION,
    SCREENING_PROMPT_VERSION,
    OpenAITelegramModels,
)
from ingestion.pipelines.telegram.pipeline import TelegramTextPipeline
from ingestion.reference_data import candidate_reference_data_hash, canonical_json


@pytest.mark.parametrize(
    "efforts",
    [{}, {"screening_reasoning_effort": "high", "extraction_reasoning_effort": "low"}],
)
def test_model_calls_send_verbosity_inside_text_configuration(monkeypatch, efforts) -> None:
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
    client = SimpleNamespace(responses=SimpleNamespace(parse=parse))
    monkeypatch.setattr(
        "ingestion.pipelines.telegram.model_client.OpenAI", Mock(return_value=client)
    )
    models = OpenAITelegramModels(
        screening_model="gpt-5-nano", extraction_model="gpt-5-mini", **efforts
    )

    models.screen([message])
    reference_data = {"classifications": {"formats": []}, "venues": []}
    models.extract([message], reference_data=reference_data)

    for call in parse.call_args_list:
        assert call.kwargs["text"] == {"verbosity": "low"}
        assert "verbosity" not in call.kwargs
    screening_prompt = json.loads(parse.call_args_list[0].kwargs["input"][1]["content"])
    extraction_call = parse.call_args_list[1]
    extraction_catalog = json.loads(extraction_call.kwargs["input"][1]["content"][0]["text"])
    extraction_prompt = json.loads(extraction_call.kwargs["input"][2]["content"])
    for prompt in (screening_prompt, extraction_prompt):
        assert prompt["messages"][0]["published_at"] == "2026-08-11T02:00:00+08:00"
        assert prompt["messages"][0]["links"] == [
            {
                "kind": "BUTTON",
                "text": "Register",
                "url": "https://example.com/register",
            }
        ]
    assert extraction_catalog["reference_data"] == reference_data
    assert extraction_call.kwargs["input"][1]["content"][0]["prompt_cache_breakpoint"] == {
        "mode": "explicit"
    }
    assert extraction_call.kwargs["prompt_cache_options"] == {"mode": "explicit"}
    extraction_system_prompt = extraction_call.kwargs["input"][0]["content"]
    assert "separate start_time and end_time" in extraction_system_prompt
    assert "building-level venue as a" in extraction_system_prompt
    assert 'wording such as "near", "beside", or "opposite"' in extraction_system_prompt
    assert parse.call_args_list[0].kwargs["reasoning"] == {
        "effort": efforts.get("screening_reasoning_effort", "low")
    }
    assert parse.call_args_list[1].kwargs["reasoning"] == {
        "effort": efforts.get("extraction_reasoning_effort", "medium")
    }
    for response in responses:
        response.model_dump_json.assert_called_once_with(warnings=False)


@pytest.mark.parametrize("efforts", [{}, {"reasoning_effort": "high"}])
def test_canonicalization_decision_provider_is_source_neutral(monkeypatch, efforts) -> None:
    proposal = CanonicalizationProposal(
        action=CanonicalizationAction.LINK_ONLY,
        target_event_id=42,
        reasoning="Same event; no canonical change.",
        add_event=None,
        event_changes=[],
        classification_changes=[],
        organizer_changes=[],
        occurrence_changes=[],
        registration_changes=[],
    )
    response = _response(proposal)
    parse = Mock(return_value=response)
    client = SimpleNamespace(responses=SimpleNamespace(parse=parse))
    monkeypatch.setattr(
        "ingestion.canonicalization.decision_provider.OpenAI", Mock(return_value=client)
    )
    provider = OpenAICanonicalizationDecisionProvider(model_name="gpt-5-mini", **efforts)

    catalog = {"organizers": [], "venues": [], "classifications": {}}
    result = provider.decide(
        {"event_candidate": {"id": 1}, "possible_matches": [], "catalog": catalog}
    )

    assert result.parsed == proposal
    call = parse.call_args
    assert call.kwargs["model"] == "gpt-5-mini"
    assert call.kwargs["reasoning"] == {"effort": efforts.get("reasoning_effort", "medium")}
    assert call.kwargs["text"] == {"verbosity": "low"}
    system_prompt = call.kwargs["input"][0]["content"]
    assert "Singapore local time" in system_prompt
    assert "NEVER convert them again" in system_prompt
    assert "building-level venue as a fallback" in system_prompt
    assert 'wording such as "near", "beside"' in system_prompt
    catalog_block = call.kwargs["input"][1]["content"][0]
    assert json.loads(catalog_block["text"]) == {"catalog": catalog}
    assert catalog_block["prompt_cache_breakpoint"] == {"mode": "explicit"}
    dynamic_context = json.loads(call.kwargs["input"][2]["content"])
    assert dynamic_context["event_candidate"]["id"] == 1
    assert "catalog" not in dynamic_context
    assert call.kwargs["prompt_cache_options"] == {"mode": "explicit"}
    assert call.kwargs["prompt_cache_key"] == prompt_cache_key(
        stage="event-canonicalization",
        model="gpt-5-mini",
        prompt_version=CANONICALIZATION_PROMPT_VERSION,
        schema_version=CANONICALIZATION_SCHEMA_VERSION,
        reference_data_hash=candidate_reference_data_hash(catalog),
    )


@pytest.mark.parametrize("prompt", [EXTRACTION_PROMPT, CANONICALIZATION_PROMPT])
def test_model_prompts_require_singapore_wall_clock_times(prompt) -> None:
    assert "MUST use Singapore local time (Asia/Singapore, UTC+08:00)" in prompt
    assert "Convert explicitly non-Singapore source times" in prompt
    assert "adjust the associated date on rollover" in prompt
    assert "otherwise treat source times as Singapore local" in prompt
    assert "Every non-null time MUST be a plain HH:MM:SS wall-clock value" in prompt
    assert "NEVER emit Z, +08:00, +00:00," in prompt
    assert "or ANY offset or timezone suffix. No exceptions." in prompt
    assert "6pm -> 18:00:00" in prompt
    assert "10:00 UTC -> 18:00:00" in prompt
    assert "20:00 UTC -> 04:00:00 on the following date" in prompt
    assert "18:00+08:00 -> 18:00:00" in prompt
    assert "without timezone conversion" not in prompt


@pytest.mark.parametrize(
    "factory, arguments, patch_target",
    [
        (
            OpenAITelegramModels,
            {"screening_model": "screening", "extraction_model": "extraction"},
            "ingestion.pipelines.telegram.model_client.OpenAI",
        ),
        (
            OpenAICanonicalizationDecisionProvider,
            {"model_name": "canonicalization"},
            "ingestion.canonicalization.decision_provider.OpenAI",
        ),
    ],
)
def test_model_clients_use_45_second_timeout_and_two_sdk_retries(
    monkeypatch, factory, arguments, patch_target
) -> None:
    sdk = Mock()
    monkeypatch.setattr(patch_target, sdk)

    factory(**arguments)

    sdk.assert_called_once_with(max_retries=2, timeout=45)


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
    models.extraction_reasoning_effort = "medium"
    models.client = SimpleNamespace(responses=SimpleNamespace(parse=Mock(return_value=response)))

    with pytest.raises(ModelOutputError) as captured:
        models.extract([message], reference_data={})

    assert captured.value.raw_response == b"{}"
    assert captured.value.response_identifier == "response-1"
    assert "max_output_tokens" in str(captured.value)


def test_extraction_prompt_uses_an_explicit_stable_catalog_cache_boundary() -> None:
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
    models.extraction_reasoning_effort = "medium"
    models.client = SimpleNamespace(responses=SimpleNamespace(parse=parse))

    for batch in batches:
        # Identity validation only needs the first message of each batch to be returned.
        models.extract(batch[:1], reference_data=reference_data)

    catalog_blocks = [call.kwargs["input"][1]["content"][0] for call in parse.call_args_list]
    serialized_reference = canonical_json(reference_data)
    for call, block in zip(parse.call_args_list, catalog_blocks, strict=True):
        assert block["text"] == '{"reference_data":' + serialized_reference + "}"
        assert block["prompt_cache_breakpoint"] == {"mode": "explicit"}
        assert call.kwargs["prompt_cache_options"] == {"mode": "explicit"}
        assert json.loads(call.kwargs["input"][2]["content"])["messages"]
    assert len({block["text"] for block in catalog_blocks}) == 1

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


def test_telegram_pipeline_passes_stage_configuration_to_provider(monkeypatch, settings) -> None:
    settings.OPENAI_API_KEY = "test-key"
    settings.OPENAI_SCREENING_MODEL = "screening-model"
    settings.OPENAI_EXTRACTION_MODEL = "extraction-model"
    settings.OPENAI_SCREENING_REASONING_EFFORT = "medium"
    settings.OPENAI_EXTRACTION_REASONING_EFFORT = "high"
    factory = Mock()
    monkeypatch.setattr("ingestion.pipelines.telegram.pipeline.OpenAITelegramModels", factory)
    pipeline = TelegramTextPipeline()

    assert pipeline._get_models() is factory.return_value
    assert pipeline._get_models() is factory.return_value
    factory.assert_called_once_with(
        screening_model="screening-model",
        extraction_model="extraction-model",
        screening_reasoning_effort="medium",
        extraction_reasoning_effort="high",
    )


def test_canonicalization_worker_passes_stage_configuration_to_provider(monkeypatch, settings):
    settings.OPENAI_API_KEY = "test-key"
    settings.OPENAI_CANONICALIZATION_MODEL = "canonicalization-model"
    settings.OPENAI_CANONICALIZATION_REASONING_EFFORT = "high"
    factory = Mock()
    monkeypatch.setattr(
        "ingestion.canonicalization.worker.OpenAICanonicalizationDecisionProvider", factory
    )
    runtime = CanonicalizationWorkerRuntime()

    assert runtime._get_decision_provider() is factory.return_value
    assert runtime._get_decision_provider() is factory.return_value
    factory.assert_called_once_with(model_name="canonicalization-model", reasoning_effort="high")


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
    screening_material = (
        f"telegram-screening:gpt-5-nano:{SCREENING_PROMPT_VERSION}:{SCREENING_SCHEMA_VERSION}"
    )
    screening_key = prompt_cache_key(
        stage="telegram-screening",
        model="gpt-5-nano",
        prompt_version=SCREENING_PROMPT_VERSION,
        schema_version=SCREENING_SCHEMA_VERSION,
    )
    assert screening_key == hashlib.sha256(screening_material.encode("utf-8")).hexdigest()
    assert len(screening_key) == 64


def test_changed_prompt_and_schema_versions_do_not_reuse_previous_cache_routes() -> None:
    current_extraction = prompt_cache_key(
        stage="telegram-extraction",
        model="gpt-5-mini",
        prompt_version=EXTRACTION_PROMPT_VERSION,
        schema_version=EXTRACTION_SCHEMA_VERSION,
    )
    previous_extraction = prompt_cache_key(
        stage="telegram-extraction",
        model="gpt-5-mini",
        prompt_version="telegram-extraction-v7",
        schema_version=EXTRACTION_SCHEMA_VERSION,
    )
    current_canonicalization = prompt_cache_key(
        stage="event-canonicalization",
        model="gpt-5-mini",
        prompt_version=CANONICALIZATION_PROMPT_VERSION,
        schema_version=CANONICALIZATION_SCHEMA_VERSION,
    )
    previous_canonicalization = prompt_cache_key(
        stage="event-canonicalization",
        model="gpt-5-mini",
        prompt_version="event-canonicalization-v6",
        schema_version=CANONICALIZATION_SCHEMA_VERSION,
    )

    assert current_extraction != previous_extraction
    assert current_canonicalization != previous_canonicalization


def test_prompt_cache_key_stays_within_the_provider_limit_for_long_components() -> None:
    key = prompt_cache_key(
        stage="event-canonicalization-with-a-future-long-stage-name",
        model="gpt-5-mini-with-a-long-version-suffix",
        prompt_version="event-canonicalization-prompt-version-123",
        schema_version="canonicalization-plan-schema-version-123",
        reference_data_hash="a" * 64,
    )

    assert len(key) == 64


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
