"""Read-only summaries of sanitized workflow JSON piped from Docker logs."""

import json
import statistics
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime


def summarize(lines, *, now=None):
    now = now or datetime.now(UTC)
    records = []
    for line in lines:
        start = line.find("{")
        if start < 0:
            continue
        try:
            record = json.loads(line[start:])
            stamp = line[:start].split("|")[-1].strip().split()[0]
            record["timestamp"] = stamp
            record["at"] = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            if "event" in record:
                records.append(record)
        except (ValueError, IndexError):
            continue
    records.sort(key=lambda r: r["at"])

    def key(r):
        return tuple(
            r.get(k)
            for k in (
                "stage",
                "job_id",
                "batch_index",
                "candidate_id",
                "model_attempt",
                "job_attempt",
            )
        )

    def timing(values):
        values = sorted(values)
        return (
            {
                "count": len(values),
                "median_s": round(statistics.median(values), 3),
                "p95_s": values[min(len(values) - 1, int(len(values) * 0.95))],
                "max_s": max(values),
            }
            if values
            else {"count": 0}
        )

    active_requests, active_candidates = {}, {}
    stage_records = defaultdict(list)
    phases = defaultdict(list)
    queues = defaultdict(list)
    candidate_durations = []
    retries = []
    for r in records:
        event = r["event"]
        if event == "model.request.started":
            active_requests[key(r)] = r.copy()
        elif event in ("model.request.finished", "model.request.failed"):
            active_requests.pop(key(r), None)
            stage_records[r["stage"]].append(r)
        elif event == "model.sdk_retry":
            retries.append(r)
            if key(r) in active_requests:
                active_requests[key(r)]["sdk_retry"] = r["sdk_retry"]
        elif event == "canonicalization.candidate.started":
            active_candidates[r["candidate_id"]] = r.copy()
        elif event in ("canonicalization.candidate.finished", "canonicalization.candidate.failed"):
            active_candidates.pop(r["candidate_id"], None)
            candidate_durations.append(
                {k: r[k] for k in ("candidate_id", "event", "elapsed_seconds")}
            )
        if event.startswith("canonicalization.") and event.endswith((".finished", ".failed")):
            if "elapsed_seconds" in r:
                phases[event.rsplit(".", 1)[0]].append(r["elapsed_seconds"])
        if event == "ingestion.batch.started":
            queues[r["stage"]].append(r["queue_wait_seconds"])

    def active_summary(r):
        return {k: v for k, v in r.items() if k != "at"} | {
            "elapsed_s": round((now - r["at"]).total_seconds(), 1)
        }

    stages = {}
    for stage, rows in stage_records.items():
        success = [r for r in rows if r["event"] == "model.request.finished"]
        stages[stage] = {
            "finished": len(success),
            "failed": len(rows) - len(success),
            "errors": dict(Counter(r.get("error_type") for r in rows if r.get("error_type"))),
            "actual_request_timing": timing([r["elapsed_seconds"] for r in rows]),
            "sdk_retry_notices": sum(r["stage"] == stage for r in retries),
            "input_tokens": sum(r.get("input_tokens") or 0 for r in success),
            "cached_tokens": sum(r.get("cached_tokens") or 0 for r in success),
            "cache_write_tokens": sum(r.get("cache_write_tokens") or 0 for r in success),
        }

    return {
        "timestamp": now.isoformat(),
        "record_count": len(records),
        "stages": stages,
        "active_requests": [active_summary(r) for r in active_requests.values()],
        "active_candidates": [active_summary(r) for r in active_candidates.values()],
        "canonical_phase_timings": {k: timing(v) for k, v in phases.items()},
        "queue_wait_timings": {k: timing(v) for k, v in queues.items()},
        "slowest_candidates": sorted(
            candidate_durations, key=lambda r: r["elapsed_seconds"], reverse=True
        )[:8],
        "latest_sdk_retries": [{k: v for k, v in r.items() if k != "at"} for r in retries[-8:]],
        "timeout_reviews": [
            {k: v for k, v in r.items() if k != "at"}
            for r in records
            if r["event"] == "canonicalization.timeout_review"
        ],
        "last_event": {k: v for k, v in records[-1].items() if k != "at"} if records else None,
    }


def main() -> None:
    print(json.dumps(summarize(sys.stdin), default=str))


if __name__ == "__main__":
    main()
