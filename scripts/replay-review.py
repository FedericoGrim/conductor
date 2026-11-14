"""Replay a recorded attempt through the reviewer, several times.

Reads an attempt JSON written by a run and the run.json two directories up,
and sends the same review request to a reviewer model again and again, to test
reviewer prompts and models (rejection categories, model benchmarks). Prints
one line per verdict and a summary; never prints the API key.

Usage: python scripts/replay-review.py <path/to/step-<id>/attempt-N.json>
       [--privacy medium] [--config PATH] [--reviewer MODEL] [--times 5]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from conductor import rejections, reviewer
from conductor.cli import find_config, money
from conductor.config import Config, ConfigError
from conductor.plan import Plan, PlanError
from conductor.reviewer import Verdict
from conductor.verify import CheckResult

REASON_LIMIT = 200


class ReplayError(ValueError):
    pass


@dataclass
class ReplayInput:
    spec: str
    rules: tuple[str, ...]
    checks: list[CheckResult]
    commit_message: str
    diff: str


def read_json(path: Path, what: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except OSError as error:
        raise ReplayError(f"cannot read {what} '{path}': {error.strerror or error}") from error
    except json.JSONDecodeError as error:
        raise ReplayError(f"{what} '{path}' is not valid JSON: {error}") from error
    if not isinstance(data, dict):
        raise ReplayError(f"{what} '{path}' does not contain a JSON object")
    return data


def attempt_step_id(attempt: dict[str, Any]) -> str:
    step = attempt.get("step")
    if isinstance(step, str):
        return step
    if isinstance(step, dict):
        step_id = step.get("id")
        if isinstance(step_id, str):
            return step_id
    raise ReplayError("the attempt does not name a step")


def load_attempt(path: Path) -> ReplayInput:
    attempt = read_json(path, "attempt")
    run_path = path.parent.parent / "run.json"
    run = read_json(run_path, "run.json")
    if "plan" not in run:
        raise ReplayError(f"run.json '{run_path}' has no plan")
    try:
        plan = Plan.from_dict(run["plan"])
    except (AttributeError, TypeError, ValueError) as error:
        raise ReplayError(f"the plan in '{run_path}' is invalid: {error}") from error
    step_id = attempt_step_id(attempt)
    step = next((entry for entry in plan.steps if entry.id == step_id), None)
    if step is None:
        raise ReplayError(f"step '{step_id}' is not in the plan in '{run_path}'")
    if plan.rules_file is not None:
        print(
            f"note: rules_file '{plan.rules_file}' is ignored; only the plan's rules are replayed"
        )
    try:
        checks = [CheckResult(**entry) for entry in attempt["verify"]]
        diff = str(attempt["diff"])
    except (KeyError, TypeError) as error:
        raise ReplayError(f"attempt '{path}' is missing review input: {error}") from error
    return ReplayInput(
        spec=step.spec,
        rules=plan.rules,
        checks=checks,
        commit_message=str(attempt.get("commit_message") or ""),
        diff=diff,
    )


def verdict_line(index: int, verdict: Verdict, checks: list[CheckResult]) -> str:
    if verdict.error is not None:
        status = "error"
    elif verdict.ok:
        status = "approved"
    else:
        status = "rejected"
    category = verdict.category or "-"
    suspicious = (
        " suspicious" if rejections.is_suspicious(verdict.ok, verdict.category, checks) else ""
    )
    cost = money(verdict.cost) if verdict.cost is not None else "-"
    return f"{index}  {status:<8}  {category}{suspicious}  {cost}  {verdict.reason[:REASON_LIMIT]}"


def summary(verdicts: list[Verdict], checks: list[CheckResult]) -> str:
    errors = sum(verdict.error is not None for verdict in verdicts)
    approved = sum(verdict.error is None and verdict.ok for verdict in verdicts)
    rejected = sum(verdict.error is None and not verdict.ok for verdict in verdicts)
    suspicious = sum(
        rejections.is_suspicious(verdict.ok, verdict.category, checks) for verdict in verdicts
    )
    costs = [verdict.cost for verdict in verdicts if verdict.cost is not None]
    total = money(sum(costs)) if costs else "-"
    return (
        f"approvals {approved}  rejections {rejected}  suspicious rejections {suspicious}  "
        f"errors {errors}  cost {total}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="replay a recorded attempt through the reviewer several times"
    )
    parser.add_argument("attempt", type=Path, help="path to step-<id>/attempt-N.json")
    parser.add_argument("--privacy", default="medium", help="profile name from conductor.toml")
    parser.add_argument("--config", type=Path, help="path to conductor.toml")
    parser.add_argument("--reviewer", help="reviewer model (default: the profile's first reviewer)")
    parser.add_argument("--times", type=int, default=5, help="how many times to ask the reviewer")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        recorded = load_attempt(args.attempt)
        profile = Config.load(find_config(args.config)).profile(args.privacy)
        model = args.reviewer or profile.reviewers[0]
        verdicts: list[Verdict] = []
        for index in range(1, args.times + 1):
            verdict = reviewer.review(
                profile,
                model,
                recorded.spec,
                recorded.diff,
                rules=recorded.rules,
                checks=recorded.checks,
                commit_message=recorded.commit_message,
            )
            verdicts.append(verdict)
            print(verdict_line(index, verdict, recorded.checks))
        print(summary(verdicts, recorded.checks))
        return 0
    except (ReplayError, ConfigError, PlanError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
