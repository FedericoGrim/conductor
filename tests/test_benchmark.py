from __future__ import annotations

import importlib.util
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "benchmark.py"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("benchmark", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


benchmark = load_script()


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )
    return result.stdout


def commit(repo: Path, message: str) -> str:
    git(repo, "commit", "--allow-empty", "-m", message)
    return git(repo, "rev-parse", "HEAD").strip()


def make_repo(path: Path) -> str:
    path.mkdir(parents=True)
    git(path, "init", "-b", "main")
    git(path, "config", "user.name", "test")
    git(path, "config", "user.email", "test@example.com")
    (path / ".gitignore").write_text(".venv/\n")
    git(path, "add", "-A")
    return commit(path, "first")


def write_task(
    directory: Path,
    task_id: str = "tiny",
    hidden: str = "tests/test_hidden.py",
) -> Any:
    directory.mkdir(parents=True, exist_ok=True)
    body = {
        "id": task_id,
        "title": "A tiny task",
        "difficulty": 3,
        "base": "aaaaaaa",
        "solution": "bbbbbbb",
        "hidden_tests": [hidden],
        "files": ["conductor/thing.py", "tests/test_thing.py"],
        "spec": "Make the thing.",
    }
    (directory / f"{task_id}.json").write_text(json.dumps(body))
    return benchmark.Task(
        id=task_id,
        title="A tiny task",
        difficulty=3,
        base="aaaaaaa",
        solution="bbbbbbb",
        hidden_tests=(hidden,),
        files=("conductor/thing.py", "tests/test_thing.py"),
        spec="Make the thing.",
    )


def stub_pre_commit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Put a fake `pre-commit` executable on PATH that records its arguments."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    log = bin_dir / "pre-commit.log"
    exe = bin_dir / "pre-commit"
    exe.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$@\" > {log}\nexit 0\n")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    return log


def test_load_tasks_reads_the_files_and_sorts_by_id(tmp_path: Path) -> None:
    first = write_task(tmp_path, task_id="zzz")
    second = write_task(tmp_path, task_id="aaa")
    loaded = benchmark.load_tasks(tmp_path, None)
    assert [task.id for task in loaded] == [second.id, first.id]
    assert loaded[0].spec == "Make the thing."
    assert loaded[0].hidden_tests == ("tests/test_hidden.py",)
    chosen = benchmark.load_tasks(tmp_path, ["aaa"])
    assert [task.id for task in chosen] == ["aaa"]


def test_load_tasks_rejects_an_unknown_id(tmp_path: Path) -> None:
    write_task(tmp_path)
    with pytest.raises(benchmark.BenchmarkError, match="nope"):
        benchmark.load_tasks(tmp_path, ["nope"])


def test_load_tasks_rejects_a_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(benchmark.BenchmarkError, match="tasks directory"):
        benchmark.load_tasks(tmp_path / "missing", None)


def test_plan_for_builds_a_single_difficulty_5_step(tmp_path: Path) -> None:
    task = write_task(tmp_path)
    plan = benchmark.plan_for(task)
    assert plan["goal"] == task.title
    (step,) = plan["steps"]
    assert step["id"] == task.id
    assert step["title"] == task.title
    assert step["spec"] == task.spec
    assert step["files"] == list(task.files)
    assert step["difficulty"] == 5
    assert step["depends_on"] == []
    assert plan["verify"] == [
        "$CONDUCTOR_REPO/.venv/bin/python -m pytest -q",
        "$CONDUCTOR_REPO/.venv/bin/ruff check conductor tests",
        "$CONDUCTOR_REPO/.venv/bin/mypy --strict conductor tests",
    ]
    assert task.hidden_tests[0] not in json.dumps(plan)


def test_prepare_copy_extracts_the_base_commit_as_one_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = stub_pre_commit(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    base = make_repo(repo)
    (repo / "second.txt").write_text("second\n")
    git(repo, "add", "-A")
    commit(repo, "second")
    (repo / ".venv").mkdir()
    task = benchmark.Task(
        id="tiny",
        title="A tiny task",
        difficulty=3,
        base=base,
        solution=base,
        hidden_tests=("tests/test_hidden.py",),
        files=("conductor/thing.py",),
        spec="Make the thing.",
    )
    destination = tmp_path / "copy"
    benchmark.prepare_copy(repo, task, destination)
    assert (destination / ".gitignore").read_text() == ".venv/\n"
    assert not (destination / "second.txt").exists()
    assert git(destination, "rev-list", "--count", "HEAD").strip() == "1"
    assert "chore: benchmark base" in git(destination, "log", "-1", "--format=%s")
    assert git(destination, "remote").strip() == ""
    assert (destination / ".venv").is_symlink()
    assert git(destination, "status", "--porcelain").strip() == ""
    installed = log.read_text().splitlines()
    assert "install" in installed
    assert "--hook-type" in installed
    assert "pre-commit" in installed and "commit-msg" in installed


def test_prepare_copy_requires_pre_commit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(benchmark.shutil, "which", lambda _: None, raising=False)
    repo = tmp_path / "repo"
    base = make_repo(repo)
    task = benchmark.Task(
        id="tiny",
        title="A tiny task",
        difficulty=3,
        base=base,
        solution=base,
        hidden_tests=(),
        files=(),
        spec="Make the thing.",
    )
    with pytest.raises(benchmark.BenchmarkError, match="pre-commit"):
        benchmark.prepare_copy(repo, task, tmp_path / "copy")


def test_attempt_commit_points_at_the_merged_head(tmp_path: Path) -> None:
    copy = tmp_path / "copy"
    head = make_repo(copy)
    run_dir = tmp_path / "2026-01-01T00-00-00"
    assert benchmark.attempt_commit(copy, run_dir, "tiny", "approved", 2) == head


def test_attempt_commit_returns_the_kept_branch_when_it_exists(tmp_path: Path) -> None:
    copy = tmp_path / "copy"
    make_repo(copy)
    run_dir = tmp_path / "2026-01-01T00-00-00"
    branch = f"conductor/{run_dir.name}/tiny-2"
    git(copy, "branch", branch)
    assert benchmark.attempt_commit(copy, run_dir, "tiny", "failed", 2) == branch


def test_attempt_commit_returns_none_without_work(tmp_path: Path) -> None:
    copy = tmp_path / "copy"
    make_repo(copy)
    run_dir = tmp_path / "2026-01-01T00-00-00"
    assert benchmark.attempt_commit(copy, run_dir, "tiny", "failed", 2) is None
    assert benchmark.attempt_commit(copy, run_dir, "tiny", "failed", 3) is None


PASSING = "def test_hidden():\n    assert True\n"
FAILING = "def test_hidden():\n    assert False, 'the worker did not solve it'\n"


def solution_repo(tmp_path: Path, test_body: str) -> tuple[Path, Path, Any]:
    repo = tmp_path / "repo"
    base = make_repo(repo)
    (repo / "tests").mkdir()
    (repo / "tests" / "test_hidden.py").write_text(test_body)
    git(repo, "add", "-A")
    solution = commit(repo, "solution")
    (repo / ".venv" / "bin").mkdir(parents=True)
    (repo / ".venv" / "bin" / "python").write_text(f'#!/bin/sh\nexec {sys.executable} "$@"\n')
    (repo / ".venv" / "bin" / "python").chmod(
        (repo / ".venv" / "bin" / "python").stat().st_mode | stat.S_IEXEC
    )
    copy = tmp_path / "copy"
    make_repo(copy)
    task = benchmark.Task(
        id="tiny",
        title="A tiny task",
        difficulty=3,
        base=base,
        solution=solution,
        hidden_tests=("tests/test_hidden.py",),
        files=("tests/test_hidden.py",),
        spec="Make the thing.",
    )
    return repo, copy, task


def test_check_hidden_runs_the_solution_tests_and_passes(tmp_path: Path) -> None:
    repo, copy, task = solution_repo(tmp_path, PASSING)
    workdir = tmp_path / "check"
    assert benchmark.check_hidden(repo, copy, "HEAD", task, workdir) is True
    assert workdir.exists() is False
    assert git(copy, "worktree", "list", "--porcelain").count("worktree") == 1


def test_check_hidden_fails_when_the_tests_fail(tmp_path: Path) -> None:
    repo, copy, task = solution_repo(tmp_path, FAILING)
    workdir = tmp_path / "check"
    assert benchmark.check_hidden(repo, copy, "HEAD", task, workdir) is False
    assert workdir.exists() is False
    assert git(copy, "worktree", "list", "--porcelain").count("worktree") == 1


def test_classify_covers_solved_rejections_and_no_work() -> None:
    assert benchmark.classify("approved", True, True) == {
        "solved": True,
        "false_rejection": False,
        "false_approval": False,
    }
    assert benchmark.classify("failed", False, True) == {
        "solved": False,
        "false_rejection": True,
        "false_approval": False,
    }
    assert benchmark.classify("approved", True, False) == {
        "solved": False,
        "false_rejection": False,
        "false_approval": True,
    }
    assert benchmark.classify("failed", None, None) == {
        "solved": False,
        "false_rejection": False,
        "false_approval": False,
    }


def write_run(
    tmp_path: Path,
    *,
    status: str = "approved",
    attempts: int = 2,
    review: dict[str, object] | None = None,
) -> Path:
    run_dir = tmp_path / "2026-01-01T00-00-00"
    (run_dir / "step-tiny").mkdir(parents=True)
    (run_dir / "run.json").write_text(
        json.dumps(
            {
                "started_at": "2026-01-01T00:00:00+00:00",
                "finished_at": "2026-01-01T00:10:00+00:00",
                "cost": 0.5,
                "steps": {"tiny": {"status": status, "attempts": attempts}},
            }
        )
    )
    (run_dir / "step-tiny" / f"attempt-{attempts}.json").write_text(json.dumps({"review": review}))
    return run_dir


def test_job_result_reads_the_run_and_the_last_attempt(tmp_path: Path) -> None:
    task = write_task(tmp_path)
    run_dir = write_run(
        tmp_path,
        review={"ok": True, "category": None, "suspicious": False},
    )
    record = benchmark.job_result("bench-a", "prov/model", task, 1, run_dir, True)
    assert record == {
        "profile": "bench-a",
        "model": "prov/model",
        "task": "tiny",
        "difficulty": 3,
        "repetition": 1,
        "status": "approved",
        "attempts": 2,
        "cost": 0.5,
        "seconds": 600.0,
        "review": {"ok": True, "category": None, "suspicious": False},
        "hidden_ok": True,
        "solved": True,
        "false_rejection": False,
        "false_approval": False,
    }


def test_job_result_without_a_run_reports_no_run(tmp_path: Path) -> None:
    task = write_task(tmp_path)
    run_dir = write_run(tmp_path, status="failed", review=None)
    (run_dir / "run.json").unlink()
    record = benchmark.job_result("bench-a", "prov/model", task, 1, run_dir, None)
    assert record["status"] == "no-run"
    assert record["attempts"] == 0
    assert record["cost"] == 0.0
    assert record["seconds"] is None
    assert record["review"] is None
    assert record["hidden_ok"] is None
    assert record["solved"] is False


def test_job_result_marks_a_suspicious_rejection(tmp_path: Path) -> None:
    task = write_task(tmp_path)
    run_dir = write_run(
        tmp_path,
        status="failed",
        review={"ok": False, "category": "spec", "suspicious": True},
    )
    record = benchmark.job_result("bench-a", "prov/model", task, 1, run_dir, True)
    assert record["false_rejection"] is True
    assert record["solved"] is False


def test_job_result_marks_a_false_approval(tmp_path: Path) -> None:
    task = write_task(tmp_path)
    run_dir = write_run(tmp_path, review={"ok": True, "category": None, "suspicious": False})
    record = benchmark.job_result("bench-a", "prov/model", task, 1, run_dir, False)
    assert record["false_approval"] is True
    assert record["solved"] is False


def job_record(**overrides: Any) -> dict[str, Any]:
    """A hand-made record like the ones job_result writes."""
    body: dict[str, Any] = {
        "profile": "bench-a",
        "model": "prov/a",
        "task": "tiny",
        "difficulty": 3,
        "repetition": 1,
        "status": "approved",
        "attempts": 1,
        "cost": 0.1,
        "seconds": 60.0,
        "review": {"ok": True, "category": None, "suspicious": False},
        "hidden_ok": True,
        "solved": True,
        "false_rejection": False,
        "false_approval": False,
    }
    body.update(overrides)
    return body


def unsolved(**overrides: Any) -> dict[str, Any]:
    return job_record(
        status="failed",
        review=None,
        hidden_ok=None,
        solved=False,
        false_rejection=False,
        false_approval=False,
        **overrides,
    )


def test_report_sorts_by_solved_then_cost() -> None:
    records = [
        unsolved(model="prov/dear", profile="p1", cost=0.5),
        job_record(model="prov/cheap", profile="p2", cost=0.2),
        unsolved(model="prov/mid", profile="p3", cost=0.1),
        job_record(model="prov/cheap", profile="p2", cost=0.3, repetition=2),
        unsolved(model="prov/mid", profile="p3", cost=0.1, repetition=2),
    ]
    lines = benchmark.report(records).splitlines()
    assert lines[0] == (
        "| Model | Solved | D3 | Cost | $/solved | Mean time"
        " | Rejections | False rej. | False appr. | Suspicious |"
    )
    assert lines[1].startswith("|---|")
    assert "| prov/cheap | 2/2 | 2/2 | 0.5000 | 0.2500 | 60.0 | 0 | 0 | 0 | 0 |" in lines
    assert "| prov/mid | 0/2 | 0/2 | 0.2000 | - | 60.0 | 0 | 0 | 0 | 0 |" in lines
    assert "| prov/dear | 0/1 | 0/1 | 0.5000 | - | 60.0 | 0 | 0 | 0 | 0 |" in lines
    models = [line.split("|")[1].strip() for line in lines if line.startswith("| prov/")]
    assert models == ["prov/cheap", "prov/mid", "prov/dear"]
    assert lines[-1] == "Total: 5 jobs, $1.2000, 3 errors"


def test_report_per_difficulty_cells() -> None:
    records = [
        job_record(task="easy", difficulty=2),
        job_record(task="hard", difficulty=4, repetition=2),
        unsolved(task="hard", difficulty=4, repetition=3),
    ]
    lines = benchmark.report(records).splitlines()
    assert lines[0] == (
        "| Model | Solved | D2 | D4 | Cost | $/solved | Mean time"
        " | Rejections | False rej. | False appr. | Suspicious |"
    )
    assert "| prov/a | 2/3 | 1/1 | 1/2 | 0.3000 | 0.1500 | 60.0 | 0 | 0 | 0 | 0 |" in lines


def test_report_dollar_per_solved_needs_a_solve() -> None:
    lines = benchmark.report([job_record(cost=0.4)]).splitlines()
    assert "| prov/a | 1/1 | 1/1 | 0.4000 | 0.4000 | 60.0 | 0 | 0 | 0 | 0 |" in lines
    lines = benchmark.report([unsolved(cost=0.4)]).splitlines()
    assert "| prov/a | 0/1 | 0/1 | 0.4000 | - | 60.0 | 0 | 0 | 0 | 0 |" in lines


def test_report_counts_rejections_false_verdicts_and_suspicious() -> None:
    records = [
        job_record(),
        job_record(
            repetition=2,
            status="failed",
            review={"ok": False, "category": "tests", "suspicious": False},
            hidden_ok=True,
            solved=False,
            false_rejection=True,
        ),
        job_record(
            repetition=3,
            status="failed",
            review={"ok": False, "category": "spec", "suspicious": True},
            hidden_ok=False,
            solved=False,
        ),
        job_record(repetition=4, hidden_ok=False, solved=False, false_approval=True),
    ]
    lines = benchmark.report(records).splitlines()
    assert "| prov/a | 1/4 | 1/4 | 0.4000 | 0.4000 | 60.0 | 2 | 1 | 1 | 1 |" in lines


def test_report_per_task_table() -> None:
    records = [
        job_record(task="easy", difficulty=2),
        unsolved(task="hard", difficulty=4, model="prov/b", profile="p2"),
        job_record(task="hard", difficulty=4, model="prov/b", profile="p2", repetition=2),
    ]
    lines = benchmark.report(records).splitlines()
    header = lines.index("| Task | Difficulty | prov/a | prov/b |")
    assert lines[header + 1].startswith("|---|")
    assert lines[header + 2] == "| easy | 2 | 1/1 | - |"
    assert lines[header + 3] == "| hard | 4 | - | 1/2 |"
    assert "| prov/a | 1/1 | 1/1 | - | 0.1000 | 0.1000 | 60.0 | 0 | 0 | 0 | 0 |" in lines
    assert "| prov/b | 1/2 | - | 1/2 | 0.2000 | 0.2000 | 60.0 | 0 | 0 | 0 | 0 |" in lines


def test_report_errors_line_counts_provider_failures() -> None:
    records = [
        job_record(),
        job_record(
            repetition=2,
            status="unavailable",
            review=None,
            hidden_ok=None,
            solved=False,
        ),
        job_record(
            repetition=3,
            status="no-run",
            review=None,
            hidden_ok=None,
            seconds=None,
            solved=False,
        ),
        unsolved(repetition=4),
        job_record(
            repetition=5,
            status="failed",
            review={"ok": False, "category": "tests", "suspicious": False},
            hidden_ok=None,
            solved=False,
        ),
    ]
    lines = benchmark.report(records).splitlines()
    assert lines[-1] == "Total: 5 jobs, $0.5000, 3 errors"


def test_report_subcommand_reads_results_jsonl(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    records = [
        job_record(),
        unsolved(model="prov/b", profile="p2"),
    ]
    path = tmp_path / "results.jsonl"
    path.write_text("".join(json.dumps(record) + "\n" for record in records))
    assert benchmark.main(["report", str(path)]) == 0
    assert capsys.readouterr().out == benchmark.report(records)
    (tmp_path / "run").mkdir()
    path.rename(tmp_path / "run" / "results.jsonl")
    assert benchmark.main(["report", str(tmp_path / "run")]) == 0
    assert capsys.readouterr().out == benchmark.report(records)


def test_report_subcommand_rejects_bad_results(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "results.jsonl").write_text("{not json}\n")
    assert benchmark.main(["report", str(tmp_path)]) == 2
    assert "not valid JSON" in capsys.readouterr().err
    assert benchmark.main(["report", str(tmp_path / "missing")]) == 2
    assert "error:" in capsys.readouterr().err
