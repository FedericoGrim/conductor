from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from conductor.config import Profile

Get = Callable[[str, dict[str, str]], dict[str, Any]]


class BillingError(RuntimeError):
    def __init__(self, status: int) -> None:
        super().__init__(f"HTTP {status}")
        self.status = status


@dataclass(frozen=True)
class Balance:
    account: str
    remaining: float | None = None
    used: float | None = None
    currency: str = "USD"
    note: str = ""


def balances(profiles: Iterable[Profile], get: Get | None = None) -> list[Balance]:
    raise NotImplementedError


@dataclass(frozen=True)
class RunCost:
    run: str
    finished_at: str | None
    cost: float | None


def ledger_path() -> Path:
    data_home = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(data_home) / "conductor" / "ledger.jsonl"


def record_run(project: Path, provider: str, run_name: str, run: dict[str, Any]) -> None:
    entry = {
        "project": str(project),
        "run": run_name,
        "finished_at": run.get("finished_at"),
        "provider": provider,
        "cost": run.get("cost", 0.0),
        "cost_by_model": run.get("cost_by_model", {}),
    }
    path = ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as ledger:
        ledger.write(json.dumps(entry) + "\n")


def read_json_object(text: str) -> dict[str, Any] | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def read_ledger() -> list[dict[str, Any]]:
    path = ledger_path()
    if not path.exists():
        return []
    entries = (read_json_object(line) for line in path.read_text().splitlines())
    return [entry for entry in entries if entry is not None]


def finished_since(entry: dict[str, Any], since: datetime) -> bool:
    try:
        return datetime.fromisoformat(str(entry.get("finished_at"))) >= since
    except ValueError:
        return False


def spend_by_project(entries: list[dict[str, Any]], since: datetime) -> dict[str, float]:
    totals: dict[str, float] = {}
    for entry in entries:
        cost = entry.get("cost")
        if isinstance(cost, int | float) and finished_since(entry, since):
            project = str(entry.get("project"))
            totals[project] = totals.get(project, 0.0) + cost
    return totals


def project_runs(repo: Path) -> list[RunCost]:
    runs: list[RunCost] = []
    for run_file in sorted((repo / ".conductor" / "runs").glob("*/run.json")):
        run = read_json_object(run_file.read_text()) or {}
        cost = run.get("cost")
        runs.append(
            RunCost(
                run=run_file.parent.name,
                finished_at=run.get("finished_at"),
                cost=float(cost) if isinstance(cost, int | float) else None,
            )
        )
    return runs
