from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RunCost:
    run: str
    finished_at: str | None
    cost: float | None


def ledger_path() -> Path:
    raise NotImplementedError


def record_run(project: Path, provider: str, run_name: str, run: dict[str, Any]) -> None:
    raise NotImplementedError


def read_ledger() -> list[dict[str, Any]]:
    raise NotImplementedError


def spend_by_project(entries: list[dict[str, Any]], since: datetime) -> dict[str, float]:
    raise NotImplementedError


def project_runs(repo: Path) -> list[RunCost]:
    raise NotImplementedError
