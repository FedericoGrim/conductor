from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from conductor import billing, reviewer, settings, setup_tui
from conductor.config import Config, ConfigError, Profile
from conductor.escalation import RunState, run_step
from conductor.harness import harness_for
from conductor.log import RunLog
from conductor.merge import merge_branch
from conductor.plan import Plan, PlanError, Step
from conductor.scheduler import APPROVED, CONFLICT, StepResult, run_plan
from conductor.verify import CheckResult, run_checks
from conductor.worker import (
    AttemptOutput,
    create_worktree,
    exclude_from_git,
    git,
    remove_worktree,
    run_attempt,
)

RULES_FILE_LIMIT = 20_000
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
    if args.config is None and not any(path.exists() for path in DEFAULT_CONFIG_PATHS):
        return 0
    config = Config.load(find_config(args.config))
    for profile in config.profiles.values():
        for warning in profile.single_provider_warnings():
            print(f"warning: {warning}")
    return 0


def domain_rules(repo: Path, plan: Plan) -> tuple[str, ...]:
    if plan.rules_file is None:
        return plan.rules
    path = repo / plan.rules_file
    if not path.is_file():
        raise PlanError(f"rules_file '{plan.rules_file}' does not exist in {repo}")
    text = path.read_text(errors="replace").strip()
    if len(text) > RULES_FILE_LIMIT:
        raise PlanError(
            f"rules_file '{plan.rules_file}' is longer than {RULES_FILE_LIMIT} characters"
        )
    return (*plan.rules, text) if text else plan.rules


async def execute_plan(
    repo: Path,
    plan: Plan,
    profile: Profile,
    log: RunLog,
    extra_args: list[str],
    rules: tuple[str, ...] = (),
) -> dict[str, StepResult]:
    base = git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    run_name = log.directory.name
    worktrees = repo / ".conductor" / "worktrees" / run_name
    state = RunState()

    async def attempt(step: Step, number: int, model: str, prompt: str) -> AttemptOutput:
        branch = f"conductor/{run_name}/{step.id}-{number}"
        path = worktrees / f"{step.id}-{number}"
        create_worktree(repo, path, branch, base)
        harness = harness_for(profile, model)
        harness.prepare(path, profile)
        print(f"[{step.id}] attempt {number} on {model}", flush=True)
        return await run_attempt(
            path,
            base,
            model,
            prompt,
            extra_args,
            f"conductor: {step.id} attempt {number}",
            transient_attempts=profile.transient_attempts,
            harness=harness,
        )

    def judge(model: str, spec: str, diff: str, checks: list[CheckResult]) -> reviewer.Verdict:
        return reviewer.review(profile, model, spec, diff, rules=rules, checks=checks)

    async def check(step: Step, number: int) -> list[CheckResult]:
        path = worktrees / f"{step.id}-{number}"
        return await run_checks(plan.verify_for(step), path, repo, plan.verify_timeout)

    async def execute(step: Step) -> StepResult:
        result = await run_step(
            step, profile, attempt, judge, log.attempt, goal=plan.goal, state=state, check=check
        )
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
    rules = domain_rules(repo, plan)
    exclude_from_git(repo, ".conductor/")
    if git(repo, "status", "--porcelain").strip():
        print("error: repository has uncommitted changes; commit or stash them first")
        return 2
    log = RunLog.create(repo, plan, profile.name)
    print(f"run {log.directory.name}: {len(plan.steps)} steps, privacy {profile.name}")
    results = asyncio.run(execute_plan(repo, plan, profile, log, args.opencode_arg, rules))
    log.finish(results)
    try:
        billing.record_run(
            project_root(repo), ",".join(profile.providers), log.directory.name, log.run
        )
    except OSError as error:
        print(f"warning: could not record the run in the ledger: {error}", file=sys.stderr)
    summary = {
        step_id: {"status": r.status, "detail": r.detail, "attempts": len(r.attempts)}
        for step_id, r in results.items()
    }
    print(json.dumps({"run": str(log.directory), "steps": summary}, indent=2))
    return 0 if all(r.status == APPROVED for r in results.values()) else 1


class NotARepositoryError(ValueError):
    pass


def project_root(directory: Path) -> Path:
    try:
        return Path(git(directory, "rev-parse", "--show-toplevel").strip())
    except subprocess.CalledProcessError as error:
        raise NotARepositoryError(f"{directory} is not a git repository") from error


def money(amount: float, currency: str = "USD") -> str:
    return f"{amount:.4f} {currency}"


def show_balances(args: argparse.Namespace) -> int:
    config = Config.load(find_config(args.config))
    for balance in billing.balances(config.profiles.values()):
        columns = [f"{balance.account:<24}"]
        if balance.remaining is not None:
            columns.append(f"remaining {money(balance.remaining, balance.currency)}")
        if balance.used is not None:
            columns.append(f"used {money(balance.used, balance.currency)}")
        if balance.note:
            columns.append(f"({balance.note})")
        print("  ".join(columns))
    return 0


def show_project_spend(args: argparse.Namespace) -> int:
    project = project_root(args.repo.resolve())
    runs = billing.project_runs(project)
    print(f"project {project.name} ({project})")
    if not runs:
        print("no runs recorded")
        return 0
    for run in runs:
        print(f"{run.run:<24}  {'unknown' if run.cost is None else money(run.cost)}")
    print(f"{'total':<24}  {money(sum(run.cost or 0.0 for run in runs))}")
    unknown = sum(run.cost is None for run in runs)
    if unknown:
        print(f"{unknown} run{'s' if unknown > 1 else ''} without a recorded cost")
    return 0


def show_projects_spend(args: argparse.Namespace) -> int:
    since = datetime.now(UTC) - timedelta(days=args.days)
    spend = billing.spend_by_project(billing.read_ledger(), since)
    if not spend:
        print(f"no runs recorded in the last {args.days} days")
        return 0
    total = sum(spend.values())
    print(f"last {args.days} days")
    for project, cost in sorted(spend.items(), key=lambda item: item[1], reverse=True):
        share = f"{cost / total:.0%}" if total else "-"
        print(f"{Path(project).name:<24}  {money(cost)}  {share:>4}  {project}")
    print(f"{'total':<24}  {money(total)}")
    return 0


def config_path(explicit: Path | None) -> Path:
    return explicit or next(
        (candidate for candidate in DEFAULT_CONFIG_PATHS if candidate.exists()),
        DEFAULT_CONFIG_PATHS[1],
    )


def setup_config(args: argparse.Namespace) -> int:
    return setup_tui.run(config_path(args.config))


def show_config_path(args: argparse.Namespace) -> int:
    print(config_path(args.config))
    return 0


def export_config(args: argparse.Namespace) -> int:
    source = find_config(args.config)
    target = args.file or Path("conductor-settings.toml")
    settings.export_settings(Config.load(source), target, version())
    print(f"exported {source} to {target}")
    return 0


def version() -> str:
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as package_version

    try:
        return package_version("conductor")
    except PackageNotFoundError:
        return "unknown"


def import_config(args: argparse.Namespace) -> int:
    result = settings.import_settings(args.file, config_path(args.config))
    print(f"imported profiles {', '.join(result.profiles)} into {result.path}")
    if result.backup:
        print(f"previous file kept as {result.backup}")
    if result.missing_keys:
        print("missing API keys (export the variable or run `conductor setup`):")
        for name in result.missing_keys:
            print(f"  {name}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="conductor")
    commands = parser.add_subparsers(dest="command", required=True)

    check = commands.add_parser("validate", help="check a plan.json")
    check.add_argument("plan", type=Path)
    check.add_argument("--config", type=Path, help="path to conductor.toml")
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

    setup = commands.add_parser("setup", help="create or edit conductor.toml in a terminal UI")
    setup.add_argument("--config", type=Path, help="path to conductor.toml")
    setup.set_defaults(handler=setup_config)

    config = commands.add_parser("config", help="inspect, export and import the settings")
    actions = config.add_subparsers(dest="action", required=True)

    path = actions.add_parser("path", help="print the configuration file in use")
    path.add_argument("--config", type=Path, help="path to conductor.toml")
    path.set_defaults(handler=show_config_path)

    export = actions.add_parser("export", help="write the settings to a file")
    export.add_argument("file", nargs="?", type=Path, help="target file")
    export.add_argument("--config", type=Path, help="path to conductor.toml")
    export.set_defaults(handler=export_config)

    load = actions.add_parser("import", help="read the settings from a file")
    load.add_argument("file", type=Path, help="file written by `config export`")
    load.add_argument("--config", type=Path, help="path to conductor.toml")
    load.set_defaults(handler=import_config)

    balance = commands.add_parser("billing", help="credits left on every configured provider")
    balance.add_argument("--config", type=Path, help="path to conductor.toml")
    balance.set_defaults(handler=show_balances)
    reports = balance.add_subparsers(dest="report")

    project = reports.add_parser("project", help="spend of this repository, run by run")
    project.add_argument("--repo", type=Path, default=Path("."), help="repository to report on")
    project.set_defaults(handler=show_project_spend)

    projects = reports.add_parser("projects", help="spend of the last days, split by project")
    projects.add_argument("--days", type=int, default=30, help="length of the period in days")
    projects.set_defaults(handler=show_projects_spend)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        code: int = args.handler(args)
        return code
    except (
        PlanError,
        ConfigError,
        NotARepositoryError,
        settings.SettingsError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
