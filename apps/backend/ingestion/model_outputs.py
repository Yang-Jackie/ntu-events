from __future__ import annotations

import hashlib
from dataclasses import dataclass

from pydantic import BaseModel


@dataclass(frozen=True)
class ModelResult[ParsedT: BaseModel]:
    parsed: ParsedT
    response_identifier: str
    token_usage: dict
    raw_response: bytes


class ModelOutputError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        raw_response: bytes,
        response_identifier: str,
        token_usage: dict,
    ):
        super().__init__(message)
        self.raw_response = raw_response
        self.response_identifier = response_identifier
        self.token_usage = token_usage


def prompt_cache_key(
    *,
    stage: str,
    model: str,
    prompt_version: str,
    schema_version: str,
    reference_data_hash: str = "",
) -> str:
    """Build a provider-safe cache-routing key for one stable prompt prefix."""
    parts = [stage, model, prompt_version, schema_version]
    if reference_data_hash:
        parts.append(reference_data_hash)
    return hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()


def model_result[ParsedT: BaseModel](response, parsed: ParsedT) -> ModelResult[ParsedT]:
    raw_response, response_identifier, token_usage = response_artifact(response)
    return ModelResult(
        parsed=parsed,
        response_identifier=response_identifier,
        token_usage=token_usage,
        raw_response=raw_response,
    )


def model_output_error(response, message: str) -> ModelOutputError:
    raw_response, response_identifier, token_usage = response_artifact(response)
    return ModelOutputError(
        message,
        raw_response=raw_response,
        response_identifier=response_identifier,
        token_usage=token_usage,
    )


def response_artifact(response) -> tuple[bytes, str, dict]:
    usage = response.usage.model_dump(mode="json") if response.usage else {}
    return (
        response.model_dump_json(warnings=False).encode("utf-8"),
        response.id,
        usage,
    )
