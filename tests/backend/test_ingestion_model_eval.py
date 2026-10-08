"""Offline regression coverage for evaluation costs and grading boundaries."""

import importlib.util
import sys
from pathlib import Path

import pytest

SUPPORT_PATH = Path(__file__).resolve().parents[2] / "scripts/ingestion_model_eval.py"
spec = importlib.util.spec_from_file_location("ingestion_model_eval", SUPPORT_PATH)
evaluation = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = evaluation
spec.loader.exec_module(evaluation)


def test_cost_distinguishes_reads_writes_and_counts_reasoning_once():
    usage = {
        "input_tokens": 1000,
        "output_tokens": 200,
        "input_tokens_details": {"cached_tokens": 600, "cache_write_tokens": 100},
        "output_tokens_details": {"reasoning_tokens": 100},
    }
    assert evaluation.cost("gpt-6-luna", usage) == pytest.approx(0.0001485)


@pytest.mark.parametrize(
    "usage",
    [
        {},
        {"input_tokens": 1},
        {"input_tokens": 1, "output_tokens": 1, "input_tokens_details": {"cached_tokens": 2}},
        {"input_tokens": -1, "output_tokens": 0},
    ],
)
def test_unknown_or_invalid_usage_is_not_free(usage):
    with pytest.raises(ValueError):
        evaluation.cost("gpt-6-luna", usage)


def test_long_context_pricing_applies_to_entire_request():
    assert evaluation.cost(
        "gpt-5.6-luna", {"input_tokens": 300000, "output_tokens": 1000}
    ) == pytest.approx(0.1218)


def test_ceiling_assumes_all_inputs_are_cache_writes():
    assert evaluation.request_ceiling("gpt-6-luna", 1000, 200) == pytest.approx(0.000225)


def test_budget_reserves_all_http_attempts():
    budget = evaluation.Budget(0.02)
    with pytest.raises(evaluation.BudgetExceeded):
        budget.reserve(0.01, attempts=3)
    assert budget.pending == 0


def test_unknown_bill_keeps_full_reservation():
    budget = evaluation.Budget(1)
    budget.reserve(0.01)
    budget.settle(None)
    assert budget.known_spend == 0
    assert budget.upper_spend == pytest.approx(0.03)


def test_known_response_plus_hidden_retry_stays_in_upper_bound():
    budget = evaluation.Budget(1)
    budget.reserve(0.01)
    budget.settle(0.002, unknown_upper=0.01)
    assert budget.known_spend == 0.002
    assert budget.upper_spend == pytest.approx(0.012)


@pytest.mark.parametrize("limit", [0, -1, float("nan"), float("inf")])
def test_budget_requires_finite_positive_limit(limit):
    with pytest.raises(ValueError):
        evaluation.Budget(limit)


def test_budget_refuses_concurrent_reservation():
    budget = evaluation.Budget(1)
    budget.reserve(0.01)
    with pytest.raises(RuntimeError):
        budget.reserve(0.01)


def test_budget_refuses_cost_above_reserved_ceiling():
    budget = evaluation.Budget(1)
    budget.reserve(0.01)
    with pytest.raises(ValueError):
        budget.settle(0.04)
    assert budget.pending == pytest.approx(0.03)


def test_object_checks_keep_fields_on_same_occurrence():
    root = [
        {
            "occurrences": [
                {"start_date": "2026-10-11", "start_time": "04:00:00"},
                {"start_date": "2026-10-12", "start_time": "18:00:00"},
            ]
        }
    ]
    assert evaluation.check(
        root,
        {
            "path": "occurrences",
            "op": "object_contains",
            "value": {"start_date": "2026-10-11", "start_time": "04:00:00"},
        },
    )
    assert not evaluation.check(
        root,
        {
            "path": "occurrences",
            "op": "object_contains",
            "value": {"start_date": "2026-10-11", "start_time": "18:00:00"},
        },
    )


def test_period_checks_allow_equivalent_daily_occurrences():
    root = [
        {
            "occurrences": [
                {"start_date": "2024-03-04"},
                {"start_date": "2024-03-08", "end_date": "2024-03-08"},
            ]
        }
    ]
    assert evaluation.check(
        root,
        {
            "path": "occurrences",
            "op": "period_bounds",
            "value": {"start_date": "2024-03-04", "end_date": "2024-03-08"},
        },
    )


def test_failed_response_does_not_pass_non_event_reference():
    score = evaluation.grade(
        {"stage": "extraction", "status": "FAILED", "events": []},
        {"status": "READY", "expected_event_count": 0, "checks": []},
    )
    assert not score["all_passed"]


def test_rejected_domain_plan_is_not_a_usable_result():
    score = evaluation.grade(
        {
            "stage": "canonicalization",
            "status": "SUCCEEDED",
            "plan_status": "REJECTED",
            "action": "UPDATE",
            "target_event_id": 1,
            "other_matches_preserved": True,
        },
        {"status": "READY", "allowed_actions": ["UPDATE"], "target_event_id": 1, "checks": []},
    )
    assert not score["available"]
    assert score["checks_passed"] == 0


def test_add_can_be_accepted_without_old_target_id():
    score = evaluation.grade(
        {
            "stage": "canonicalization",
            "status": "SUCCEEDED",
            "plan_status": "APPLIED",
            "action": "ADD",
            "target_event_id": None,
            "other_matches_preserved": True,
            "final_event": {},
        },
        {
            "status": "READY",
            "allowed_actions": ["ADD", "UPDATE"],
            "target_event_id": 10,
            "checks": [],
        },
    )
    assert score["all_passed"]


def test_grading_refuses_unreviewed_reference():
    with pytest.raises(ValueError):
        evaluation.grade({"stage": "extraction"}, {"status": "REVIEW"})


def test_summary_keeps_stages_configurations_and_strata_separate():
    ref = {"extraction": {"x": {"status": "READY", "expected_event_count": 0, "checks": []}}}
    rows = [
        {
            "stage": "extraction",
            "case_id": "x",
            "configuration": "luna6-low",
            "stratum": stratum,
            "status": "SUCCEEDED",
            "events": [],
        }
        for stratum in ("representative", "synthetic_edge")
    ]
    summary = evaluation.summarize(rows, ref)
    assert len(summary) == 2
    assert all(v["cases"] == 1 for v in summary.values())


def test_reference_loader_refuses_path_traversal(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"extraction_files":["../outside.json"],"canonicalization_files":[]}')
    with pytest.raises(ValueError, match="escaped"):
        evaluation.load_references(manifest)


def test_timing_reports_nearest_rank_p95():
    result = evaluation.timing([1, 2, 3, 4])
    assert result == {"count": 4, "median_s": 2.5, "p95_s": 4, "max_s": 4}


@pytest.mark.parametrize("attempts", [0, -1, 1.5, True])
def test_budget_requires_integer_attempt_count(attempts):
    with pytest.raises(ValueError):
        evaluation.Budget(1).reserve(0.01, attempts)


def test_action_specific_checks_preserve_existing_sessions_only_when_merging():
    reference = {
        "status": "READY",
        "allowed_actions": ["ADD", "UPDATE"],
        "target_event_id": 10,
        "checks": [
            {
                "path": "occurrences",
                "op": "object_contains",
                "value": {"start_date": "2026-08-05"},
                "when_action": "UPDATE",
            }
        ],
    }
    base = {
        "stage": "canonicalization",
        "status": "SUCCEEDED",
        "plan_status": "APPLIED",
        "other_matches_preserved": True,
        "final_event": {"occurrences": []},
    }
    assert evaluation.grade(base | {"action": "ADD", "target_event_id": None}, reference)[
        "all_passed"
    ]
    assert not evaluation.grade(base | {"action": "UPDATE", "target_event_id": 10}, reference)[
        "all_passed"
    ]
