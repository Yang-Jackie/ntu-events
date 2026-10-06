"""Content-free workflow timings and correlated provider retry notices."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

logger = logging.getLogger("ingestion")
_context: ContextVar[dict[str, Any] | None] = ContextVar("ingestion_log_context", default=None)


@contextmanager
def log_context(**fields: Any) -> Iterator[None]:
    token = _context.set((_context.get() or {}) | fields)
    try:
        yield
    finally:
        _context.reset(token)


def log_event(event: str, *, level: int = logging.INFO, **fields: Any) -> None:
    logger.log(level, _event_message(event, fields))


def _event_message(event: str, fields: dict[str, Any]) -> str:
    return json.dumps({"event": event, **(_context.get() or {}), **fields}, sort_keys=True)


@contextmanager
def logged_phase(phase: str, **fields: Any) -> Iterator[None]:
    started = time.monotonic()
    log_event(f"{phase}.started", **fields)
    try:
        yield
    except Exception as exc:
        log_event(
            f"{phase}.failed",
            level=logging.WARNING,
            elapsed_seconds=round(time.monotonic() - started, 3),
            error_type=type(exc).__name__,
            **fields,
        )
        raise
    else:
        log_event(
            f"{phase}.finished",
            elapsed_seconds=round(time.monotonic() - started, 3),
            **fields,
        )


def usage_fields(usage: dict[str, Any]) -> dict[str, int | None]:
    inputs = usage.get("input_tokens_details") or {}
    outputs = usage.get("output_tokens_details") or {}
    values = {
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "cached_tokens": inputs.get("cached_tokens"),
        "cache_write_tokens": inputs.get("cache_write_tokens"),
        "reasoning_tokens": outputs.get("reasoning_tokens"),
    }
    return {key: value if type(value) is int else None for key, value in values.items()}


def log_model_call(call: Callable[..., Any], *, stage: str, model_name: str, **kwargs: Any) -> Any:
    with log_context(stage=stage, model_name=model_name, sdk_retry=0):
        started = time.monotonic()
        log_event("model.request.started")
        try:
            response = call(**kwargs)
        except Exception as exc:
            log_event(
                "model.request.failed",
                level=logging.WARNING,
                elapsed_seconds=round(time.monotonic() - started, 3),
                error_type=type(exc).__name__,
                request_id=_identifier(getattr(exc, "request_id", None)),
            )
            raise
        usage = response.usage.model_dump(mode="json") if response.usage else {}
        log_event(
            "model.request.finished",
            elapsed_seconds=round(time.monotonic() - started, 3),
            request_id=_identifier(getattr(response, "_request_id", None)),
            response_id=_identifier(getattr(response, "id", None)),
            **usage_fields(usage),
        )
        return response


def _identifier(value: Any) -> str | None:
    return value[:128] if isinstance(value, str) else None


class SDKRetryFilter(logging.Filter):
    """Expose only SDK retry notices, never request bodies, headers, URLs or errors."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.msg != "Retrying request to %s in %f seconds":
            return False
        if not isinstance(record.args, tuple) or len(record.args) != 2:
            return False
        delay = record.args[1]
        if not isinstance(delay, (int, float)):
            return False
        context = _context.get()
        if context is None or "sdk_retry" not in context:
            return False
        context["sdk_retry"] += 1
        record.msg = _event_message("model.sdk_retry", {"retry_delay_seconds": round(delay, 3)})
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return True


class UTCFormatter(logging.Formatter):
    converter = time.gmtime
