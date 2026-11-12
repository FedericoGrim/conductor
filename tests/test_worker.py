import asyncio
import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from conductor.errors import TRANSIENT
from conductor.worker import (
    build_command,
    commit_work,
    create_worktree,
    diff_against,
    events_cost,
    exclude_from_git,
    final_text,
    parse_events,
    retry_limit,
    run_attempt,
    subprocess_runner,
    write_opencode_config,
)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "README.md").write_text("hi\n")
    git(repo, "add", ".")
    git(repo, "commit", "-q", "-m", "init")
    return repo


def test_build_command_targets_model_and_json_output() -> None:
    cmd = build_command("openrouter/x/y", "write code", extra_args=["--variant", "high"])
    assert cmd[:2] == ["opencode", "run"]
    assert cmd[-1] == "write code"
    for flag in ("--format", "json", "-m", "openrouter/x/y", "--auto", "--archived"):
        assert flag in cmd
    assert cmd.index("--variant") < cmd.index("write code")


def test_parse_events_keeps_json_lines_and_session_id() -> None:
    raw = "\n".join(
        [
            json.dumps({"type": "step-start", "sessionID": "ses_1", "timestamp": 1}),
            "not json at all",
            json.dumps({"type": "text", "sessionID": "ses_1", "text": "done"}),
        ]
    )
    events, session_id = parse_events(raw)
    assert [e["type"] for e in events] == ["step-start", "text"]
    assert session_id == "ses_1"


def test_worktree_config_commit_and_diff(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    worktree = tmp_path / "wt"
    create_worktree(repo, worktree, branch="conductor/s1-1", base="main")
    write_opencode_config(worktree, {"provider": {}})
    (worktree / "new.py").write_text("x = 1\n")
    commit_work(worktree, "conductor: step s1 attempt 1")
    diff = diff_against(worktree, "main")
    assert "+x = 1" in diff
    assert "opencode.json" not in diff
    assert "opencode.json" in (repo / ".git" / "info" / "exclude").read_text()


def never_stop(line: str) -> bool:
    return False


def test_subprocess_runner_sets_pwd_to_the_working_directory(tmp_path: Path) -> None:
    code, stdout, _ = asyncio.run(
        subprocess_runner(["sh", "-c", "echo $PWD"], tmp_path, never_stop)
    )
    assert code == 0
    assert stdout.strip() == str(tmp_path)


def test_subprocess_runner_stops_the_process_when_asked(tmp_path: Path) -> None:
    endless = "while true; do echo line; sleep 0.01; done"
    seen: list[str] = []

    def stop_on_third(line: str) -> bool:
        seen.append(line)
        return len(seen) == 3

    code, stdout, _ = asyncio.run(
        asyncio.wait_for(subprocess_runner(["sh", "-c", endless], tmp_path, stop_on_third), 10)
    )
    assert code != 0
    assert stdout.splitlines()[:3] == ["line", "line", "line"]


def test_subprocess_runner_keeps_stderr(tmp_path: Path) -> None:
    code, _, stderr = asyncio.run(
        subprocess_runner(["sh", "-c", "echo oops >&2; exit 3"], tmp_path, never_stop)
    )
    assert code == 3
    assert stderr.strip() == "oops"


def retry_line(kind: str = "provider.rate-limit") -> str:
    return json.dumps({"type": "retry", "error": {"type": kind, "message": "slow down"}})


def test_retry_limit_stops_after_more_retries_than_allowed() -> None:
    should_stop = retry_limit(2)
    decisions = [should_stop(line) for line in ['{"type":"text"}', retry_line(), retry_line()]]
    assert decisions == [False, False, False]
    assert should_stop(retry_line()) is True


def test_retry_limit_ignores_lines_that_are_not_json() -> None:
    should_stop = retry_limit(0)
    assert should_stop("retry") is False
    assert should_stop(retry_line()) is True


def test_exclude_from_git_adds_pattern_once(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    exclude_from_git(repo, ".conductor/")
    exclude_from_git(repo, ".conductor/")
    assert (repo / ".git" / "info" / "exclude").read_text().count(".conductor/") == 1


def step_finish(cost: object) -> dict[str, Any]:
    return {"type": "step_finish", "sessionID": "ses_1", "part": {"cost": cost}}


def test_events_cost_sums_the_cost_of_every_finished_step() -> None:
    events = [
        {"type": "step_start", "sessionID": "ses_1", "part": {}},
        step_finish(0.0125),
        {"type": "text", "sessionID": "ses_1", "part": {"text": "done"}},
        step_finish(0.004),
    ]
    assert events_cost(events) == pytest.approx(0.0165)


def test_events_cost_ignores_events_without_a_numeric_cost() -> None:
    events = [step_finish(None), step_finish("free"), {"type": "step_finish"}, step_finish(0.5)]
    assert events_cost(events) == 0.5


def test_run_attempt_uses_injected_runner(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    worktree = tmp_path / "wt"
    create_worktree(repo, worktree, branch="conductor/s1-1", base="main")
    seen: dict[str, object] = {}

    async def fake_runner(
        cmd: list[str], cwd: Path, should_stop: Callable[[str], bool]
    ) -> tuple[int, str, str]:
        seen["cmd"] = cmd
        seen["cwd"] = cwd
        (cwd / "made.txt").write_text("by model\n")
        events = [{"type": "text", "sessionID": "ses_9"}, step_finish(0.02)]
        return 0, "".join(json.dumps(event) + "\n" for event in events), ""

    output = asyncio.run(
        run_attempt(
            worktree,
            base="main",
            model="openrouter/a/b",
            prompt="do it",
            extra_args=[],
            commit_message="conductor: s1 attempt 1",
            transient_attempts=3,
            runner=fake_runner,
        )
    )
    assert seen["cwd"] == worktree
    assert output.exit_code == 0
    assert output.session_id == "ses_9"
    assert output.cost == 0.02
    assert output.error is None
    assert output.final_text == ""
    assert "+by model" in output.diff


def test_run_attempt_stops_after_the_retry_limit_and_reports_a_transient_error(
    tmp_path: Path,
) -> None:
    repo = init_repo(tmp_path)
    worktree = tmp_path / "wt"
    create_worktree(repo, worktree, branch="conductor/s1-1", base="main")

    async def retrying_runner(
        cmd: list[str], cwd: Path, should_stop: Callable[[str], bool]
    ) -> tuple[int, str, str]:
        lines: list[str] = []
        while True:
            line = retry_line("provider.internal")
            lines.append(line)
            if should_stop(line):
                return -15, "\n".join(lines) + "\n", ""

    output = asyncio.run(
        run_attempt(
            worktree,
            base="main",
            model="openrouter/a/b",
            prompt="do it",
            extra_args=[],
            commit_message="conductor: s1 attempt 1",
            transient_attempts=2,
            runner=retrying_runner,
        )
    )
    assert len(output.events) == 3
    assert output.error is not None
    assert output.error.kind == TRANSIENT
    assert output.error.type == "provider.internal"


def text_event(text: str) -> dict[str, Any]:
    return {"type": "text", "sessionID": "ses", "part": {"type": "text", "text": text}}


def test_final_text_is_the_last_text_part() -> None:
    events = [text_event("first"), step_finish(0.1), text_event("last"), step_finish(0.1)]
    assert final_text(events) == "last"


def test_final_text_is_empty_without_text_parts() -> None:
    assert final_text([step_finish(0.1), {"type": "text", "part": "broken"}]) == ""
