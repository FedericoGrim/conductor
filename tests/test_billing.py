import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from conductor.billing import (
    RunCost,
    ledger_path,
    project_runs,
    read_ledger,
    record_run,
    spend_by_project,
)


def finished_run(cost: float, finished_at: str = "2026-11-11T10:00:00+00:00") -> dict[str, Any]:
    return {"finished_at": finished_at, "cost": cost, "cost_by_model": {"openrouter/m": cost}}


def test_ledger_lives_under_the_user_data_directory(isolated_data_home: Path) -> None:
    assert ledger_path() == isolated_data_home / "conductor" / "ledger.jsonl"


def test_record_run_appends_one_line_per_run(tmp_path: Path) -> None:
    record_run(tmp_path / "alpha", "openrouter", "run-1", finished_run(0.5))
    record_run(tmp_path / "beta", "scaleway", "run-2", finished_run(0.25))

    assert len(ledger_path().read_text().splitlines()) == 2
    assert read_ledger() == [
        {
            "project": str(tmp_path / "alpha"),
            "run": "run-1",
            "finished_at": "2026-11-11T10:00:00+00:00",
            "provider": "openrouter",
            "cost": 0.5,
            "cost_by_model": {"openrouter/m": 0.5},
        },
        {
            "project": str(tmp_path / "beta"),
            "run": "run-2",
            "finished_at": "2026-11-11T10:00:00+00:00",
            "provider": "scaleway",
            "cost": 0.25,
            "cost_by_model": {"openrouter/m": 0.25},
        },
    ]


def test_read_ledger_is_empty_without_a_file_and_skips_broken_lines() -> None:
    assert read_ledger() == []
    ledger_path().parent.mkdir(parents=True)
    ledger_path().write_text('{"project": "/p", "cost": 1}\nnot json\n[1, 2]\n')
    assert read_ledger() == [{"project": "/p", "cost": 1}]


def test_spend_by_project_sums_runs_finished_since_the_given_moment() -> None:
    entries = [
        {"project": "/alpha", "finished_at": "2026-11-10T09:00:00+00:00", "cost": 0.5},
        {"project": "/alpha", "finished_at": "2026-11-11T09:00:00+00:00", "cost": 0.25},
        {"project": "/beta", "finished_at": "2026-11-01T09:00:00+00:00", "cost": 2.0},
        {"project": "/beta", "finished_at": "2026-09-30T09:00:00+00:00", "cost": 9.0},
        {"project": "/gamma", "finished_at": "garbage", "cost": 9.0},
        {"project": "/gamma", "cost": 9.0},
    ]
    since = datetime(2026, 10, 12, tzinfo=UTC)
    assert spend_by_project(entries, since) == {"/alpha": 0.75, "/beta": 2.0}


def write_run(repo: Path, name: str, run: dict[str, Any]) -> None:
    directory = repo / ".conductor" / "runs" / name
    directory.mkdir(parents=True)
    (directory / "run.json").write_text(json.dumps(run))


def test_project_runs_lists_every_run_oldest_first(tmp_path: Path) -> None:
    write_run(tmp_path, "2026-11-11T10-00-00", finished_run(0.4))
    write_run(tmp_path, "2026-11-10T08-00-00", {"finished_at": "2026-11-10T08:05:00+00:00"})
    (tmp_path / ".conductor" / "runs" / "2026-11-12T00-00-00").mkdir()

    assert project_runs(tmp_path) == [
        RunCost("2026-11-10T08-00-00", "2026-11-10T08:05:00+00:00", None),
        RunCost("2026-11-11T10-00-00", "2026-11-11T10:00:00+00:00", 0.4),
    ]


def test_project_runs_is_empty_for_a_project_never_run(tmp_path: Path) -> None:
    assert project_runs(tmp_path) == []
