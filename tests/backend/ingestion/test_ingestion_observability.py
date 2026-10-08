import json
import logging
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from ingestion.observability import (
    SDKRetryFilter,
    log_context,
    log_event,
    log_model_call,
    logged_phase,
)
from openai import APITimeoutError, OpenAI


@pytest.fixture
def workflow_logs(monkeypatch, caplog):
    monkeypatch.setattr(logging.getLogger("ingestion"), "propagate", True)
    caplog.set_level(logging.INFO, logger="ingestion")
    return caplog


def test_model_logs_include_usage_and_request_ids_without_input_or_raw_output(workflow_logs):
    usage = {
        "input_tokens": 1000,
        "output_tokens": 30,
        "input_tokens_details": {"cached_tokens": 900, "cache_write_tokens": 0},
        "output_tokens_details": {"reasoning_tokens": 20},
        "untrusted_detail": "secret-usage-detail",
    }
    response = SimpleNamespace(
        id="resp-1", _request_id="req-1", usage=SimpleNamespace(model_dump=Mock(return_value=usage))
    )
    call = Mock(return_value=response)

    with log_context(job_id=7, candidate_id=8):
        assert (
            log_model_call(
                call, stage="CANONICALIZATION", model_name="model", input="secret-source-text"
            )
            is response
        )
    events = [json.loads(record.message) for record in workflow_logs.records]
    finished = next(item for item in events if item["event"] == "model.request.finished")
    assert finished["job_id"] == 7
    assert finished["candidate_id"] == 8
    assert finished["request_id"] == "req-1"
    assert finished["response_id"] == "resp-1"
    assert finished["cached_tokens"] == 900
    assert finished["input_tokens"] == 1000
    assert finished["reasoning_tokens"] == 20
    assert finished["elapsed_seconds"] >= 0
    assert "secret-source-text" not in workflow_logs.text
    assert "secret-usage-detail" not in workflow_logs.text


def test_actual_sdk_timeout_retries_are_correlated_and_sanitized(monkeypatch, workflow_logs):
    output = StringIO()
    handler = logging.StreamHandler(output)
    handler.addFilter(SDKRetryFilter())
    monkeypatch.setattr(logging.getLogger("openai"), "handlers", [handler])
    monkeypatch.setattr(logging.getLogger("openai"), "level", logging.INFO)
    monkeypatch.setattr(logging.getLogger("openai"), "propagate", False)
    attempts = []

    def timeout(request):
        attempts.append(request)
        raise httpx.ReadTimeout("secret-transport-error", request=request)

    with OpenAI(
        api_key="secret-test-key",
        max_retries=2,
        timeout=45,
        http_client=httpx.Client(transport=httpx.MockTransport(timeout)),
    ) as client:
        with log_context(job_id=7, candidate_id=8), pytest.raises(APITimeoutError):
            log_model_call(
                client.responses.create,
                stage="CANONICALIZATION",
                model_name="model",
                model="model",
                input="secret-source-text",
            )

    assert len(attempts) == 3
    assert all(request.extensions["timeout"]["read"] == 45 for request in attempts)
    retries = [json.loads(line) for line in output.getvalue().splitlines()]
    assert [item["sdk_retry"] for item in retries] == [1, 2]
    assert all(item["candidate_id"] == 8 and item["job_id"] == 7 for item in retries)
    assert all(item["event"] == "model.sdk_retry" for item in retries)
    failures = [
        json.loads(record.message)
        for record in workflow_logs.records
        if json.loads(record.message)["event"] == "model.request.failed"
    ]
    assert len(failures) == 1
    assert failures[0]["sdk_retry"] == 2
    assert failures[0]["error_type"] == "APITimeoutError"
    combined = output.getvalue() + workflow_logs.text
    assert "secret-" not in combined
    assert "https://" not in combined


def test_sdk_filter_drops_non_retry_logs_and_uncorrelated_notices():
    filter_ = SDKRetryFilter()
    record = logging.LogRecord("openai", logging.INFO, "", 1, "secret-body", (), None)
    assert filter_.filter(record) is False
    retry = logging.LogRecord(
        "openai",
        logging.INFO,
        "",
        1,
        "Retrying request to %s in %f seconds",
        ("secret-url", 0.5),
        None,
    )
    assert filter_.filter(retry) is False


def test_phase_error_logs_only_error_type_and_restores_concurrent_context(workflow_logs):
    def run(job_id):
        with log_context(job_id=job_id), pytest.raises(ValueError):
            with logged_phase("test.phase"):
                raise ValueError("secret-error-payload")

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(run, [1, 2]))
    log_event("outside")
    events = [json.loads(record.message) for record in workflow_logs.records]
    failed = [item for item in events if item["event"] == "test.phase.failed"]
    assert {item["job_id"] for item in failed} == {1, 2}
    assert all(item["error_type"] == "ValueError" for item in failed)
    assert "job_id" not in events[-1]
    assert "secret-error-payload" not in workflow_logs.text
