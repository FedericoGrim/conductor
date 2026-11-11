import json
import os
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from conductor import billing, cli, reviewer
from conductor.billing import read_ledger, record_run
from conductor.worker import commit_work, git

FAKE_OPENCODE = """#!/bin/sh
printf '{"type":"text","sessionID":"ses_fake","text":"hello"}\\n'
printf '{"type":"step_finish","sessionID":"ses_fake","part":{"cost":0.01}}\\n'
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
        content = json.dumps({"ok": ok, "reason": reason})
        return {"choices": [{"message": {"content": content}}], "usage": {"cost": 0.001}}

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
        "cost": pytest.approx(0.022),
    }
    assert run["cost"] == pytest.approx(0.033)
    assert read_ledger() == [
        {
            "project": str(repo),
            "run": runs[0].name,
            "finished_at": run["finished_at"],
            "provider": "openrouter",
            "cost": pytest.approx(0.033),
            "cost_by_model": {
                "openrouter/cheap": pytest.approx(0.01),
                "openrouter/strong": pytest.approx(0.02),
                "openrouter/judge": pytest.approx(0.003),
            },
        }
    ]
    assert run["steps"]["b"]["attempts"] == 1
    assert (runs[0] / "step-a" / "attempt-1.json").exists()
    assert "conductor: merge" in git(repo, "log", "--oneline")
    assert git(repo, "status", "--porcelain") == ""
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


def days_ago(days: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).isoformat(timespec="seconds")


def test_billing_project_lists_the_runs_of_the_repository_and_their_total(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = init_repo(tmp_path)
    runs = repo / ".conductor" / "runs"
    for name, run in (
        ("2026-11-09T08-00-00", {"finished_at": "2026-11-09T08:05:00+00:00"}),
        ("2026-11-10T08-00-00", {"finished_at": "2026-11-10T08:05:00+00:00", "cost": 0.25}),
        ("2026-11-11T08-00-00", {"finished_at": "2026-11-11T08:05:00+00:00", "cost": 1.5}),
    ):
        (runs / name).mkdir(parents=True)
        (runs / name / "run.json").write_text(json.dumps(run))
    nested = repo / "src"
    nested.mkdir()

    assert cli.main(["billing", "project", "--repo", str(nested)]) == 0

    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == f"project repo ({repo})"
    assert lines[1].split() == ["2026-11-09T08-00-00", "unknown"]
    assert lines[2].split() == ["2026-11-10T08-00-00", "0.2500", "USD"]
    assert lines[3].split() == ["2026-11-11T08-00-00", "1.5000", "USD"]
    assert lines[4].split() == ["total", "1.7500", "USD"]
    assert lines[5] == "1 run without a recorded cost"


def test_billing_project_says_when_there_are_no_runs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = init_repo(tmp_path)
    assert cli.main(["billing", "project", "--repo", str(repo)]) == 0
    assert "no runs recorded" in capsys.readouterr().out


def test_billing_projects_splits_the_spend_of_the_period_by_project(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    record_run(tmp_path / "alpha", "openrouter", "r1", {"finished_at": days_ago(1), "cost": 0.5})
    record_run(tmp_path / "alpha", "openrouter", "r2", {"finished_at": days_ago(5), "cost": 0.25})
    record_run(tmp_path / "beta", "openrouter", "r3", {"finished_at": days_ago(20), "cost": 2.25})
    record_run(tmp_path / "beta", "openrouter", "r4", {"finished_at": days_ago(40), "cost": 9.0})

    assert cli.main(["billing", "projects"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "last 30 days"
    assert lines[1].split() == ["beta", "2.2500", "USD", "75%", str(tmp_path / "beta")]
    assert lines[2].split() == ["alpha", "0.7500", "USD", "25%", str(tmp_path / "alpha")]
    assert lines[3].split() == ["total", "3.0000", "USD"]

    assert cli.main(["billing", "projects", "--days", "7"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "last 7 days"
    assert lines[1].split() == ["alpha", "0.7500", "USD", "100%", str(tmp_path / "alpha")]


def test_billing_projects_says_when_nothing_was_spent(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["billing", "projects"]) == 0
    assert "no runs recorded in the last 30 days" in capsys.readouterr().out


def test_billing_shows_the_balance_of_every_configured_provider(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "conductor.toml"
    config.write_text(
        CONFIG.replace("https://example.invalid/v1", "https://openrouter.ai/api/v1")
        + """
[privacy.high]
provider = "scaleway"
base_url = "https://api.scaleway.ai/v1"
api_key_env = "TEST_CLI_MISSING_KEY"
tiers = ["scaleway/m"]
reviewer = "scaleway/m"
"""
    )
    monkeypatch.setenv("TEST_CLI_KEY", "sk-secret")
    monkeypatch.delenv("TEST_CLI_MISSING_KEY", raising=False)

    def fake_get(url: str, headers: dict[str, str]) -> dict[str, Any]:
        assert url == "https://openrouter.ai/api/v1/credits"
        return {"data": {"total_credits": 20, "total_usage": 7.5}}

    monkeypatch.setattr(billing, "http_get", fake_get)

    assert cli.main(["billing", "--config", str(config)]) == 0
    out = capsys.readouterr().out
    lines = out.splitlines()
    assert lines[0].split() == [
        "openrouter.ai",
        "remaining",
        "12.5000",
        "USD",
        "used",
        "7.5000",
        "USD",
    ]
    assert lines[1].startswith("api.scaleway.ai")
    assert "environment variable TEST_CLI_MISSING_KEY is not set" in lines[1]
    assert "sk-secret" not in out
