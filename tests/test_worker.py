import asyncio
import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from conductor.commits import choose_commit_message
from conductor.errors import TRANSIENT
from conductor.harness import (
    OPENCODE,
    build_command,
    events_cost,
    final_text,
    is_retry,
    session_id,
    write_opencode_config,
)
from conductor.worker import (
    commit_work,
    create_worktree,
    diff_against,
    exclude_from_git,
    parse_events,
    retry_limit,
    run_attempt,
    subprocess_runner,
)
from tests.factories import install_git_hook


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
    events = parse_events(raw)
    assert [e["type"] for e in events] == ["step-start", "text"]
    assert session_id(events) == "ses_1"


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
    should_stop = retry_limit(2, is_retry)
    decisions = [should_stop(line) for line in ['{"type":"text"}', retry_line(), retry_line()]]
    assert decisions == [False, False, False]
    assert should_stop(retry_line()) is True


def test_retry_limit_ignores_lines_that_are_not_json() -> None:
    should_stop = retry_limit(0, is_retry)
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
            commit_message=lambda final_text: "chore(conductor): apply step s1 attempt 1",
            transient_attempts=3,
            harness=OPENCODE,
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
            commit_message=lambda final_text: "chore(conductor): apply step s1 attempt 1",
            transient_attempts=2,
            harness=OPENCODE,
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


def test_commit_work_reports_the_output_of_a_hook_that_rejects_the_commit(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    install_git_hook(repo, "pre-commit", "echo 'lint failed: unused import'\nexit 1\n")
    (repo / "new.py").write_text("import os\n")

    rejection = commit_work(repo, "chore(conductor): apply step s1 attempt 1")

    assert rejection is not None and "lint failed: unused import" in rejection
    assert git(repo, "log", "--oneline").count("\n") == 1


def test_commit_work_retries_once_when_a_hook_fixes_the_files(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    fixer = (
        "if grep -q ' $' new.py; then\n"
        "  sed -i 's/ *$//' new.py; echo 'fixed whitespace'; exit 1\n"
        "fi\n"
    )
    install_git_hook(repo, "pre-commit", fixer)
    (repo / "new.py").write_text("x = 1   \n")

    assert commit_work(repo, "chore(conductor): apply step s1 attempt 1") is None
    assert git(repo, "show", "HEAD:new.py") == "x = 1\n"
    assert git(repo, "status", "--porcelain") == ""


def test_commit_work_without_changes_commits_nothing(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    assert commit_work(repo, "chore(conductor): apply step s1 attempt 1") is None
    assert git(repo, "log", "--oneline").count("\n") == 1


def test_run_attempt_reports_a_commit_rejected_by_a_hook(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    install_git_hook(repo, "pre-commit", "echo 'mypy: error'\nexit 1\n")
    worktree = tmp_path / "wt"
    create_worktree(repo, worktree, branch="conductor/s1-1", base="main")

    async def writing_runner(
        cmd: list[str], cwd: Path, should_stop: Callable[[str], bool]
    ) -> tuple[int, str, str]:
        (cwd / "made.py").write_text("x: int = 'a'\n")
        return 0, "", ""

    output = asyncio.run(
        run_attempt(
            worktree,
            base="main",
            model="openrouter/a/b",
            prompt="do it",
            extra_args=[],
            commit_message=lambda final_text: "chore(conductor): apply step s1 attempt 1",
            transient_attempts=3,
            harness=OPENCODE,
            runner=writing_runner,
        )
    )
    assert output.commit_rejection is not None and "mypy: error" in output.commit_rejection
    assert output.diff == ""


def test_run_attempt_commits_with_the_callables_message(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    worktree = tmp_path / "wt"
    create_worktree(repo, worktree, branch="conductor/s1-1", base="main")
    received: list[str] = []

    async def writing_runner(
        cmd: list[str], cwd: Path, should_stop: Callable[[str], bool]
    ) -> tuple[int, str, str]:
        (cwd / "made.txt").write_text("x = 1\n")
        events = [text_event("COMMIT: feat(parser): scan the input")]
        return 0, "".join(json.dumps(event) + "\n" for event in events), ""

    def message(final_text: str) -> str:
        received.append(final_text)
        return choose_commit_message("s1", 1, "openrouter/a/b", final_text)

    output = asyncio.run(
        run_attempt(
            worktree,
            base="main",
            model="openrouter/a/b",
            prompt="do it",
            extra_args=[],
            commit_message=message,
            transient_attempts=3,
            harness=OPENCODE,
            runner=writing_runner,
        )
    )
    assert received == ["COMMIT: feat(parser): scan the input"]
    assert output.commit_message == (
        "feat(parser): scan the input\n\n"
        "Written by a Conductor worker: step s1, attempt 1, on openrouter/a/b."
    )
    assert git(worktree, "log", "-1", "--format=%B").strip() == output.commit_message
