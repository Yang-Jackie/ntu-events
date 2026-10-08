"""Offline progress reports and case review; no provider calls."""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from . import scoring as support
from .paths import run_directory


def analyze(directory: Path):
    progress = json.loads((directory / "progress.json").read_text(encoding="utf-8"))
    manifest, references = support.load_references(directory / "reference_answers.json")
    rows = progress["rows"]
    groups = defaultdict(list)
    calls = defaultdict(list)
    for row in rows:
        groups[(row["stage"], row["configuration"])].append(row)
    for call in progress["invocations"]:
        calls[(call["stage"], call["configuration"])].append(call)
    totals = {}
    for (stage, configuration), cases in sorted(groups.items()):
        requests = calls[(stage, configuration)]
        usage = [r["usage"] for r in requests if r.get("usage")]
        totals[stage + "/" + configuration] = {
            "cases": len(cases),
            "parsed": sum(r["status"] == "SUCCEEDED" for r in cases),
            "strict_cases_passed": sum(r["grade"]["all_passed"] for r in cases),
            "checks_passed": sum(r["grade"]["checks_passed"] for r in cases),
            "checks_total": sum(r["grade"]["checks_total"] for r in cases),
            "plan_statuses": dict(
                Counter(r.get("plan_status") for r in cases if r.get("plan_status"))
            ),
            "requests": len(requests),
            "request_timing": support.timing(
                [r["elapsed_seconds"] for r in requests if r.get("elapsed_seconds") is not None]
            ),
            "sdk_retries": sum(r.get("sdk_retries", 0) for r in requests),
            "output_errors": sum(bool(r.get("application_output_error")) for r in requests),
            "known_cost_usd": sum(
                support.cost(r["model"], r["usage"]) for r in requests if r.get("usage")
            ),
            "input_tokens": sum(u["input_tokens"] for u in usage),
            "cached_tokens": sum(
                u.get("input_tokens_details", {}).get("cached_tokens", 0) for u in usage
            ),
            "cache_write_tokens": sum(
                u.get("input_tokens_details", {}).get("cache_write_tokens", 0) for u in usage
            ),
            "output_tokens": sum(u["output_tokens"] for u in usage),
            "reasoning_tokens": sum(
                u.get("output_tokens_details", {}).get("reasoning_tokens", 0) for u in usage
            ),
        }
    print(
        json.dumps(
            {
                "complete": progress["metadata"]["complete"],
                "rows": len(rows),
                "known_cost_usd": progress["known_cost_usd"],
                "cost_upper_usd": progress["cost_upper_usd"],
                "active": progress["active_task"],
                "totals": totals,
                "strata": support.summarize(rows, references),
            },
            ensure_ascii=False,
        )
    )
    if progress["metadata"]["complete"]:
        (directory / "analysis.json").write_text(
            json.dumps({"totals": totals, "strata": support.summarize(rows, references)}, indent=2),
            encoding="utf-8",
        )


def review(directory: Path, case_id: str):
    dataset = json.loads((directory / "dataset.json").read_text(encoding="utf-8"))
    progress = json.loads((directory / "progress.json").read_text(encoding="utf-8"))
    selected = [r for r in progress["rows"] if r["case_id"] == case_id]
    case = next(
        c
        for stage in ("extraction", "canonicalization")
        for c in dataset[stage]
        if c["id"] == case_id
    )
    source = case.get("message") or case["context"]["raw_document"]
    unique = {}
    for row in selected:
        root = row.get("events") if row["stage"] == "extraction" else row.get("final_event")

        def compact(value):
            if isinstance(value, list):
                return [compact(item) for item in value]
            if not isinstance(value, dict):
                return value
            return {
                k: v
                for k, v in value.items()
                if k
                in (
                    "title",
                    "description",
                    "occurrences",
                    "registrations",
                    "formats",
                    "topics",
                    "purposes",
                    "audiences",
                    "organizers",
                )
            }

        root = compact(root)
        data = {
            "status": row["status"],
            "plan_status": row.get("plan_status"),
            "action": row.get("action"),
            "target": row.get("target_event_id"),
            "result": root,
            "issues": row.get("validation_issues"),
        }
        key = support.sha256(data)
        unique.setdefault(key, data)
    print(
        json.dumps(
            {
                "case": case_id,
                "source": source["text"],
                "published_at": source["published_at"],
                "links": source["links"],
                "variants": [
                    {"blind_id": key[:10], **value} for key, value in sorted(unique.items())
                ],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--review-case")
    args = parser.parse_args()
    directory = run_directory(args.run_dir)
    review(directory, args.review_case) if args.review_case else analyze(directory)
