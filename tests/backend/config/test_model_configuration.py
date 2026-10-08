import runpy
from pathlib import Path

import pytest

DEFAULT_MODEL_SETTINGS = {
    "OPENAI_SCREENING_MODEL": "gpt-5-nano",
    "OPENAI_EXTRACTION_MODEL": "gpt-6-luna",
    "OPENAI_CANONICALIZATION_MODEL": "gpt-6-luna",
    "OPENAI_SCREENING_REASONING_EFFORT": "low",
    "OPENAI_EXTRACTION_REASONING_EFFORT": "medium",
    "OPENAI_CANONICALIZATION_REASONING_EFFORT": "medium",
}


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {
            "OPENAI_SCREENING_MODEL": "screening-model",
            "OPENAI_EXTRACTION_MODEL": "extraction-model",
            "OPENAI_CANONICALIZATION_MODEL": "canonicalization-model",
            "OPENAI_SCREENING_REASONING_EFFORT": "medium",
            "OPENAI_EXTRACTION_REASONING_EFFORT": "high",
            "OPENAI_CANONICALIZATION_REASONING_EFFORT": "low",
        },
    ],
)
def test_stage_model_settings_read_defaults_and_environment_overrides(monkeypatch, overrides):
    # Keep developer secrets and local .env overrides out of this configuration test.
    monkeypatch.setattr("dotenv.load_dotenv", lambda *args, **kwargs: None)
    for name in DEFAULT_MODEL_SETTINGS:
        monkeypatch.delenv(name, raising=False)
    for name, value in overrides.items():
        monkeypatch.setenv(name, value)

    settings_path = Path(__file__).resolve().parents[3] / "apps/backend/config/settings.py"
    configured = runpy.run_path(str(settings_path))

    assert {name: configured[name] for name in DEFAULT_MODEL_SETTINGS} == (
        DEFAULT_MODEL_SETTINGS | overrides
    )
