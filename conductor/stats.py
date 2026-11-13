from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from conductor.brain import TokenUsage, session_tokens
from conductor.worker import git

HandCommits = Callable[[Path, str, tuple[str, ...]], int | None]


@dataclass(frozen=True)
class StepStats:
    step_id: str
    status: str
    attempts: int
    models: tuple[str, ...]
    cost: float | None
    subscription: float | None
    first_try: bool
    hand_commits: int | None


@dataclass(frozen=True)
class RunStats:
    name: str
    started_at: str | None
    finished_at: str | None
    privacy: str | None
    steps: tuple[StepStats, ...]
    cost: float | None
    subscription: float | None
    brain_session: str | None
    brain_tokens: dict[str, TokenUsage] | None


def hand_commits(repo: Path, since: str, files: tuple[str, ...]) -> int | None:
    if not files:
        return None
    try:
        output = git(
            repo, "log", "--no-merges", f"--since={since}", "--format=%an%x00%s", "--", *files
        )
    except subprocess.CalledProcessError:
        return None
    count = 0
    for line in output.splitlines():
        author, separator, subject = line.partition("\x00")
        if not separator:
            continue
        if author == "conductor" or subject.startswith("chore(conductor):"):
            continue
        count += 1
    return count


def collect(
    repo: Path,
    hand: HandCommits = hand_commits,
    tokens: Callable[[str], dict[str, TokenUsage] | None] = session_tokens,
) -> list[RunStats]:
    runs_dir = repo / ".conductor" / "runs"
    if not runs_dir.is_dir():
        return []
    run_dirs = sorted(
        (
            entry
            for entry in runs_dir.iterdir()
            if entry.is_dir() and (entry / "run.json").is_file()
        ),
        key=lambda entry: entry.name,
    )
    token_cache: dict[str, dict[str, TokenUsage] | None] = {}
    runs: list[RunStats] = []
    for run_dir in run_dirs:
        run = _read_json_object((run_dir / "run.json").read_text())
        if run is None:
            continue
        runs.append(_run_stats(repo, run_dir.name, run, hand, tokens, token_cache))
    return runs


def format_report(runs: list[RunStats]) -> list[str]:
    if not runs:
        return ["no runs recorded"]
    lines: list[str] = []
    for run in runs:
        lines.extend(_format_run(run))
    return lines


def _read_json_object(text: str) -> dict[str, Any] | None:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _run_stats(
    repo: Path,
    name: str,
    run: dict[str, Any],
    hand: HandCommits,
    tokens: Callable[[str], dict[str, TokenUsage] | None],
    token_cache: dict[str, dict[str, TokenUsage] | None],
) -> RunStats:
    finished_at = _optional_string(run.get("finished_at"))
    plan_files = _plan_files(run.get("plan"))
    steps = tuple(
        _step_stats(repo, step_id, entry, plan_files.get(step_id, ()), finished_at, hand)
        for step_id, entry in _steps(run.get("steps"))
    )
    brain_session = _brain_session(run.get("brain_session"))
    return RunStats(
        name=name,
        started_at=_optional_string(run.get("started_at")),
        finished_at=finished_at,
        privacy=_optional_string(run.get("privacy")),
        steps=steps,
        cost=_optional_number(run.get("cost")),
        subscription=_optional_number(run.get("subscription")),
        brain_session=brain_session,
        brain_tokens=_brain_tokens(brain_session, tokens, token_cache),
    )


def _steps(value: Any) -> list[tuple[str, dict[str, Any]]]:
    if not isinstance(value, dict):
        return []
    return [(str(step_id), entry) for step_id, entry in value.items() if isinstance(entry, dict)]


def _plan_files(value: Any) -> dict[str, tuple[str, ...]]:
    files_by_step: dict[str, tuple[str, ...]] = {}
    if not isinstance(value, dict):
        return files_by_step
    plan_steps = value.get("steps")
    if not isinstance(plan_steps, list):
        return files_by_step
    for step in plan_steps:
        if not isinstance(step, dict):
            continue
        step_id = step.get("id")
        files = step.get("files")
        if isinstance(step_id, str) and isinstance(files, list):
            files_by_step[step_id] = tuple(item for item in files if isinstance(item, str))
    return files_by_step


def _step_stats(
    repo: Path,
    step_id: str,
    entry: dict[str, Any],
    files: tuple[str, ...],
    finished_at: str | None,
    hand: HandCommits,
) -> StepStats:
    status = _string(entry.get("status"))
    attempts = _integer(entry.get("attempts"))
    return StepStats(
        step_id=step_id,
        status=status,
        attempts=attempts,
        models=_strings(entry.get("models")),
        cost=_optional_number(entry.get("cost")),
        subscription=_optional_number(entry.get("subscription")),
        first_try=status == "approved" and attempts == 1,
        hand_commits=hand(repo, finished_at, files) if finished_at is not None else None,
    )


def _brain_session(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    session_id = value.get("id")
    return session_id if isinstance(session_id, str) else None


def _brain_tokens(
    session_id: str | None,
    tokens: Callable[[str], dict[str, TokenUsage] | None],
    cache: dict[str, dict[str, TokenUsage] | None],
) -> dict[str, TokenUsage] | None:
    if session_id is None:
        return None
    if session_id not in cache:
        cache[session_id] = tokens(session_id)
    return cache[session_id]


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _string(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _integer(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _optional_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _strings(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str))


def _format_run(run: RunStats) -> list[str]:
    privacy = run.privacy if run.privacy is not None else "n/a"
    finished = run.finished_at if run.finished_at is not None else "n/a"
    lines = [f"run {run.name}  privacy {privacy}  finished {finished}"]
    lines.extend(_format_step(step) for step in run.steps)
    lines.append(f"  total  cost {_money(run.cost)}  subscription {_money(run.subscription)}")
    lines.extend(_format_brain(run))
    return lines


def _format_step(step: StepStats) -> str:
    models = ", ".join(step.models) if step.models else "n/a"
    hand = str(step.hand_commits) if step.hand_commits is not None else "n/a"
    first_try = "yes" if step.first_try else "no"
    return (
        f"  step {step.step_id}  {step.status}  attempts {step.attempts}  "
        f"first try {first_try}  models {models}  "
        f"cost {_money(step.cost)}  subscription {_money(step.subscription)}  "
        f"hand commits {hand}"
    )


def _format_brain(run: RunStats) -> list[str]:
    if run.brain_session is None:
        return ["  brain n/a"]
    if run.brain_tokens is None:
        return [f"  brain {run.brain_session}  n/a"]
    lines: list[str] = []
    for model in sorted(run.brain_tokens):
        usage = run.brain_tokens[model]
        lines.append(
            f"  brain {run.brain_session}  {model}  "
            f"replies {usage.replies}  output {usage.output}  "
            f"reasoning {usage.reasoning}  input {usage.input}  "
            f"cache write {usage.cache_write}  cache read {usage.cache_read}"
        )
    return lines


def _money(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f} USD"
