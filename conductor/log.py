from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from conductor.plan import Plan, Step
from conductor.scheduler import StepResult


def now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


@dataclass
class RunLog:
    directory: Path
    run: dict[str, Any]

    @classmethod
    def create(cls, repo: Path, plan: Plan, privacy: str) -> RunLog:
        runs = repo / ".conductor" / "runs"
        runs.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S")
        directory = runs / stamp
        suffix = 1
        while directory.exists():
            suffix += 1
            directory = runs / f"{stamp}-{suffix}"
        directory.mkdir()
        log = cls(
            directory,
            {
                "started_at": now(),
                "finished_at": None,
                "privacy": privacy,
                "plan": asdict(plan),
                "steps": {},
            },
        )
        log.write_run()
        return log

    def write_run(self) -> None:
        (self.directory / "run.json").write_text(json.dumps(self.run, indent=2) + "\n")

    def attempt(self, step: Step, data: dict[str, Any]) -> Path:
        step_dir = self.directory / f"step-{step.id}"
        step_dir.mkdir(exist_ok=True)
        path = step_dir / f"attempt-{data['attempt']}.json"
        payload = {"step": {"id": step.id, "title": step.title}, "recorded_at": now(), **data}
        path.write_text(json.dumps(payload, indent=2) + "\n")
        return path

    def finish(self, results: dict[str, StepResult]) -> None:
        for step_id, result in results.items():
            count = len(result.attempts)
            self.run["steps"][step_id] = {
                "status": result.status,
                "detail": result.detail,
                "attempts": count,
                "models": [a.get("model") for a in result.attempts],
                "last_attempt": f"step-{step_id}/attempt-{count}.json" if count else None,
            }
        self.run["finished_at"] = now()
        self.write_run()
