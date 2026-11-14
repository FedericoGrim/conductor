from __future__ import annotations

import asyncio
import json
import os
import subprocess
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from conductor.commits import choose_commit_message
from conductor.config import Profile
from conductor.errors import ModelError

EVENT_LINE_LIMIT = 64 * 1024 * 1024
STOP_GRACE_SECONDS = 10
HOOK_OUTPUT_LIMIT = 4000

StopCondition = Callable[[str], bool]
Runner = Callable[[list[str], Path, StopCondition], Awaitable[tuple[int, str, str]]]
Events = list[dict[str, Any]]
EventCheck = Callable[[dict[str, Any]], bool]


@dataclass(frozen=True)
class Harness:
    """The command-line agent that runs a worker, and how to read its event stream."""

    name: str
    prepare: Callable[[Path, Profile], None]
    command: Callable[[str, str, list[str]], list[str]]
    session_id: Callable[[Events], str | None]
    is_retry: EventCheck
    cost: Callable[[Events], float]
    error: Callable[[Events, int, str], ModelError | None]
    final_text: Callable[[Events], str]
    subscription_cost: Callable[[Events], float] | None = None


@dataclass
class AttemptOutput:
    exit_code: int
    session_id: str | None
    events: list[dict[str, Any]]
    diff: str
    stderr: str = ""
    command: list[str] = field(default_factory=list)
    cost: float = 0.0
    error: ModelError | None = None
    final_text: str = ""
    subscription_cost: float = 0.0
    commit_rejection: str | None = None


def git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return completed.stdout


def create_worktree(repo: Path, path: Path, branch: str, base: str) -> None:
    git(repo, "worktree", "add", "-q", "-b", branch, str(path), base)


def remove_worktree(repo: Path, path: Path) -> None:
    git(repo, "worktree", "remove", "--force", str(path))


def exclude_from_git(repo: Path, pattern: str) -> None:
    common_dir = Path(git(repo, "rev-parse", "--git-common-dir").strip())
    if not common_dir.is_absolute():
        common_dir = repo / common_dir
    exclude = common_dir / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    existing = exclude.read_text() if exclude.exists() else ""
    if pattern not in existing.splitlines():
        exclude.write_text(existing.rstrip("\n") + f"\n{pattern}\n")


def parse_events(stdout: str) -> Events:
    events: Events = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def commit_work(worktree: Path, message: str) -> str | None:
    """Commit every change; return the hooks' output when they reject the commit, else None."""
    rejection: str | None = None
    # A hook may fix the files (formatters) and still fail: stage its fixes and try once more.
    for _ in range(2):
        git(worktree, "add", "-A")
        if not git(worktree, "status", "--porcelain").strip():
            return None
        completed = subprocess.run(
            [
                "git",
                "-c",
                "user.name=conductor",
                "-c",
                "user.email=conductor@local",
                "commit",
                "-q",
                "-m",
                message,
            ],
            cwd=worktree,
            capture_output=True,
            text=True,
        )
        if completed.returncode == 0:
            return None
        rejection = (completed.stdout + completed.stderr).strip()[-HOOK_OUTPUT_LIMIT:]
    return rejection


def diff_against(worktree: Path, base: str) -> str:
    return git(worktree, "diff", f"{base}...HEAD")


def retry_limit(
    transient_attempts: int, is_retry: Callable[[dict[str, Any]], bool]
) -> StopCondition:
    retries = 0

    def should_stop(line: str) -> bool:
        nonlocal retries
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return False
        if isinstance(event, dict) and is_retry(event):
            retries += 1
        return retries > transient_attempts

    return should_stop


async def stop_process(process: asyncio.subprocess.Process) -> None:
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), STOP_GRACE_SECONDS)
    except TimeoutError:
        process.kill()
        await process.wait()


async def subprocess_runner(
    cmd: list[str], cwd: Path, should_stop: StopCondition
) -> tuple[int, str, str]:
    # OpenCode resolves its project root from $PWD, not from the process cwd.
    process = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        env={**os.environ, "PWD": str(cwd)},
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        limit=EVENT_LINE_LIMIT,
    )
    assert process.stdout is not None and process.stderr is not None
    stderr_task = asyncio.create_task(process.stderr.read())
    lines: list[str] = []
    while raw := await process.stdout.readline():
        line = raw.decode(errors="replace")
        lines.append(line)
        if should_stop(line.rstrip("\n")):
            await stop_process(process)
            break
    await process.wait()
    stderr = await stderr_task
    return process.returncode or 0, "".join(lines), stderr.decode(errors="replace")


async def run_attempt(
    worktree: Path,
    base: str,
    model: str,
    prompt: str,
    extra_args: list[str],
    transient_attempts: int,
    harness: Harness,
    runner: Runner = subprocess_runner,
    *,
    step_id: str | None = None,
    number: int | None = None,
    planned: str | None = None,
    commit_message: str | None = None,
) -> AttemptOutput:
    command = harness.command(model, prompt, extra_args)
    should_stop = retry_limit(transient_attempts, harness.is_retry)
    exit_code, stdout, stderr = await runner(command, worktree, should_stop)
    events = parse_events(stdout)
    worker_text = harness.final_text(events)
    if commit_message is None:
        assert step_id is not None and number is not None
        commit_message = choose_commit_message(step_id, number, model, worker_text, planned)
    commit_rejection = commit_work(worktree, commit_message)
    return AttemptOutput(
        exit_code=exit_code,
        session_id=harness.session_id(events),
        events=events,
        diff=diff_against(worktree, base),
        stderr=stderr,
        command=command,
        cost=harness.cost(events),
        error=harness.error(events, exit_code, stderr),
        final_text=worker_text,
        subscription_cost=harness.subscription_cost(events) if harness.subscription_cost else 0.0,
        commit_rejection=commit_rejection,
    )
