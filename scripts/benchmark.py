"""Run benchmark tasks with Conductor and score them with hidden tests (#65).

Every job (profile × task × repetition) gets a throwaway copy of this
repository at the task's base commit, runs a single-step plan on it through
Conductor on one profile (difficulty 5: every level is the same model, so
exactly one attempt), then checks the worker's commit with the task's hidden
tests, taken from the solution commit of this repository. One JSON record per
job is appended to <out>/results.jsonl; the copies are deleted afterwards.

Usage: python scripts/benchmark.py run [--profiles bench-a,bench-b]
       [--tasks id1,id2] [--repeat 3] [--budget 12] [--parallel 4]
       [--out DIR] [--config benchmarks/profiles.toml]
       [--conductor PATH] [--keep]
       python scripts/benchmark.py report <results dir or results.jsonl>
"""

from __future__ import annotations

import argparse
import io
import json
import shutil
import subprocess
import sys
import tarfile
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from conductor.cli import money
from conductor.config import Config, ConfigError

VERIFY = (
    "$CONDUCTOR_REPO/.venv/bin/python -m pytest -q",
    "$CONDUCTOR_REPO/.venv/bin/ruff check conductor tests",
    "$CONDUCTOR_REPO/.venv/bin/mypy --strict conductor tests",
)
BASE_COMMIT = "chore: benchmark base"


class BenchmarkError(ValueError):
    pass


@dataclass(frozen=True)
class Task:
    id: str
    title: str
    difficulty: int
    base: str
    solution: str
    hidden_tests: tuple[str, ...]
    files: tuple[str, ...]
    spec: str


def read_json(path: Path, what: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text())
    except OSError as error:
        raise BenchmarkError(f"cannot read {what} '{path}': {error.strerror or error}") from error
    except json.JSONDecodeError as error:
        raise BenchmarkError(f"{what} '{path}' is not valid JSON: {error}") from error
    if not isinstance(data, dict):
        raise BenchmarkError(f"{what} '{path}' does not contain a JSON object")
    return data


def load_tasks(directory: Path, ids: list[str] | None) -> list[Task]:
    if not directory.is_dir():
        raise BenchmarkError(f"tasks directory '{directory}' does not exist")
    tasks: dict[str, Task] = {}
    for path in sorted(directory.glob("*.json")):
        data = read_json(path, "task")
        try:
            task = Task(
                id=str(data["id"]),
                title=str(data["title"]),
                difficulty=int(data["difficulty"]),
                base=str(data["base"]),
                solution=str(data["solution"]),
                hidden_tests=tuple(str(p) for p in data.get("hidden_tests", [])),
                files=tuple(str(f) for f in data.get("files", [])),
                spec=str(data["spec"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise BenchmarkError(f"task '{path}' is invalid: {error}") from error
        if not 1 <= task.difficulty <= 5:
            raise BenchmarkError(f"task '{path}': difficulty must be between 1 and 5")
        if task.id in tasks:
            raise BenchmarkError(f"duplicate task id '{task.id}'")
        tasks[task.id] = task
    if ids is not None:
        unknown = [task_id for task_id in ids if task_id not in tasks]
        if unknown:
            raise BenchmarkError(
                f"unknown task ids: {', '.join(unknown)} (known: {', '.join(sorted(tasks))})"
            )
        return sorted((tasks[task_id] for task_id in ids), key=lambda task: task.id)
    return sorted(tasks.values(), key=lambda task: task.id)


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    if check and result.returncode != 0:
        message = result.stderr.decode(errors="replace").strip() or f"exit {result.returncode}"
        raise BenchmarkError(f"git {' '.join(args)} in {repo}: {message}")
    return result


def prepare_copy(repo: Path, task: Task, destination: Path) -> None:
    """Extract the task's base commit into a fresh one-commit repository."""
    destination.mkdir(parents=True)
    archive = subprocess.run(
        ["git", "-C", str(repo), "archive", "--format=tar", task.base], capture_output=True
    )
    if archive.returncode != 0:
        message = archive.stderr.decode(errors="replace").strip() or f"exit {archive.returncode}"
        raise BenchmarkError(f"git archive {task.base}: {message}")
    with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r") as tar:
        tar.extractall(destination, filter="data")
    git(destination, "init", "-b", "main")
    git(destination, "add", "-A")
    git(
        destination,
        "-c",
        "user.name=benchmark",
        "-c",
        "user.email=benchmark@local",
        "commit",
        "-m",
        BASE_COMMIT,
        "--no-verify",
    )
    exclude = destination / ".git" / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    with exclude.open("a") as stream:
        stream.write(".venv\n")
    (destination / ".venv").symlink_to(repo / ".venv", target_is_directory=True)
    pre_commit = shutil.which("pre-commit")
    if pre_commit is None:
        raise BenchmarkError("pre-commit is not on PATH; needed to install the copy's git hooks")
    installed = subprocess.run(
        [pre_commit, "install", "--hook-type", "pre-commit", "--hook-type", "commit-msg"],
        cwd=destination,
        capture_output=True,
    )
    if installed.returncode != 0:
        message = installed.stderr.decode(errors="replace").strip()
        raise BenchmarkError(f"pre-commit install in {destination} failed: {message}")


def plan_for(task: Task) -> dict[str, Any]:
    """A single-step plan: difficulty 5, so every level is the same model."""
    return {
        "goal": task.title,
        "verify": list(VERIFY),
        "steps": [
            {
                "id": task.id,
                "title": task.title,
                "spec": task.spec,
                "files": list(task.files),
                "difficulty": 5,
                "depends_on": [],
            }
        ],
    }


def run_conductor(
    conductor: str, plan: Path, config: Path, profile: str, copy: Path, log: Path
) -> int:
    """Run the plan on the copy; a non-zero exit means the step failed, not the benchmark."""
    command = [
        conductor,
        "run",
        str(plan),
        "--config",
        str(config),
        "--privacy",
        profile,
        "--repo",
        str(copy),
    ]
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w") as stream:
        return subprocess.call(command, stdout=stream, stderr=stream)


def latest_run(copy: Path) -> Path | None:
    runs = copy / ".conductor" / "runs"
    if not runs.is_dir():
        return None
    directories = [entry for entry in runs.iterdir() if entry.is_dir()]
    return max(directories, key=lambda entry: entry.name) if directories else None


def attempt_commit(
    copy: Path, run_dir: Path, step_id: str, status: str, attempts: int
) -> str | None:
    """The commit holding the worker's work: the merged HEAD, the kept branch, or None."""
    if status == "approved":
        return git(copy, "rev-parse", "HEAD").stdout.decode().strip()
    branch = f"conductor/{run_dir.name}/{step_id}-{attempts}"
    listed = git(copy, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}", check=False)
    return branch if listed.returncode == 0 else None


def check_hidden(
    repo: Path, copy: Path, commit: str, task: Task, workdir: Path, timeout: float = 600
) -> bool:
    """Run the task's hidden tests from the solution commit on the worker's commit."""
    workdir.parent.mkdir(parents=True, exist_ok=True)
    git(copy, "worktree", "add", "--detach", str(workdir), commit)
    try:
        tests = workdir / "tests"
        tests.mkdir(parents=True, exist_ok=True)
        paths: list[str] = []
        for source in task.hidden_tests:
            content = git(repo, "show", f"{task.solution}:{source}").stdout
            name = f"hidden_{Path(source).name}"
            (tests / name).write_bytes(content)
            paths.append(str(tests / name))
        command = [
            str(repo / ".venv" / "bin" / "python"),
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            *paths,
        ]
        try:
            checked = subprocess.run(command, cwd=workdir, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return False
        return checked.returncode == 0
    finally:
        git(copy, "worktree", "remove", "--force", str(workdir))


def classify(status: str, review_ok: bool | None, hidden_ok: bool | None) -> dict[str, bool]:
    solved = status == "approved" and hidden_ok is True
    return {
        "solved": solved,
        "false_rejection": review_ok is False and hidden_ok is True,
        "false_approval": status == "approved" and hidden_ok is False,
    }


def read_run(run_dir: Path | None) -> dict[str, Any] | None:
    if run_dir is None:
        return None
    path = run_dir / "run.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def elapsed_seconds(run: dict[str, Any]) -> float | None:
    started, finished = run.get("started_at"), run.get("finished_at")
    if not isinstance(started, str) or not isinstance(finished, str):
        return None
    try:
        return (datetime.fromisoformat(finished) - datetime.fromisoformat(started)).total_seconds()
    except ValueError:
        return None


def last_review(run_dir: Path | None, step_id: str, attempts: int) -> dict[str, Any] | None:
    if run_dir is None or attempts < 1:
        return None
    path = run_dir / f"step-{step_id}" / f"attempt-{attempts}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    review = data.get("review") if isinstance(data, dict) else None
    if not isinstance(review, dict):
        return None
    return {
        "ok": review.get("ok"),
        "category": review.get("category"),
        "suspicious": review.get("suspicious"),
    }


def job_result(
    profile: str,
    model: str,
    task: Task,
    repetition: int,
    run_dir: Path | None,
    hidden_ok: bool | None,
) -> dict[str, Any]:
    """One record for one job, read from the run Conductor left in the copy."""
    run = read_run(run_dir) or {}
    step = (run.get("steps") or {}).get(task.id) or {}
    status = str(step.get("status", "no-run"))
    attempts = int(step.get("attempts", 0))
    cost = run.get("cost")
    if isinstance(cost, bool) or not isinstance(cost, int | float):
        cost = 0.0
    review = last_review(run_dir, task.id, attempts)
    review_ok = None if review is None else bool(review.get("ok"))
    return {
        "profile": profile,
        "model": model,
        "task": task.id,
        "difficulty": task.difficulty,
        "repetition": repetition,
        "status": status,
        "attempts": attempts,
        "cost": cost,
        "seconds": elapsed_seconds(run),
        "review": review,
        "hidden_ok": hidden_ok,
        **classify(status, review_ok, hidden_ok),
    }


def step_state(run_dir: Path | None, step_id: str) -> tuple[str, int]:
    run = read_run(run_dir) or {}
    step = (run.get("steps") or {}).get(step_id) or {}
    return str(step.get("status", "no-run")), int(step.get("attempts", 0))


def cost_of(record: dict[str, Any]) -> float:
    cost = record.get("cost")
    if isinstance(cost, bool) or not isinstance(cost, int | float):
        return 0.0
    return float(cost)


def seconds_of(record: dict[str, Any]) -> float | None:
    seconds = record.get("seconds")
    if isinstance(seconds, bool) or not isinstance(seconds, int | float):
        return None
    return float(seconds)


def review_of(record: dict[str, Any]) -> dict[str, Any] | None:
    review = record.get("review")
    return review if isinstance(review, dict) else None


def is_error(record: dict[str, Any]) -> bool:
    """Lost to the provider or the harness, not to the model."""
    status = str(record.get("status", "no-run"))
    return status in ("unavailable", "no-run") or (status == "failed" and review_of(record) is None)


def solved_count(records: list[dict[str, Any]]) -> int:
    return sum(1 for record in records if record.get("solved") is True)


def total_cost(records: list[dict[str, Any]]) -> float:
    return sum(cost_of(record) for record in records)


def separator(columns: int) -> str:
    return "|" + "---|" * columns


def model_header(difficulties: list[int]) -> str:
    cells = "".join(f" | D{difficulty}" for difficulty in difficulties)
    return (
        f"| Model | Solved{cells}"
        " | Cost | $/solved | Mean time | Rejections | False rej. | False appr. | Suspicious |"
    )


def per_difficulty(group: list[dict[str, Any]], difficulty: int) -> str:
    jobs = [record for record in group if int(record.get("difficulty", 0)) == difficulty]
    return f"{solved_count(jobs)}/{len(jobs)}" if jobs else "-"


def model_row(group: list[dict[str, Any]], difficulties: list[int]) -> str:
    jobs, solved, cost = len(group), solved_count(group), total_cost(group)
    cells = "".join(f" | {per_difficulty(group, difficulty)}" for difficulty in difficulties)
    times = [second for record in group if (second := seconds_of(record)) is not None]
    mean = f"{sum(times) / len(times):.1f}" if times else "-"
    per_solved = f"{cost / solved:.4f}" if solved else "-"
    reviews = [review_of(record) for record in group]
    rejected = [review for review in reviews if review is not None and review.get("ok") is False]
    suspicious = sum(1 for review in rejected if review.get("suspicious") is True)
    false_rejections = sum(1 for record in group if record.get("false_rejection") is True)
    false_approvals = sum(1 for record in group if record.get("false_approval") is True)
    model = str(group[0].get("model", ""))
    return (
        f"| {model} | {solved}/{jobs}{cells} | {cost:.4f} | {per_solved} | {mean} | "
        f"{len(rejected)} | {false_rejections} | {false_approvals} | {suspicious} |"
    )


def task_header(models: list[str]) -> str:
    cells = "".join(f" | {model}" for model in models)
    return f"| Task | Difficulty{cells} |"


def per_task(group: list[dict[str, Any]], task_id: str) -> str:
    jobs = [record for record in group if str(record.get("task", "")) == task_id]
    return f"{solved_count(jobs)}/{len(jobs)}" if jobs else "-"


def task_row(
    task_id: str,
    records: list[dict[str, Any]],
    ordered: list[tuple[tuple[str, str], list[dict[str, Any]]]],
) -> str:
    same = [record for record in records if str(record.get("task", "")) == task_id]
    difficulty = int(same[0].get("difficulty", 0))
    cells = "".join(f" | {per_task(group, task_id)}" for _, group in ordered)
    return f"| {task_id} | {difficulty}{cells} |"


def total_line(records: list[dict[str, Any]]) -> str:
    errors = sum(1 for record in records if is_error(record))
    return f"Total: {len(records)} jobs, ${total_cost(records):.4f}, {errors} errors"


def report(records: list[dict[str, Any]]) -> str:
    """The Markdown report for the records `run` wrote: per model, per task, totals."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for record in records:
        key = (str(record.get("profile", "")), str(record.get("model", "")))
        groups.setdefault(key, []).append(record)
    ordered = sorted(groups.items(), key=lambda item: (-solved_count(item[1]), total_cost(item[1])))
    difficulties = sorted({int(record.get("difficulty", 0)) for record in records})
    lines = [model_header(difficulties), separator(3 + len(difficulties) + 6)]
    for _, group in ordered:
        lines.append(model_row(group, difficulties))
    lines.append("")
    models = [key[1] for key, _ in ordered]
    lines.append(task_header(models))
    lines.append(separator(2 + len(models)))
    tasks = sorted({str(record.get("task", "")) for record in records})
    for task_id in tasks:
        lines.append(task_row(task_id, records, ordered))
    lines.append("")
    lines.append(total_line(records))
    return "\n".join(lines) + "\n"


def read_records(path: Path) -> list[dict[str, Any]]:
    try:
        text = path.read_text()
    except OSError as error:
        raise BenchmarkError(f"cannot read results '{path}': {error.strerror or error}") from error
    records: list[dict[str, Any]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise BenchmarkError(f"{path}:{number} is not valid JSON: {error}") from error
        if not isinstance(record, dict):
            raise BenchmarkError(f"{path}:{number} does not contain a JSON object")
        records.append(record)
    return records


def run_report(args: argparse.Namespace) -> int:
    path: Path = args.source
    if path.is_dir():
        path = path / "results.jsonl"
    print(report(read_records(path)), end="")
    return 0


def split_list(value: str | None) -> list[str] | None:
    if value is None:
        return None
    items = [item.strip() for item in value.split(",")]
    return [item for item in items if item] or None


def chosen_profiles(config: Config, requested: str | None) -> list[str]:
    names = split_list(requested)
    if names is None:
        return list(config.profiles)
    unknown = [name for name in names if name not in config.profiles]
    if unknown:
        raise BenchmarkError(
            f"unknown profiles: {', '.join(unknown)} (known: {', '.join(config.profiles)})"
        )
    return names


def run_benchmark(args: argparse.Namespace) -> int:
    repo = Path(__file__).resolve().parent.parent
    config_path = args.config if args.config is not None else repo / "benchmarks" / "profiles.toml"
    config = Config.load(config_path)
    profiles = chosen_profiles(config, args.profiles)
    tasks = load_tasks(repo / "benchmarks" / "tasks", split_list(args.tasks))
    if args.repeat < 1:
        raise BenchmarkError("--repeat must be at least 1")
    if args.parallel < 1:
        raise BenchmarkError("--parallel must be at least 1")
    conductor = args.conductor or shutil.which("conductor")
    if conductor is None:
        raise BenchmarkError("conductor is not on PATH; pass --conductor PATH")
    out = args.out if args.out is not None else repo / "benchmarks" / "results" / stamp()
    out.mkdir(parents=True, exist_ok=True)

    lock = threading.Lock()
    results_path = out / "results.jsonl"
    spent = [0.0]
    skipped = [0]
    failures: list[str] = []

    def job(profile: str, task: Task, repetition: int) -> None:
        name = f"{profile}-{task.id}-{repetition}"
        work = out / "work" / profile / f"{task.id}-{repetition}"
        copy = work / "copy"
        with lock:
            if spent[0] >= args.budget:
                skipped[0] += 1
                return
        prepare_copy(repo, task, copy)
        plan_path = out / "plans" / f"{name}.json"
        plan_path.parent.mkdir(parents=True, exist_ok=True)
        plan_path.write_text(json.dumps(plan_for(task), indent=2) + "\n")
        run_conductor(
            conductor, plan_path, config_path, profile, copy, out / "logs" / f"{name}.log"
        )
        run_dir = latest_run(copy)
        status, attempts = step_state(run_dir, task.id)
        commit = (
            attempt_commit(copy, run_dir, task.id, status, attempts)
            if run_dir is not None
            else None
        )
        hidden_ok = (
            None if commit is None else check_hidden(repo, copy, commit, task, work / "check")
        )
        model = config.profiles[profile].tiers[0][0]
        record = job_result(profile, model, task, repetition, run_dir, hidden_ok)
        with lock:
            with results_path.open("a") as stream:
                stream.write(json.dumps(record) + "\n")
            spent[0] += float(record["cost"])
            print(
                f"{name}: {record['status']}  solved={record['solved']}  "
                f"cost={money(float(record['cost']))}",
                flush=True,
            )
        if not args.keep:
            shutil.rmtree(copy, ignore_errors=True)

    jobs = [
        (profile, task, repetition)
        for profile in profiles
        for task in tasks
        for repetition in range(1, args.repeat + 1)
    ]
    with ThreadPoolExecutor(max_workers=args.parallel) as pool:
        futures = [
            pool.submit(job, profile, task, repetition) for profile, task, repetition in jobs
        ]
        for future in futures:
            try:
                future.result()
            except (BenchmarkError, ConfigError, OSError) as error:
                failures.append(str(error))
    if skipped[0]:
        print(
            f"{skipped[0]} jobs skipped: the budget of {money(args.budget)} was reached", flush=True
        )
    for failure in failures:
        print(f"error: {failure}", file=sys.stderr)
    return 2 if failures else 0


def stamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%S")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="run benchmark tasks with Conductor and score them with hidden tests"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    runner = commands.add_parser("run", help="run every task on every profile")
    runner.add_argument("--profiles", help="comma-separated profile names (default: every profile)")
    runner.add_argument("--tasks", help="comma-separated task ids (default: every task)")
    runner.add_argument("--repeat", type=int, default=3, help="repetitions per profile and task")
    runner.add_argument("--budget", type=float, default=12.0, help="USD budget of the whole run")
    runner.add_argument("--parallel", type=int, default=4, help="jobs running at once")
    runner.add_argument(
        "--out", type=Path, help="output directory (default: benchmarks/results/<timestamp>)"
    )
    runner.add_argument(
        "--config", type=Path, help="path to the profiles (default: benchmarks/profiles.toml)"
    )
    runner.add_argument(
        "--conductor", help="path to the conductor executable (default: which conductor)"
    )
    runner.add_argument("--keep", action="store_true", help="keep the throwaway copies")
    runner.set_defaults(handler=run_benchmark)
    reporter = commands.add_parser(
        "report", help="print a Markdown report from a run's results.jsonl"
    )
    reporter.add_argument("source", type=Path, help="results directory or results.jsonl file")
    reporter.set_defaults(handler=run_report)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    handler: Callable[[argparse.Namespace], int] = args.handler
    try:
        return handler(args)
    except (BenchmarkError, ConfigError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
