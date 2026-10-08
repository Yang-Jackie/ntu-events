"""Private runner for the reviewed, frozen request-14 experiment."""

import argparse
import copy
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from openai.lib._parsing._responses import type_to_text_format_param
from pydantic import ValidationError

from . import replay
from . import scoring as support
from .paths import run_directory, run_file
from .prepare import fingerprint

OUT = None
DATABASE = None

CONFIGS = [
    ("gpt-6-luna", "low"),
    ("gpt-6-luna", "medium"),
    ("gpt-5.6-luna", "low"),
    ("gpt-5.6-luna", "medium"),
]
REPETITIONS = 2
ledger = support.Budget(2.0)
rows, invocations = [], []
metadata = {}
references = {}
policy = ""
active_task = {}
current_gateway = None


def save():
    report = {
        "metadata": metadata,
        "rows": rows,
        "invocations": invocations,
        "known_cost_usd": ledger.known_spend,
        "cost_upper_usd": ledger.upper_spend,
        "pending_reservation_usd": ledger.pending,
        "active_task": active_task,
    }
    temporary = OUT / "progress.tmp.json"
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(OUT / "progress.json")


class RetryCounter(logging.Handler):
    def __init__(self):
        super().__init__()
        self.retries = 0

    def emit(self, record):
        if record.msg == "Retrying request to %s in %f seconds":
            self.retries += 1
        else:
            try:
                if json.loads(record.getMessage()).get("event") == "model.sdk_retry":
                    self.retries += 1
            except (ValueError, AttributeError):
                pass


class Gateway:
    def __init__(self, client, stage, model, effort):
        self.client, self.stage, self.model, self.effort = client, stage, model, effort
        if urlparse(str(client.base_url)).hostname != "api.openai.com":
            raise RuntimeError("Nonstandard API billing host; confirm prices before testing")
        self.original_parse = client.responses.parse
        client.responses.parse = self.parse
        self.last_record = None

    def parse(self, **original):
        params = copy.deepcopy(original)
        params["input"][0]["content"] += "\n\n" + policy
        params["prompt_cache_key"] = support.sha256(
            {"original": params["prompt_cache_key"], "policy": support.sha256(policy)}
        )
        params["service_tier"] = "default"
        params["max_output_tokens"] = 16384 if self.stage == "extraction" else 8192
        schema = type_to_text_format_param(params["text_format"])
        input_tokens = self.client.responses.input_tokens.count(
            model=self.model, input=params["input"], text={**params["text"], "format": schema}
        ).input_tokens
        ceiling = support.request_ceiling(self.model, input_tokens, params["max_output_tokens"])
        ledger.reserve(ceiling, attempts=3)
        record = {
            "stage": self.stage,
            "model": self.model,
            "effort": self.effort,
            "configuration": self.model + "/" + self.effort,
            "task": copy.deepcopy(active_task),
            "input_tokens_preflight": input_tokens,
            "max_output_tokens": params["max_output_tokens"],
            "schema_sha256": support.sha256(schema),
            "request_input_sha256": support.sha256(params["input"]),
            "request_ceiling_usd": ceiling,
            "sdk_retries": 0,
            "status": "STARTED",
            "usage": None,
            "elapsed_seconds": None,
        }
        invocations.append(record)
        self.last_record = record
        save()
        counter = RetryCounter()
        logger = logging.getLogger("openai._base_client")
        logger.addHandler(counter)
        started = time.monotonic()
        try:
            response = self.original_parse(**params)
            record["usage"] = response.usage.model_dump(mode="json") if response.usage else None
            record["response_id"] = response.id
            record["request_id"] = getattr(response, "_request_id", None)
            record["returned_model"] = response.model
            record["status"] = "REQUEST_COMPLETED"
            artifact = OUT / "responses" / f"{len(invocations):04d}.json"
            artifact.parent.mkdir(exist_ok=True)
            artifact.write_text(response.model_dump_json(warnings=False), encoding="utf-8")
            record["artifact"] = artifact.name
            known = support.cost(self.model, record["usage"] or {})
            ledger.settle(known, unknown_upper=counter.retries * ceiling)
            if getattr(response, "service_tier", "default") not in (None, "default"):
                raise RuntimeError("Unexpected processing tier; stop to review actual pricing")
            return response
        except Exception as error:
            record["error_type"] = type(error).__name__
            record["status"] = "REQUEST_ERROR"
            if ledger.pending:
                ledger.settle(None)
            raise
        finally:
            logger.removeHandler(counter)
            record["sdk_retries"] = counter.retries
            record["elapsed_seconds"] = round(time.monotonic() - started, 3)
            save()


def message(raw):
    from ingestion.pipelines.telegram.adapter import TelegramLink, TelegramMessage

    value = dict(raw)
    for key in ("published_at", "edited_at", "retrieved_at"):
        value[key] = datetime.fromisoformat(value[key]) if value[key] else None
    value["links"] = tuple(TelegramLink(**link) for link in value.get("links", []))
    return TelegramMessage(**value)


def record_extraction(case, events, error, first_ok, configuration, repetition):
    from ingestion.candidates.validation.payload import validate_candidate

    issues = [
        validate_candidate(candidate, dataset["reference_data"]).issues for candidate in events
    ]
    row = {
        "stage": "extraction",
        "case_id": case["id"],
        "stratum": case["stratum"],
        "configuration": configuration,
        "repetition": repetition,
        "status": "SUCCEEDED" if error is None else "FAILED",
        "first_response_available": first_ok,
        "error_type": type(error).__name__ if error else None,
        "events": [event.model_dump(mode="json") for event in events],
        "candidate_issues": issues,
    }
    row["grade"] = support.grade(row, references["extraction"][case["id"]])
    rows.append(row)
    save()


def extract_batch(cases, models, gateway, configuration, repetition, first_ok=None):
    from ingestion.model_outputs import ModelOutputError

    try:
        result = models.extract(
            [message(case["message"]) for case in cases], reference_data=dataset["reference_data"]
        )
        results = {item.message_identity: item.events for item in result.parsed.results}
        for case in cases:
            record_extraction(
                case,
                results[str(case["message"]["message_id"])],
                None,
                first_ok is not False,
                configuration,
                repetition,
            )
    except (ModelOutputError, ValidationError) as error:
        gateway.last_record["application_output_error"] = type(error).__name__
        if len(cases) > 1:
            split = (len(cases) + 1) // 2
            extract_batch(cases[:split], models, gateway, configuration, repetition, False)
            extract_batch(cases[split:], models, gateway, configuration, repetition, False)
        else:
            record_extraction(cases[0], [], error, False, configuration, repetition)
    except support.BudgetExceeded:
        raise
    except Exception:
        # An unknown-usage request or infrastructure failure is a stop condition,
        # not free retries. Keep all artifacts and the conservative reservation.
        raise


def canonical_case(case, provider, gateway, configuration, repetition):
    from ingestion.model_outputs import ModelOutputError

    result, error = None, None
    attempts = 0
    while attempts < 3:
        attempts += 1
        try:
            result = provider.decide(case["context"])
            break
        except (ModelOutputError, ValidationError) as exc:
            error = exc
            gateway.last_record["application_output_error"] = type(exc).__name__
    row = {
        "stage": "canonicalization",
        "case_id": case["id"],
        "stratum": case["stratum"],
        "configuration": configuration,
        "repetition": repetition,
        "model_attempts": attempts,
        "first_response_available": result is not None and attempts == 1,
        "status": "SUCCEEDED" if result else "FAILED",
        "error_type": type(error).__name__ if result is None and error else None,
    }
    if result:
        proposal = result.parsed.model_dump(mode="json")
        applied = replay.replay(case, result.parsed, database=DATABASE)
        row.update(
            {
                "proposal": proposal,
                "action": proposal["action"],
                "target_event_id": proposal["target_event_id"],
                "plan_status": applied["status"],
                "final_event": applied["final_event"],
                "validation_issues": applied["issues"],
                "other_matches_preserved": applied["other_matches_preserved"],
            }
        )
    row["grade"] = support.grade(row, references["canonicalization"][case["id"]])
    rows.append(row)
    save()


def main(execute, *, directory: Path, database: str, budget_usd: float = 2.0):
    global \
        OUT, \
        DATABASE, \
        ledger, \
        dataset, \
        references, \
        metadata, \
        policy, \
        active_task, \
        rows, \
        invocations
    OUT, DATABASE = directory, database
    rows, invocations = [], []
    ledger = support.Budget(budget_usd)
    replay.require_isolation(database)
    from ingestion.canonicalization.decisions.provider import OpenAICanonicalizationDecisionProvider
    from ingestion.contracts import CanonicalizationProposal
    from ingestion.pipelines.telegram.contracts import ExtractionBatch
    from ingestion.pipelines.telegram.model_client import OpenAITelegramModels

    dataset = json.loads((OUT / "dataset.json").read_text(encoding="utf-8"))
    unsigned = {k: v for k, v in dataset.items() if k != "sha256"}
    if support.sha256(unsigned) != dataset["sha256"]:
        raise RuntimeError("Frozen dataset hash changed")
    manifest, references = support.load_references(OUT / "reference_answers.json")
    if manifest["review_status"] != "APPROVED" or manifest["dataset_sha256"] != dataset["sha256"]:
        raise RuntimeError("Reference approval or dataset linkage is invalid")
    for stage in ("extraction", "canonicalization"):
        if {c["id"] for c in dataset[stage]} != references[stage].keys():
            raise RuntimeError("Dataset and reference cases differ")
        if any(r["status"] != "READY" for r in references[stage].values()):
            raise RuntimeError("Unreviewed reference answers remain")
    policy = json.loads(
        (run_file(OUT, manifest["benchmark_policy_file"])).read_text(encoding="utf-8")
    )["addendum"]
    from ingestion.canonicalization.decisions.provider import CANONICALIZATION_PROMPT
    from ingestion.pipelines.telegram.model_client import EXTRACTION_PROMPT

    metadata = {
        "dataset_sha256": dataset["sha256"],
        "reference_sha256": support.sha256(references),
        "policy_sha256": support.sha256(policy),
        "policy": policy,
        "configurations": CONFIGS,
        "repetitions": REPETITIONS,
        "budget_usd": budget_usd,
        "sdk_timeout_seconds": 45,
        "sdk_retries": 2,
        "serial_requests": True,
        "extraction_batch_size": 5,
        "pricing_verified_on": "2026-10-08",
        "extraction_prompt_sha256": support.sha256(EXTRACTION_PROMPT + policy),
        "canonicalization_prompt_sha256": support.sha256(CANONICALIZATION_PROMPT + policy),
        "schema_sha256": {
            "extraction": support.sha256(type_to_text_format_param(ExtractionBatch)),
            "canonicalization": support.sha256(type_to_text_format_param(CanonicalizationProposal)),
        },
        "complete": False,
    }
    if not execute:
        print(
            json.dumps(
                {
                    "dry_run_valid": True,
                    "database": DATABASE,
                    "cases": {s: len(dataset[s]) for s in references},
                    "metadata": metadata,
                }
            )
        )
        return
    if (OUT / "progress.json").exists():
        raise RuntimeError("An experiment already exists; do not reset its spending ledger")
    before = fingerprint()
    clients = {}
    try:
        for model, effort in CONFIGS:
            models = OpenAITelegramModels(
                screening_model="gpt-5-nano",
                extraction_model=model,
                extraction_reasoning_effort=effort,
            )
            provider = OpenAICanonicalizationDecisionProvider(
                model_name=model, reasoning_effort=effort
            )
            models.client.models.retrieve(model)
            clients[(model, effort)] = (
                models,
                provider,
                Gateway(models.client, "extraction", model, effort),
                Gateway(provider.client, "canonicalization", model, effort),
            )
        save()
        tasks = [
            ("extraction", dataset["extraction"][i : i + 5])
            for i in range(0, len(dataset["extraction"]), 5)
        ]
        tasks += [("canonicalization", [case]) for case in dataset["canonicalization"]]
        for repetition in range(1, REPETITIONS + 1):
            for task_index, (stage, cases) in enumerate(tasks):
                shift = (task_index + repetition - 1) % len(CONFIGS)
                order = CONFIGS[shift:] + CONFIGS[:shift]
                for model, effort in order:
                    configuration = model + "/" + effort
                    active_task = {
                        "stage": stage,
                        "case_ids": [c["id"] for c in cases],
                        "configuration": configuration,
                        "repetition": repetition,
                    }
                    models, provider, extraction_gateway, canonical_gateway = clients[
                        (model, effort)
                    ]
                    print(
                        json.dumps(
                            {
                                "event": "benchmark.task",
                                **active_task,
                                "known_cost_usd": round(ledger.known_spend, 6),
                            }
                        ),
                        flush=True,
                    )
                    if stage == "extraction":
                        extract_batch(cases, models, extraction_gateway, configuration, repetition)
                    else:
                        canonical_case(
                            cases[0], provider, canonical_gateway, configuration, repetition
                        )
        metadata["complete"] = True
    except Exception as error:
        metadata["stop_reason"] = type(error).__name__
        print(
            json.dumps({"event": "benchmark.stopped", "reason": type(error).__name__}), flush=True
        )
    finally:
        for models, provider, *_rest in clients.values():
            models.close()
            provider.close()
        metadata["rollback_verified"] = fingerprint() == before
        active_task = {}
        save()
        (OUT / "summary.json").write_text(
            json.dumps(support.summarize(rows, references), indent=2), encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "event": "benchmark.finished",
                    "complete": metadata["complete"],
                    "rows": len(rows),
                    "requests": len(invocations),
                    "known_cost_usd": ledger.known_spend,
                    "cost_upper_usd": ledger.upper_spend,
                    "rollback_verified": metadata["rollback_verified"],
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--budget-usd", type=float, default=2.0)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    main(
        args.execute,
        directory=run_directory(args.run_dir),
        database=args.database,
        budget_usd=args.budget_usd,
    )
