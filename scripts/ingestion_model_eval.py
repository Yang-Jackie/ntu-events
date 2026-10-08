"""Offline scoring and conservative cost guards for ingestion model experiments.

These helpers do not change ingestion settings or call a provider. Prices are
Standard API USD rates verified on 2026-10-08, not an invoice reconciliation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import median

PRICES = {
    "gpt-6-luna": (0.10, 0.01, 0.125, 0.50),
    "gpt-5.6-luna": (0.20, 0.02, 0.25, 1.20),
}


class BudgetExceeded(RuntimeError):
    pass


def cost(model: str, usage: dict) -> float:
    """Count output/reasoning once and distinguish cache reads from writes."""
    input_rate, read_rate, write_rate, output_rate = PRICES[model]
    inputs, outputs = usage.get("input_tokens"), usage.get("output_tokens")
    if type(inputs) is not int or type(outputs) is not int or min(inputs, outputs) < 0:
        raise ValueError("Missing or invalid usage is unknown cost")
    details = usage.get("input_tokens_details") or {}
    reads = details.get("cached_tokens", 0)
    writes = details.get("cache_write_tokens", 0)
    if any(type(n) is not int or n < 0 for n in (reads, writes)):
        raise ValueError("Invalid cache usage")
    if reads + writes > inputs:
        raise ValueError("Cache counts exceed total input")
    input_multiplier, output_multiplier = (2, 1.5) if inputs > 272_000 else (1, 1)
    return (
        ((inputs - reads - writes) * input_rate + reads * read_rate + writes * write_rate)
        * input_multiplier
        + outputs * output_rate * output_multiplier
    ) / 1_000_000


def request_ceiling(model: str, input_tokens: int, max_output_tokens: int) -> float:
    """Assume cold cache writes and maximum generated output, including reasoning."""
    if type(input_tokens) is not int or input_tokens < 0:
        raise ValueError("Invalid input token count")
    if type(max_output_tokens) is not int or max_output_tokens <= 0:
        raise ValueError("Invalid output limit")
    return cost(
        model,
        {
            "input_tokens": input_tokens,
            "output_tokens": max_output_tokens,
            "input_tokens_details": {"cache_write_tokens": input_tokens},
        },
    )


class Budget:
    """Serial request ledger; reserve retries before the network call."""

    def __init__(self, limit: float):
        if not math.isfinite(limit) or limit <= 0:
            raise ValueError("A finite positive budget is required")
        self.limit = limit
        self.upper_spend = 0.0
        self.known_spend = 0.0
        self.pending = 0.0

    def reserve(self, ceiling: float, attempts: int = 3) -> None:
        if self.pending:
            raise RuntimeError("A request is already reserved")
        if not math.isfinite(ceiling) or ceiling <= 0 or type(attempts) is not int or attempts < 1:
            raise ValueError("Invalid reservation")
        reservation = ceiling * attempts
        if self.upper_spend + reservation > self.limit:
            raise BudgetExceeded("Insufficient budget for the next request and SDK retries")
        self.pending = reservation

    def settle(self, known: float | None, *, unknown_upper: float = 0) -> None:
        if not self.pending:
            raise RuntimeError("No pending reservation")
        upper = (known or 0) + unknown_upper
        if known is None and not unknown_upper:
            upper = self.pending
        if known is not None and (not math.isfinite(known) or known < 0):
            raise ValueError("Invalid recorded cost")
        if not math.isfinite(unknown_upper) or unknown_upper < 0 or upper > self.pending + 1e-9:
            raise ValueError("Usage exceeded its conservative reservation")
        self.upper_spend += upper
        self.known_spend += known or 0
        self.pending = 0


def sha256(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def values(root, parts: list[str]) -> list:
    if not parts:
        return [root]
    if isinstance(root, list):
        remaining = parts[1:] if parts[0] == "*" else parts
        return [v for item in root for v in values(item, remaining)]
    if not isinstance(root, dict) or parts[0] not in root:
        return []
    return values(root[parts[0]], parts[1:])


def check(root, rule: dict) -> bool:
    found = values(root, rule["path"].split("."))
    operation, expected = rule["op"], rule["value"]
    if operation == "all_in":
        return all(v in expected for v in found)
    if operation == "contains":
        return expected in found
    if operation == "contains_any":
        return any(v in expected for v in found)
    items = [item for value in found for item in (value if isinstance(value, list) else [value])]
    if operation == "count_eq":
        return len(items) == expected
    if operation == "object_contains":
        return any(
            isinstance(item, dict)
            and all(item.get(key) == value for key, value in expected.items())
            for item in items
        )
    if operation == "period_bounds":
        starts = [i.get("start_date") for i in items if isinstance(i, dict) and i.get("start_date")]
        ends = [
            i.get("end_date") or i.get("start_date")
            for i in items
            if isinstance(i, dict) and (i.get("end_date") or i.get("start_date"))
        ]
        return bool(
            starts
            and ends
            and min(starts) == expected["start_date"]
            and max(ends) == expected["end_date"]
        )
    raise ValueError(f"Unknown grading operation: {operation}")


def load_references(path: Path) -> tuple[dict, dict]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    references = {}
    for stage in ("extraction", "canonicalization"):
        merged = {}
        for filename in manifest[f"{stage}_files"]:
            source = (path.parent / filename).resolve()
            if path.parent.resolve() not in source.parents:
                raise ValueError("Reference path escaped its directory")
            part = json.loads(source.read_text(encoding="utf-8"))
            if merged.keys() & part.keys():
                raise ValueError("Duplicate reference case")
            merged.update(part)
        references[stage] = merged
    return manifest, references


def grade(row: dict, reference: dict) -> dict:
    if reference["status"] != "READY":
        raise ValueError("Reference answers must be finalized before grading")
    stage = row["stage"]
    available = row.get("status") == "SUCCEEDED"
    tests = []
    if stage == "extraction":
        root = row.get("events", [])
        expected = reference["expected_event_count"]
        allowed = expected if isinstance(expected, list) else [expected]
        tests.append(available and len(root) in allowed)
    else:
        root = row.get("final_event") or {}
        available = available and row.get("plan_status") == "APPLIED"
        tests.append(available and row.get("action") in reference["allowed_actions"])
        tests.append(
            available
            and (
                row.get("action") == "ADD"
                or row.get("target_event_id") == reference["target_event_id"]
            )
        )
        tests.append(available and row.get("other_matches_preserved", False))
    tests.extend(
        available and check(root, rule)
        for rule in reference["checks"]
        if "when_action" not in rule or row.get("action") == rule["when_action"]
    )
    return {
        "available": available,
        "checks_passed": sum(tests),
        "checks_total": len(tests),
        "all_passed": all(tests),
        "failures": [i for i, passed in enumerate(tests) if not passed],
    }


def summarize(rows: list[dict], references: dict) -> dict:
    groups = defaultdict(list)
    for row in rows:
        result = grade(row, references[row["stage"]][row["case_id"]])
        groups[(row["stage"], row["configuration"], row["stratum"])].append((row, result))
    report = {}
    for (stage, configuration, stratum), results in sorted(groups.items()):
        completed = [r for r, _ in results]
        scores = [score for _, score in results]
        report[f"{stage}/{configuration}/{stratum}"] = {
            "cases": len(results),
            "available": sum(s["available"] for s in scores),
            "all_checks_passed": sum(s["all_passed"] for s in scores),
            "checks_passed": sum(s["checks_passed"] for s in scores),
            "checks_total": sum(s["checks_total"] for s in scores),
            "first_response_available": sum(
                r.get("first_response_available", False) for r in completed
            ),
            "plan_statuses": {
                s: sum(r.get("plan_status") == s for r in completed)
                for s in {r.get("plan_status") for r in completed}
                if s is not None
            },
        }
    return report


def timing(samples: list[float]) -> dict:
    if not samples:
        return {"count": 0}
    ordered = sorted(samples)
    return {
        "count": len(samples),
        "median_s": median(samples),
        "p95_s": ordered[math.ceil(len(samples) * 0.95) - 1],
        "max_s": ordered[-1],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--references", type=Path, required=True)
    args = parser.parse_args()
    manifest, references = load_references(args.references)
    if manifest["review_status"] != "APPROVED":
        raise ValueError("Owner-review gate is not approved")
    results = json.loads(args.results.read_text(encoding="utf-8"))
    if results["metadata"]["dataset_sha256"] != manifest["dataset_sha256"]:
        raise ValueError("Results and references belong to different datasets")
    if results["metadata"]["reference_sha256"] != sha256(references):
        raise ValueError("Reference answers changed after the experiment")
    rows = results["rows"]
    print(json.dumps(summarize(rows, references), indent=2))


if __name__ == "__main__":
    main()
