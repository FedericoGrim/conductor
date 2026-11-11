from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from conductor import reviewer
from conductor.config import Config, ConfigError, Profile
from conductor.escalation import run_step
from conductor.log import RunLog
from conductor.merge import merge_branch
from conductor.plan import Plan, PlanError, Step
from conductor.privacy import opencode_config
from conductor.scheduler import APPROVED, CONFLICT, StepResult, run_plan
from conductor.worker import (
    AttemptOutput,
    create_worktree,
    exclude_from_git,
    git,
    remove_worktree,
    run_attempt,
    write_opencode_config,
)

DEFAULT_CONFIG_PATHS = (
    Path("conductor.toml"),
    Path.home() / ".config" / "conductor" / "conductor.toml",
)


def find_config(explicit: Path | None) -> Path:
    candidates = [explicit] if explicit else list(DEFAULT_CONFIG_PATHS)
    for path in candidates:
        if path and path.exists():
            return path
    raise ConfigError(
        "no conductor.toml found (looked in: " + ", ".join(map(str, candidates)) + ")"
    )


def validate(args: argparse.Namespace) -> int:
    plan = Plan.load(args.plan)
    print(f"ok: {len(plan.steps)} steps")
    return 0


async def execute_plan(
    repo: Path, plan: Plan, profile: Profile, log: RunLog, extra_args: list[str]
) -> dict[str, StepResult]:
    base = git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    run_name = log.directory.name
    worktrees = repo / ".conductor" / "worktrees" / run_name

    async def attempt(step: Step, number: int, model: str, prompt: str) -> AttemptOutput:
        branch = f"conductor/{run_name}/{step.id}-{number}"
        path = worktrees / f"{step.id}-{number}"
        create_worktree(repo, path, branch, base)
        write_opencode_config(path, opencode_config(profile))
        print(f"[{step.id}] attempt {number} on {model}", flush=True)
        return await run_attempt(
            path, base, model, prompt, extra_args, f"conductor: {step.id} attempt {number}"
        )

    def judge(spec: str, diff: str) -> reviewer.Verdict:
        return reviewer.review(profile, spec, diff)

    async def execute(step: Step) -> StepResult:
        result = await run_step(step, profile, attempt, judge, log.attempt, goal=plan.goal)
        print(f"[{step.id}] {result.status}: {result.detail}", flush=True)
        numbers = [a["attempt"] for a in result.attempts]
        for number in numbers[:-1]:
            discard(step, number)
        if result.status == APPROVED and numbers:
            branch = f"conductor/{run_name}/{step.id}-{numbers[-1]}"
            problem = merge_branch(repo, branch, into=base)
            if problem:
                result.status = CONFLICT
                result.detail = f"{problem} (branch {branch} kept)"
            else:
                discard(step, numbers[-1])
        return result

    def discard(step: Step, number: int) -> None:
        remove_worktree(repo, worktrees / f"{step.id}-{number}")
        git(repo, "branch", "-D", f"conductor/{run_name}/{step.id}-{number}")

    return await run_plan(plan, profile.max_parallel, execute)


def run(args: argparse.Namespace) -> int:
    repo = args.repo.resolve()
    config = Config.load(find_config(args.config))
    profile = config.profile(args.privacy)
    plan = Plan.load(args.plan)
    exclude_from_git(repo, ".conductor/")
    if git(repo, "status", "--porcelain").strip():
        print("error: repository has uncommitted changes; commit or stash them first")
        return 2
    log = RunLog.create(repo, plan, profile.name)
    print(f"run {log.directory.name}: {len(plan.steps)} steps, privacy {profile.name}")
    results = asyncio.run(execute_plan(repo, plan, profile, log, args.opencode_arg))
    log.finish(results)
    summary = {
        step_id: {"status": r.status, "detail": r.detail, "attempts": len(r.attempts)}
        for step_id, r in results.items()
    }
    print(json.dumps({"run": str(log.directory), "steps": summary}, indent=2))
    return 0 if all(r.status == APPROVED for r in results.values()) else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="conductor")
    commands = parser.add_subparsers(dest="command", required=True)

    check = commands.add_parser("validate", help="check a plan.json")
    check.add_argument("plan", type=Path)
    check.set_defaults(handler=validate)

    execute = commands.add_parser("run", help="execute a plan.json")
    execute.add_argument("plan", type=Path)
    execute.add_argument("--privacy", choices=None, help="profile name from conductor.toml")
    execute.add_argument("--config", type=Path, help="path to conductor.toml")
    execute.add_argument("--repo", type=Path, default=Path("."), help="repository to work in")
    execute.add_argument(
        "--opencode-arg",
        action="append",
        default=[],
        help="extra argument passed to every `opencode run` (repeatable)",
    )
    execute.set_defaults(handler=run)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        code: int = args.handler(args)
        return code
    except (PlanError, ConfigError, reviewer.ReviewerError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
