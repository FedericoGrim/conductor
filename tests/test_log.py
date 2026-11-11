import json
from pathlib import Path

import pytest

from conductor.log import RunLog
from conductor.plan import Plan, Step
from conductor.scheduler import StepResult

PLAN = Plan("goal", (Step("s1", "S1", "do", ("a.py",), 1, ()),))


def test_run_log_writes_run_and_attempt_files(tmp_path: Path) -> None:
    log = RunLog.create(tmp_path, PLAN, privacy="medium")
    log.attempt(PLAN.steps[0], {"attempt": 1, "model": "m", "diff": "+x"})
    log.attempt(PLAN.steps[0], {"attempt": 2, "model": "n", "diff": "+y"})
    log.finish({"s1": StepResult("s1", "approved", "fine", attempts=[{"attempt": 1}])})

    run = json.loads((log.directory / "run.json").read_text())
    assert run["privacy"] == "medium"
    assert run["plan"]["goal"] == "goal"
    assert run["steps"]["s1"]["status"] == "approved"
    assert run["steps"]["s1"]["attempts"] == 1
    assert run["steps"]["s1"]["last_attempt"] == "step-s1/attempt-1.json"
    assert run["finished_at"]

    second = json.loads((log.directory / "step-s1" / "attempt-2.json").read_text())
    assert second["model"] == "n"
    assert second["step"] == {"id": "s1", "title": "S1"}


def test_finish_totals_the_cost_per_step_per_model_and_for_the_run(tmp_path: Path) -> None:
    log = RunLog.create(tmp_path, PLAN, privacy="medium")
    attempts = [
        {
            "attempt": 1,
            "model": "openrouter/cheap",
            "review": {"model": "openrouter/judge"},
            "cost": {"worker": 0.01, "reviewer": 0.002},
        },
        {
            "attempt": 2,
            "model": "openrouter/strong",
            "review": {"model": "openrouter/judge"},
            "cost": {"worker": 0.3, "reviewer": None},
        },
        {"attempt": 3, "model": "openrouter/strong", "review": None},
    ]
    log.finish({"s1": StepResult("s1", "approved", "fine", attempts=attempts)})

    run = json.loads((log.directory / "run.json").read_text())
    assert run["steps"]["s1"]["cost"] == pytest.approx(0.312)
    assert run["cost"] == pytest.approx(0.312)
    assert run["cost_by_model"] == {
        "openrouter/cheap": pytest.approx(0.01),
        "openrouter/strong": pytest.approx(0.3),
        "openrouter/judge": pytest.approx(0.002),
    }


def test_each_run_gets_its_own_directory(tmp_path: Path) -> None:
    first = RunLog.create(tmp_path, PLAN, privacy="low")
    second = RunLog.create(tmp_path, PLAN, privacy="low")
    assert first.directory != second.directory
    assert first.directory.parent == tmp_path / ".conductor" / "runs"
