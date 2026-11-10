import json
import os
import stat
from pathlib import Path
from typing import Any

import pytest

from conductor import cli, reviewer
from conductor.worker import commit_work, git

FAKE_OPENCODE = """#!/bin/sh
printf '{"type":"text","sessionID":"ses_fake","text":"hello"}\\n'
echo "made by $(echo "$@" | grep -o 'openrouter/[^ ]*') pid $$" >> output.txt
"""

CONFIG = """
default_privacy = "medium"
[privacy.medium]
provider = "openrouter"
base_url = "https://example.invalid/v1"
api_key_env = "TEST_CLI_KEY"
max_parallel = 2
tiers = ["openrouter/cheap", "openrouter/strong"]
reviewer = "openrouter/judge"
"""


def init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "README.md").write_text("hi\n")
    commit_work(repo, "init")
    return repo


def install_fake_opencode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    script = bin_dir / "opencode"
    script.write_text(FAKE_OPENCODE)
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")


def test_validate_accepts_the_example_plan(capsys: pytest.CaptureFixture[str]) -> None:
    example = Path(__file__).parent.parent / "examples" / "plan.json"
    assert cli.main(["validate", str(example)]) == 0
    assert "ok:" in capsys.readouterr().out


def test_run_executes_reviews_and_merges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = init_repo(tmp_path)
    install_fake_opencode(tmp_path, monkeypatch)
    monkeypatch.setenv("TEST_CLI_KEY", "k")
    config = tmp_path / "conductor.toml"
    config.write_text(CONFIG)
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps(
            {
                "goal": "demo",
                "steps": [
                    {"id": "a", "spec": "write output", "difficulty": 1},
                    {"id": "b", "spec": "write more", "difficulty": 2, "depends_on": ["a"]},
                ],
            }
        )
    )
    verdicts = iter([(False, "weak"), (True, "good"), (True, "good")])

    def fake_post(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        ok, reason = next(verdicts)
        return {"choices": [{"message": {"content": json.dumps({"ok": ok, "reason": reason})}}]}

    monkeypatch.setattr(reviewer, "http_post", fake_post)

    code = cli.main(["run", str(plan), "--config", str(config), "--repo", str(repo)])

    assert code == 0, capsys.readouterr().out
    lines = (repo / "output.txt").read_text().splitlines()
    assert len(lines) == 2
    assert all(line.startswith("made by openrouter/strong pid") for line in lines)
    runs = list((repo / ".conductor" / "runs").iterdir())
    assert len(runs) == 1
    run = json.loads((runs[0] / "run.json").read_text())
    assert run["steps"]["a"] == {
        "status": "approved",
        "detail": "good",
        "attempts": 2,
        "models": ["openrouter/cheap", "openrouter/strong"],
        "last_attempt": "step-a/attempt-2.json",
    }
    assert run["steps"]["b"]["attempts"] == 1
    assert (runs[0] / "step-a" / "attempt-1.json").exists()
    assert "conductor: merge" in git(repo, "log", "--oneline")
    assert git(repo, "worktree", "list").count("\n") == 1


def test_run_refuses_a_dirty_repository(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = init_repo(tmp_path)
    (repo / "dirty.txt").write_text("x")
    config = tmp_path / "conductor.toml"
    config.write_text(CONFIG)
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"goal": "g", "steps": [{"id": "a", "spec": "s"}]}))
    assert cli.main(["run", str(plan), "--config", str(config), "--repo", str(repo)]) == 2
    assert "uncommitted" in capsys.readouterr().out
