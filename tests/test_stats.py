from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from conductor.brain import TokenUsage
from conductor.stats import StepStats, collect, format_report, hand_commits
from conductor.worker import git

SINCE = "2000-01-01T00:00:00+00:00"
URUSAGE = TokenUsage(
    replies=12, output=3400, reasoning=900, input=50, cache_write=12000, cache_read=45000
)


def write_run(repo: Path, name: str, run: dict[str, Any]) -> Path:
    directory = repo / ".conductor" / "runs" / name
    directory.mkdir(parents=True)
    (directory / "run.json").write_text(json.dumps(run))
    return directory


def make_run(
    *,
    started_at: str = "2026-11-13T15:32:28+00:00",
    finished_at: str | None = "2026-11-13T15:32:37+00:00",
    privacy: str = "dogfood",
    steps: dict[str, dict[str, Any]] | None = None,
    cost: float | None = 0.0,
    subscription: float | None = 0.0497,
    brain_session: dict[str, str] | None = None,
) -> dict[str, Any]:
    if steps is None:
        steps = {
            "hello-script": {
                "status": "approved",
                "attempts": 1,
                "models": ["claude-code/sonnet"],
                "cost": 0.0,
                "subscription": 0.0497,
            }
        }
    return {
        "started_at": started_at,
        "finished_at": finished_at,
        "privacy": privacy,
        "plan": {"steps": [{"id": "hello-script", "files": ["scripts/hello.sh"]}]},
        "steps": steps,
        "cost": cost,
        "subscription": subscription,
        "brain_session": brain_session,
    }


def zero_hand(repo: Path, since: str, files: tuple[str, ...]) -> int | None:
    return 0


def no_tokens(session_id: str) -> dict[str, TokenUsage] | None:
    return None


def brain_tokens(session_id: str) -> dict[str, TokenUsage] | None:
    return {"claude-agent/opus": URUSAGE}


def test_collects_a_complete_run(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    write_run(
        repo,
        "2026-11-13T15-32-28",
        make_run(brain_session={"harness": "opencode", "id": "ses_abc"}),
    )

    runs = collect(repo, hand=zero_hand, tokens=brain_tokens)

    assert len(runs) == 1
    run = runs[0]
    assert run.name == "2026-11-13T15-32-28"
    assert run.started_at == "2026-11-13T15:32:28+00:00"
    assert run.finished_at == "2026-11-13T15:32:37+00:00"
    assert run.privacy == "dogfood"
    assert run.cost == 0.0
    assert run.subscription == 0.0497
    assert run.brain_session == "ses_abc"
    assert run.brain_tokens == {"claude-agent/opus": URUSAGE}
    assert run.steps == (
        StepStats(
            step_id="hello-script",
            status="approved",
            attempts=1,
            models=("claude-code/sonnet",),
            cost=0.0,
            subscription=0.0497,
            first_try=True,
            hand_commits=0,
        ),
    )


def test_an_older_run_without_optional_keys_prints_n_a_never_zero(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    older: dict[str, Any] = {
        "started_at": "2026-11-10T10:00:00+00:00",
        "finished_at": "2026-11-10T10:05:00+00:00",
        "privacy": "internal",
        "plan": {"steps": [{"id": "legacy", "files": ["legacy.txt"]}]},
        "steps": {
            "legacy": {
                "status": "approved",
                "attempts": 2,
                "models": ["openrouter/r"],
            }
        },
    }
    write_run(repo, "2026-11-10T10-00-00", older)

    runs = collect(repo, hand=zero_hand, tokens=no_tokens)

    run = runs[0]
    assert run.cost is None
    assert run.subscription is None
    assert run.brain_session is None
    assert run.brain_tokens is None
    assert run.steps[0].cost is None
    assert run.steps[0].subscription is None

    lines = format_report(runs)
    step_line = lines[1]
    total_line = lines[2]
    assert "cost n/a" in step_line
    assert "subscription n/a" in step_line
    assert "cost 0.0000 USD" not in step_line
    assert "cost n/a" in total_line
    assert "subscription n/a" in total_line
    assert lines[3] == "  brain n/a"


def test_an_unfinished_run_does_not_call_hand(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    calls: list[tuple[str, tuple[str, ...]]] = []

    def hand(repo_path: Path, since: str, files: tuple[str, ...]) -> int | None:
        calls.append((since, files))
        return 0

    write_run(repo, "2026-11-13T15-32-28", make_run(finished_at=None))
    runs = collect(repo, hand=hand, tokens=no_tokens)

    assert calls == []
    assert runs[0].finished_at is None
    assert runs[0].steps[0].hand_commits is None
    assert format_report(runs)[0].endswith("finished n/a")


def test_invalid_run_json_is_skipped(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    write_run(repo, "2026-11-13T15-32-28", make_run())
    bad = repo / ".conductor" / "runs" / "2026-11-13T15-32-29"
    bad.mkdir(parents=True)
    (bad / "run.json").write_text("{not json")

    runs = collect(repo, hand=zero_hand, tokens=no_tokens)

    assert [run.name for run in runs] == ["2026-11-13T15-32-28"]


def test_a_run_json_that_is_not_utf8_is_skipped(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    write_run(repo, "2026-11-13T15-32-28", make_run())
    bad = repo / ".conductor" / "runs" / "2026-11-13T15-32-29"
    bad.mkdir(parents=True)
    (bad / "run.json").write_bytes(b"\xff\xfe{}")

    runs = collect(repo, hand=zero_hand, tokens=no_tokens)

    assert [run.name for run in runs] == ["2026-11-13T15-32-28"]


def test_session_tokens_are_cached_per_id(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    calls: list[str] = []

    def tokens(session_id: str) -> dict[str, TokenUsage] | None:
        calls.append(session_id)
        return {"m/a": TokenUsage(replies=1)}

    write_run(
        repo,
        "2026-11-13T15-32-28",
        make_run(brain_session={"harness": "opencode", "id": "ses_abc"}),
    )
    write_run(
        repo,
        "2026-11-13T15-32-29",
        make_run(brain_session={"harness": "opencode", "id": "ses_abc"}),
    )
    runs = collect(repo, hand=zero_hand, tokens=tokens)

    assert calls == ["ses_abc"]
    assert runs[0].brain_tokens is runs[1].brain_tokens
    assert runs[0].brain_tokens == {"m/a": TokenUsage(replies=1)}


def test_first_try_true_and_false(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    write_run(repo, "2026-11-13T15-32-28", make_run())
    write_run(
        repo,
        "2026-11-13T15-32-29",
        make_run(
            steps={
                "hello-script": {
                    "status": "approved",
                    "attempts": 2,
                    "models": ["claude-code/sonnet"],
                }
            }
        ),
    )

    runs = collect(repo, hand=zero_hand, tokens=no_tokens)

    assert runs[0].steps[0].first_try is True
    assert runs[1].steps[0].first_try is False


def test_format_report_exact_lines(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    write_run(
        repo,
        "2026-11-13T15-32-28",
        make_run(brain_session={"harness": "opencode", "id": "ses_abc"}),
    )

    assert format_report(collect(repo, hand=zero_hand, tokens=brain_tokens)) == [
        "run 2026-11-13T15-32-28  privacy dogfood  finished 2026-11-13T15:32:37+00:00",
        "  step hello-script  approved  attempts 1  first try yes  "
        "models claude-code/sonnet  cost 0.0000 USD  subscription 0.0497 USD  "
        "hand commits 0",
        "  total  cost 0.0000 USD  subscription 0.0497 USD",
        "  brain ses_abc  claude-agent/opus  replies 12  output 3400  reasoning 900  "
        "input 50  cache write 12000  cache read 45000",
    ]


def test_format_report_with_no_runs(tmp_path: Path) -> None:
    assert format_report([]) == ["no runs recorded"]


def commit(repo: Path, author: str, message: str) -> None:
    subprocess.run(
        [
            "git",
            "-c",
            f"user.name={author}",
            "-c",
            f"user.email={author}@example.com",
            "commit",
            "-q",
            "-m",
            message,
        ],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "README.md").write_text("base\n")
    git(repo, "add", ".")
    commit(repo, "alice", "init")
    return repo


def test_hand_commits_counts_human_commits_on_step_files(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    src = repo / "src"
    src.mkdir()
    app = src / "app.py"

    app.write_text("first\n")
    git(repo, "add", ".")
    commit(repo, "alice", "add the hand edit")

    app.write_text("second\n")
    git(repo, "add", ".")
    commit(repo, "conductor", "apply step")

    app.write_text("third\n")
    git(repo, "add", ".")
    commit(repo, "alice", "chore(conductor): apply step hello attempt 1")

    (src / "other.py").write_text("other\n")
    git(repo, "add", ".")
    commit(repo, "alice", "edit an unrelated file")

    assert hand_commits(repo, SINCE, ("src/app.py",)) == 1
    assert hand_commits(repo, SINCE, ()) is None
