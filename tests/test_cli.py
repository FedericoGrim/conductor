import json
import os
import stat
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from conductor import billing, cli, reviewer
from conductor.billing import read_ledger, record_run
from conductor.config import Config
from conductor.worker import commit_work, git
from tests.factories import CONVENTIONAL_COMMIT_HOOK, install_git_hook

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


EXAMPLE_PLAN = Path(__file__).parent.parent / "examples" / "plan.json"


def test_validate_accepts_the_example_plan(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "DEFAULT_CONFIG_PATHS", ())
    assert cli.main(["validate", str(EXAMPLE_PLAN)]) == 0
    assert capsys.readouterr().out == "ok: 3 steps\n"


SINGLE_PROVIDER = """
default_privacy = "medium"
[privacy.medium]
tiers = [["openrouter/a", "openrouter/a2"], ["openrouter/b", "deepseek/b2"]]
reviewer = "openrouter/r"

[privacy.medium.providers.openrouter]
base_url = "https://openrouter.ai/api/v1"
api_key_env = "OPENROUTER_API_KEY"

[privacy.medium.providers.deepseek]
base_url = "https://api.deepseek.com/v1"
api_key_env = "DEEPSEEK_API_KEY"
"""


def test_validate_warns_about_levels_that_depend_on_one_provider(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "conductor.toml"
    config.write_text(SINGLE_PROVIDER)
    assert cli.main(["validate", str(EXAMPLE_PLAN), "--config", str(config)]) == 0
    out = capsys.readouterr().out
    assert "ok: 3 steps" in out
    assert (
        "warning: privacy.medium: level 1, the reviewer rely only on openrouter; "
        "an outage there leaves them unavailable\n"
    ) in out
    assert "level 2" not in out


def test_validate_does_not_warn_about_a_brain_reviewer(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "conductor.toml"
    config.write_text(SINGLE_PROVIDER.replace('reviewer = "openrouter/r"', 'reviewer = "brain"'))
    cli.main(["validate", str(EXAMPLE_PLAN), "--config", str(config)])
    assert "reviewer" not in capsys.readouterr().out


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
        "question": None,
        "cost": pytest.approx(0.022),
        "subscription": None,
    }
    assert run["brain_session"] is None
    assert run["subscription"] is None
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
    assert "chore(conductor): merge" in git(repo, "log", "--oneline")
    assert git(repo, "status", "--porcelain") == ""
    assert git(repo, "worktree", "list").count("\n") == 1


def test_run_works_in_a_repository_that_enforces_conventional_commits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = init_repo(tmp_path)
    install_git_hook(repo, "commit-msg", CONVENTIONAL_COMMIT_HOOK)
    install_fake_opencode(tmp_path, monkeypatch)
    monkeypatch.setenv("TEST_CLI_KEY", "k")
    config = tmp_path / "conductor.toml"
    config.write_text(CONFIG)
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"goal": "g", "steps": [{"id": "a", "spec": "write output"}]}))

    def fake_post(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        content = json.dumps({"ok": True, "reason": "good"})
        return {"choices": [{"message": {"content": content}}]}

    monkeypatch.setattr(reviewer, "http_post", fake_post)

    code = cli.main(["run", str(plan), "--config", str(config), "--repo", str(repo)])

    assert code == 0, capsys.readouterr().out
    assert git(repo, "log", "-1", "--format=%s", "HEAD").startswith("chore(conductor): merge ")
    assert git(repo, "log", "-1", "--format=%s", "HEAD^2") == (
        "chore(conductor): apply step a attempt 1\n"
    )
    assert (repo / "output.txt").exists()


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
    assert "no API key: TEST_CLI_MISSING_KEY is not set or stored" in lines[1]
    assert "sk-secret" not in out


def test_billing_project_outside_a_repository_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["billing", "project", "--repo", str(tmp_path)]) == 2
    assert "not a git repository" in capsys.readouterr().err


def test_stats_prints_the_run_and_step_lines(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = init_repo(tmp_path)
    run = {
        "started_at": "2026-11-13T15:32:28+00:00",
        "finished_at": "2026-11-13T15:32:37+00:00",
        "privacy": "medium",
        "plan": {"steps": [{"id": "a", "files": ["output.txt"]}]},
        "steps": {
            "a": {
                "status": "approved",
                "attempts": 1,
                "models": ["openrouter/cheap"],
                "cost": 0.01,
                "subscription": 0.02,
            }
        },
        "cost": 0.01,
        "subscription": 0.02,
    }
    run_dir = repo / ".conductor" / "runs" / "2026-11-13T15-32-28"
    run_dir.mkdir(parents=True)
    (run_dir / "run.json").write_text(json.dumps(run))

    assert cli.main(["stats", "--repo", str(repo)]) == 0

    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == (
        "run 2026-11-13T15-32-28  privacy medium  finished 2026-11-13T15:32:37+00:00"
    )
    assert lines[1] == (
        "  step a  approved  attempts 1  first try yes  models openrouter/cheap  "
        "cost 0.0100 USD  subscription 0.0200 USD  hand commits 0"
    )
    assert lines[2] == "  total  cost 0.0100 USD  subscription 0.0200 USD"
    assert lines[3] == "  brain n/a"


def test_stats_says_when_there_are_no_runs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = init_repo(tmp_path)

    assert cli.main(["stats", "--repo", str(repo)]) == 0

    assert capsys.readouterr().out == "no runs recorded\n"


def test_stats_outside_a_repository_is_an_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["stats", "--repo", str(tmp_path)]) == 2
    assert "not a git repository" in capsys.readouterr().err


def test_a_ledger_that_cannot_be_written_does_not_fail_the_run(
    tmp_path: Path,
    isolated_data_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = init_repo(tmp_path)
    install_fake_opencode(tmp_path, monkeypatch)
    monkeypatch.setenv("TEST_CLI_KEY", "k")
    config = tmp_path / "conductor.toml"
    config.write_text(CONFIG)
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({"goal": "g", "steps": [{"id": "a", "spec": "s"}]}))
    isolated_data_home.write_text("a file where the data directory should be")

    def approve(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        return {"choices": [{"message": {"content": '{"ok": true, "reason": "good"}'}}]}

    monkeypatch.setattr(reviewer, "http_post", approve)

    assert cli.main(["run", str(plan), "--config", str(config), "--repo", str(repo)]) == 0
    assert "warning: could not record the run in the ledger" in capsys.readouterr().err


def test_config_path_prints_the_configuration_in_use(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = tmp_path / "conductor.toml"
    config.write_text(CONFIG)
    assert cli.main(["config", "path", "--config", str(config)]) == 0
    assert capsys.readouterr().out.strip() == str(config)


def test_config_export_and_import_round_trip_through_the_cli(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "conductor.toml"
    source.write_text(CONFIG)
    exported = tmp_path / "my-settings.toml"
    assert cli.main(["config", "export", str(exported), "--config", str(source)]) == 0
    assert "my-settings.toml" in capsys.readouterr().out
    assert "schema" in exported.read_text()

    target = tmp_path / "other.toml"
    assert cli.main(["config", "import", str(exported), "--config", str(target)]) == 0
    out = capsys.readouterr().out
    assert "medium" in out
    assert Config.load(target).profile("medium").tiers[0] == ("openrouter/cheap",)

    assert cli.main(["config", "import", str(exported), "--config", str(target)]) == 0
    assert "previous file kept" in capsys.readouterr().out


def test_config_import_reports_missing_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("TEST_CLI_KEY", raising=False)
    source = tmp_path / "conductor.toml"
    source.write_text(CONFIG)
    exported = tmp_path / "settings.toml"
    assert cli.main(["config", "export", str(exported), "--config", str(source)]) == 0
    capsys.readouterr()
    assert (
        cli.main(["config", "import", str(exported), "--config", str(tmp_path / "out.toml")]) == 0
    )
    assert "TEST_CLI_KEY" in capsys.readouterr().out


def test_config_export_requires_an_existing_configuration(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        cli.main(
            [
                "config",
                "export",
                str(tmp_path / "s.toml"),
                "--config",
                str(tmp_path / "missing.toml"),
            ]
        )
        == 2
    )
    assert "no conductor.toml" in capsys.readouterr().err


def test_config_import_refuses_a_broken_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = tmp_path / "broken.toml"
    broken.write_text("not = [valid")
    assert cli.main(["config", "import", str(broken), "--config", str(tmp_path / "out.toml")]) == 2
    assert "cannot read" in capsys.readouterr().err


def run_verified_plan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    plan_fields: dict[str, Any],
    prepare: Callable[[Path], None] = lambda repo: None,
    extra_args: tuple[str, ...] = (),
) -> tuple[int, Path, list[dict[str, Any]]]:
    repo = init_repo(tmp_path)
    prepare(repo)
    install_fake_opencode(tmp_path, monkeypatch)
    monkeypatch.setenv("TEST_CLI_KEY", "k")
    config = tmp_path / "conductor.toml"
    config.write_text(CONFIG)
    plan = tmp_path / "plan.json"
    steps = [{"id": "a", "spec": "write output", "difficulty": 1}]
    plan.write_text(json.dumps({"goal": "demo", "steps": steps, **plan_fields}))
    requests: list[dict[str, Any]] = []

    def fake_post(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        requests.append(body)
        content = json.dumps({"ok": True, "reason": "good"})
        return {"choices": [{"message": {"content": content}}], "usage": {"cost": 0.001}}

    monkeypatch.setattr(reviewer, "http_post", fake_post)
    code = cli.main(["run", str(plan), "--config", str(config), "--repo", str(repo), *extra_args])
    return code, repo, requests


def test_run_rejects_an_attempt_whose_checks_fail_without_calling_the_reviewer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    check = 'grep -q strong output.txt && test -d "$CONDUCTOR_REPO/.git"'
    code, repo, requests = run_verified_plan(tmp_path, monkeypatch, {"verify": [check]})
    assert code == 0
    assert len(requests) == 1
    run_dir = next((repo / ".conductor" / "runs").iterdir())
    first = json.loads((run_dir / "step-a" / "attempt-1.json").read_text())
    assert first["verify"][0]["exit_code"] == 1
    assert first["review"] is None


def test_run_sends_the_plan_rules_and_the_rules_file_to_the_reviewer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def write_rules(repo: Path) -> None:
        (repo / "docs").mkdir()
        (repo / "docs" / "rules.md").write_text("Orders own their lines.\n")
        commit_work(repo, "rules")

    fields = {"rules": ["Totals never go negative"], "rules_file": "docs/rules.md"}
    code, _, requests = run_verified_plan(tmp_path, monkeypatch, fields, prepare=write_rules)
    assert code == 0
    prompt = requests[0]["messages"][-1]["content"]
    assert "- Totals never go negative" in prompt
    assert "Orders own their lines." in prompt


def test_run_stops_before_any_attempt_when_the_rules_file_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code, repo, requests = run_verified_plan(
        tmp_path, monkeypatch, {"rules_file": "docs/missing.md"}
    )
    assert code == 2
    assert "docs/missing.md" in capsys.readouterr().err
    assert not (repo / "output.txt").exists()


def test_run_records_the_brain_session_option_in_run_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, repo, _ = run_verified_plan(tmp_path, monkeypatch, {}, extra_args=("--session", "ses_x"))
    assert code == 0
    run_dir = next((repo / ".conductor" / "runs").iterdir())
    run = json.loads((run_dir / "run.json").read_text())
    assert run["brain_session"] == {"harness": "opencode", "id": "ses_x"}


def test_run_takes_the_brain_session_from_the_environment_without_the_option(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENCODE_SESSION_ID", "ses_env")
    code, repo, _ = run_verified_plan(tmp_path, monkeypatch, {})
    assert code == 0
    run_dir = next((repo / ".conductor" / "runs").iterdir())
    run = json.loads((run_dir / "run.json").read_text())
    assert run["brain_session"] == {"harness": "opencode", "id": "ses_env"}
