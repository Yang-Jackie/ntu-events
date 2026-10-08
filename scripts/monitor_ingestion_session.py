"""Read-only ingestion request diagnostics; no provider calls or database writes."""

import argparse
import json
import os
import statistics
import sys
from collections import Counter
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request-id", type=int, required=True)
    parser.add_argument("--details", action="store_true")
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/backend"))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
    from django.db import connection, transaction
    from django.db.models import Count
    from django.utils import timezone
    from events.models import Event
    from ingestion.models import (
        CandidateMatch,
        CanonicalizationPlan,
        EventCandidate,
        IngestionJob,
        ModelInvocation,
    )

    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        now = timezone.now()
        jobs = IngestionJob.objects.filter(request_id=args.request_id).order_by("pk")
        candidates = EventCandidate.objects.filter(
            extraction_run__raw_source_document__ingestion_job__in=jobs
        )
        plans = CanonicalizationPlan.objects.filter(event_candidate__in=candidates)
        invocations = list(
            ModelInvocation.objects.filter(job__in=jobs)
            .order_by("pk")
            .values(
                "id",
                "job_id",
                "stage",
                "batch_index",
                "attempt_number",
                "status",
                "model_name",
                "started_at",
                "completed_at",
                "error_type",
                "error_message",
                "token_usage",
                "raw_output_storage_key",
            )
        )
        for invocation in invocations:
            invocation["duration_s"] = (
                round((invocation["completed_at"] - invocation["started_at"]).total_seconds(), 3)
                if invocation["completed_at"]
                else None
            )
        stages = {}
        for stage in sorted({inv["stage"] for inv in invocations}):
            rows = [inv for inv in invocations if inv["stage"] == stage]
            durations = sorted(inv["duration_s"] for inv in rows if inv["duration_s"] is not None)
            stages[stage] = {
                "statuses": dict(Counter(inv["status"] for inv in rows)),
                "errors": dict(Counter(inv["error_type"] for inv in rows if inv["error_type"])),
                "duration_median_s": round(statistics.median(durations), 3) if durations else None,
                "duration_max_s": max(durations) if durations else None,
                "input_tokens": sum(inv["token_usage"].get("input_tokens", 0) for inv in rows),
                "cached_tokens": sum(
                    inv["token_usage"].get("input_tokens_details", {}).get("cached_tokens", 0)
                    for inv in rows
                ),
                "cache_write_tokens": sum(
                    inv["token_usage"].get("input_tokens_details", {}).get("cache_write_tokens", 0)
                    for inv in rows
                ),
                "output_tokens": sum(inv["token_usage"].get("output_tokens", 0) for inv in rows),
                "reasoning_tokens": sum(
                    inv["token_usage"].get("output_tokens_details", {}).get("reasoning_tokens", 0)
                    for inv in rows
                ),
                "missing_usage_count": sum(not inv["token_usage"] for inv in rows),
            }
        unplanned = candidates.filter(status="READY", canonicalization_plan__isnull=True).order_by(
            "created_at", "pk"
        )
        first = unplanned.first()
        first_details = None
        if first:
            first_details = {
                "id": first.pk,
                "title": first.title,
                "created_at": first.created_at,
                "matches": list(
                    CandidateMatch.objects.filter(event_candidate=first).values(
                        "event_id", "event__title", "score"
                    )
                ),
                "attempts": [
                    inv
                    for inv in invocations
                    if inv["stage"] == "CANONICALIZATION" and inv["batch_index"] == first.pk
                ],
            }
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pid,state,wait_event_type,wait_event,pg_blocking_pids(pid),left(query,100) "
                "FROM pg_stat_activity WHERE datname=current_database() "
                "AND pid<>pg_backend_pid()"
            )
            sessions = cursor.fetchall()
        result = {
            "timestamp": now,
            "request_id": args.request_id,
            "jobs": list(
                jobs.values(
                    "id",
                    "source_id",
                    "status",
                    "claimed_at",
                    "completed_at",
                    "heartbeat_at",
                    "items_discovered",
                    "items_screened",
                    "items_relevant",
                    "items_extracted",
                    "candidates_created",
                    "failures_count",
                    "error_type",
                    "error_message",
                )
            ),
            "candidate_statuses": {
                r["status"]: r["count"]
                for r in candidates.values("status").annotate(count=Count("pk"))
            },
            "plan_statuses": {
                r["status"]: r["count"] for r in plans.values("status").annotate(count=Count("pk"))
            },
            "event_count": Event.objects.count(),
            "unplanned_ready_count": unplanned.count(),
            "oldest_unplanned": first_details,
            "stages": stages,
            "latest_canonical": [inv for inv in invocations if inv["stage"] == "CANONICALIZATION"][
                -3:
            ],
            "database_sessions": sessions,
        }
        if args.details:
            result["canonical_attempts"] = [
                {
                    k: inv[k]
                    for k in (
                        "id",
                        "batch_index",
                        "attempt_number",
                        "status",
                        "duration_s",
                        "error_type",
                        "started_at",
                        "completed_at",
                    )
                }
                for inv in invocations
                if inv["stage"] == "CANONICALIZATION"
            ]
            result["failure_categories"] = dict(
                Counter(
                    inv["stage"]
                    + ": "
                    + (
                        "invalid time offset"
                        if "wall-clock" in inv["error_message"]
                        else "incomplete response"
                        if "incomplete" in inv["error_message"]
                        else "refused or unparsed output"
                        if "no " in inv["error_message"].lower()
                        and inv["error_type"] == "ModelOutputError"
                        else inv["error_type"]
                    )
                    for inv in invocations
                    if inv["status"] == "FAILED"
                )
            )
            result["failure_samples"] = [
                {
                    k: inv[k]
                    for k in (
                        "id",
                        "job_id",
                        "stage",
                        "batch_index",
                        "attempt_number",
                        "duration_s",
                        "error_type",
                    )
                }
                | {"error": inv["error_message"][:650]}
                for inv in invocations
                if inv["status"] == "FAILED"
            ][:8]
            result["blocked_candidates"] = list(
                candidates.filter(status="BLOCKED").values("id", "title", "validation_issues")
            )
            result["problem_plans"] = list(
                plans.exclude(status="APPLIED").values(
                    "event_candidate_id",
                    "status",
                    "action",
                    "application_error",
                    "validation_issues",
                    "grounding_flags",
                    "domain_flags",
                )
            )
        print(json.dumps(result, default=str, ensure_ascii=False))


if __name__ == "__main__":
    main()
