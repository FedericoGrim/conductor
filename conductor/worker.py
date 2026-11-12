from __future__ import annotations

import asyncio
import json
import os
import subprocess
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from conductor.errors import (
    MODEL_UNSUITABLE,
    PROVIDER_UNUSABLE,
    TRANSIENT,
    UNCLASSIFIED,
    ModelError,
    mentions_context_limit,
)

OPENCODE_CONFIG_NAME = "opencode.json"
ERROR_EVENT = "error"
RETRY_EVENT = "retry"
EVENT_LINE_LIMIT = 64 * 1024 * 1024
STOP_GRACE_SECONDS = 10

StopCondition = Callable[[str], bool]
Runner = Callable[[list[str], Path, StopCondition], Awaitable[tuple[int, str, str]]]


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


def write_opencode_config(worktree: Path, config: dict[str, Any]) -> None:
    (worktree / OPENCODE_CONFIG_NAME).write_text(json.dumps(config, indent=2) + "\n")
    exclude_from_git(worktree, OPENCODE_CONFIG_NAME)


def build_command(model: str, prompt: str, extra_args: list[str]) -> list[str]:
    return [
        "opencode",
        "run",
        "--format",
        "json",
        "-m",
        model,
        "--auto",
        "--archived",
        *extra_args,
        prompt,
    ]


def parse_events(stdout: str) -> tuple[list[dict[str, Any]], str | None]:
    events: list[dict[str, Any]] = []
    session_id: str | None = None
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        events.append(event)
        session_id = session_id or event.get("sessionID")
    return events, session_id


def events_cost(events: list[dict[str, Any]]) -> float:
    total = 0.0
    for event in events:
        part = event.get("part")
        cost = part.get("cost") if isinstance(part, dict) else None
        if event.get("type") == "step_finish" and isinstance(cost, int | float):
            total += cost
    return total


ERROR_KINDS = {
    "provider.rate-limit": TRANSIENT,
    "provider.internal": TRANSIENT,
    "provider.transport": TRANSIENT,
    "provider.auth": PROVIDER_UNUSABLE,
    "provider.quota": PROVIDER_UNUSABLE,
    "provider.no-route": MODEL_UNSUITABLE,
}


def classify_opencode_error(error: dict[str, Any]) -> ModelError:
    error_type = str(error.get("type", ""))
    message = str(error.get("message", ""))
    kind = ERROR_KINDS.get(error_type, UNCLASSIFIED)
    if error_type == "provider.invalid-request" and mentions_context_limit(message):
        kind = MODEL_UNSUITABLE
    return ModelError.of(kind, error_type, message)


def attempt_error(events: list[dict[str, Any]], exit_code: int, stderr: str) -> ModelError | None:
    if exit_code == 0:
        return None
    reported = [
        event["error"]
        for event in events
        if event.get("type") in (ERROR_EVENT, RETRY_EVENT) and isinstance(event.get("error"), dict)
    ]
    if reported:
        return classify_opencode_error(reported[-1])
    return ModelError.of(UNCLASSIFIED, f"exit {exit_code}", stderr)


def commit_work(worktree: Path, message: str) -> bool:
    git(worktree, "add", "-A")
    if not git(worktree, "status", "--porcelain").strip():
        return False
    git(
        worktree,
        "-c",
        "user.name=conductor",
        "-c",
        "user.email=conductor@local",
        "commit",
        "-q",
        "-m",
        message,
    )
    return True


def diff_against(worktree: Path, base: str) -> str:
    return git(worktree, "diff", f"{base}...HEAD")


def retry_limit(transient_attempts: int) -> StopCondition:
    retries = 0

    def should_stop(line: str) -> bool:
        nonlocal retries
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return False
        if isinstance(event, dict) and event.get("type") == RETRY_EVENT:
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
    commit_message: str,
    transient_attempts: int,
    runner: Runner = subprocess_runner,
) -> AttemptOutput:
    command = build_command(model, prompt, extra_args)
    exit_code, stdout, stderr = await runner(command, worktree, retry_limit(transient_attempts))
    events, session_id = parse_events(stdout)
    commit_work(worktree, commit_message)
    return AttemptOutput(
        exit_code=exit_code,
        session_id=session_id,
        events=events,
        diff=diff_against(worktree, base),
        stderr=stderr,
        command=command,
        cost=events_cost(events),
        error=attempt_error(events, exit_code, stderr),
    )
