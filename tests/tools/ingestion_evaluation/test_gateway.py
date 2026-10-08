import json
from types import SimpleNamespace

import pytest
from ingestion.pipelines.telegram.contracts import ExtractionBatch
from ntu_events_evaluation import run as experiment


class FakeResponse:
    id = "fake-response"
    model = "gpt-6-luna"
    service_tier = "default"

    def __init__(self):
        self.usage = SimpleNamespace(
            model_dump=lambda **kwargs: {
                "input_tokens": 1000,
                "output_tokens": 100,
                "input_tokens_details": {"cached_tokens": 600, "cache_write_tokens": 100},
            }
        )

    def model_dump_json(self, **kwargs):
        return json.dumps({"id": self.id})


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(experiment, "OUT", tmp_path)
    monkeypatch.setattr(experiment, "ledger", experiment.support.Budget(2))
    monkeypatch.setattr(experiment, "invocations", [])
    monkeypatch.setattr(experiment, "policy", "APPROVED BENCHMARK POLICY")
    monkeypatch.setattr(experiment, "save", lambda: None)
    seen = []
    responses = SimpleNamespace(
        parse=lambda **params: seen.append(params) or FakeResponse(),
        input_tokens=SimpleNamespace(count=lambda **params: SimpleNamespace(input_tokens=1000)),
    )
    client = SimpleNamespace(base_url="https://api.openai.com/v1/", responses=responses)
    return client, seen


def params():
    return dict(
        input=[
            {"role": "system", "content": "production prompt"},
            {"role": "user", "content": "specific evidence"},
        ],
        prompt_cache_key="original",
        text={"verbosity": "low"},
        text_format=ExtractionBatch,
    )


def test_gateway_appends_fixed_policy_without_mutating_production_inputs(setup):
    client, seen = setup
    gateway = experiment.Gateway(client, "extraction", "gpt-6-luna", "low")
    original = params()
    gateway.parse(**original)
    assert original["input"][0]["content"] == "production prompt"
    assert seen[0]["input"][0]["content"].endswith("APPROVED BENCHMARK POLICY")
    assert seen[0]["input"][1]["content"] == "specific evidence"
    assert seen[0]["max_output_tokens"] == 16384
    assert seen[0]["prompt_cache_key"] != "original"
    assert experiment.ledger.pending == 0
    assert experiment.ledger.known_spend > 0


def test_gateway_stops_before_generation_if_budget_cannot_cover_retries(setup):
    client, seen = setup
    experiment.ledger = experiment.support.Budget(0.000001)
    gateway = experiment.Gateway(client, "extraction", "gpt-6-luna", "low")
    with pytest.raises(experiment.support.BudgetExceeded):
        gateway.parse(**params())
    assert not seen
    assert not experiment.invocations


def test_gateway_unknown_usage_consumes_upper_reservation(setup):
    client, _seen = setup

    def fail(**kwargs):
        raise TimeoutError()

    client.responses.parse = fail
    gateway = experiment.Gateway(client, "canonicalization", "gpt-6-luna", "medium")
    with pytest.raises(TimeoutError):
        gateway.parse(**params())
    assert experiment.ledger.known_spend == 0
    assert experiment.ledger.upper_spend > 0
    assert experiment.invocations[-1]["status"] == "REQUEST_ERROR"
