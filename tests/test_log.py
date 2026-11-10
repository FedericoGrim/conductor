import json
from pathlib import Path

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


def test_each_run_gets_its_own_directory(tmp_path: Path) -> None:
    first = RunLog.create(tmp_path, PLAN, privacy="low")
    second = RunLog.create(tmp_path, PLAN, privacy="low")
    assert first.directory != second.directory
    assert first.directory.parent == tmp_path / ".conductor" / "runs"
