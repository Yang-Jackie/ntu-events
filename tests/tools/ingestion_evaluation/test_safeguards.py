from argparse import Namespace
from unittest.mock import Mock

import pytest
from ntu_events_evaluation import paired, paths, prepare, replay


def test_output_paths_stay_inside_the_run(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "REPOSITORY_ROOT", tmp_path)
    directory = paths.run_directory("var/evaluations/ingestion/example")
    assert directory == tmp_path / "var/evaluations/ingestion/example"
    for value in ("var/raw", "var/evaluations", "var/evaluations/../../outside"):
        with pytest.raises(ValueError):
            paths.run_directory(value)
    with pytest.raises(ValueError):
        paths.run_file(directory, "../policy.json")


def test_prepare_refuses_existing_artifacts_before_database_access(monkeypatch, tmp_path):
    (tmp_path / "reference_answers.json").write_text("{}")
    monkeypatch.setattr(prepare, "run_directory", lambda _: tmp_path)
    bootstrap = Mock()
    monkeypatch.setattr(prepare, "bootstrap_django", bootstrap)
    with pytest.raises(RuntimeError, match="empty run directory"):
        prepare.main(Namespace(run_dir="existing"))
    bootstrap.assert_not_called()


def test_replay_refuses_working_database_before_connecting(monkeypatch):
    bootstrap = Mock()
    monkeypatch.setattr(replay, "bootstrap_django", bootstrap)
    with pytest.raises(RuntimeError, match="disposable database"):
        replay.require_isolation("ntu_events")
    bootstrap.assert_not_called()


def test_replay_checks_actual_database_even_with_an_evaluation_name(monkeypatch):
    from django.db import connection

    cursor = Mock()
    cursor.fetchone.return_value = ("ntu_events",)
    context = Mock()
    context.__enter__ = Mock(return_value=cursor)
    context.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(connection, "cursor", lambda: context)
    monkeypatch.setattr(replay, "bootstrap_django", lambda: None)
    with pytest.raises(RuntimeError, match="Refusing evaluation writes"):
        replay.require_isolation("ntu_events_eval_example")
    cursor.execute.assert_called_once_with("SELECT current_database()")


def test_paired_comparison_rejects_different_case_sets():
    data = {
        "metadata": {"complete": True},
        "rows": [
            {
                "stage": "extraction",
                "configuration": config,
                "case_id": case,
                "grade": {"all_passed": True},
            }
            for config, case in (("a", "one"), ("b", "two"))
            for _ in range(2)
        ],
    }
    with pytest.raises(RuntimeError, match="same paired cases"):
        paired.compare(data)
