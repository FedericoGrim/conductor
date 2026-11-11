import asyncio
import json
import subprocess
from pathlib import Path

from conductor.worker import (
    build_command,
    commit_work,
    create_worktree,
    diff_against,
    exclude_from_git,
    parse_events,
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


def test_subprocess_runner_sets_pwd_to_the_working_directory(tmp_path: Path) -> None:
    code, stdout, _ = asyncio.run(subprocess_runner(["sh", "-c", "echo $PWD"], tmp_path))
    assert code == 0
    assert stdout.strip() == str(tmp_path)


def test_exclude_from_git_adds_pattern_once(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    exclude_from_git(repo, ".conductor/")
    exclude_from_git(repo, ".conductor/")
    assert (repo / ".git" / "info" / "exclude").read_text().count(".conductor/") == 1


def test_run_attempt_uses_injected_runner(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    worktree = tmp_path / "wt"
    create_worktree(repo, worktree, branch="conductor/s1-1", base="main")
    seen: dict[str, object] = {}

    async def fake_runner(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
        seen["cmd"] = cmd
        seen["cwd"] = cwd
        (cwd / "made.txt").write_text("by model\n")
        return 0, json.dumps({"type": "text", "sessionID": "ses_9"}) + "\n", ""

    output = asyncio.run(
        run_attempt(
            worktree,
            base="main",
            model="openrouter/a/b",
            prompt="do it",
            extra_args=[],
            commit_message="conductor: s1 attempt 1",
            runner=fake_runner,
        )
    )
    assert seen["cwd"] == worktree
    assert output.exit_code == 0
    assert output.session_id == "ses_9"
    assert "+by model" in output.diff
