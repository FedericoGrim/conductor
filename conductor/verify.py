from __future__ import annotations

import asyncio
import os
import signal
import time
from dataclasses import dataclass
from pathlib import Path

OUTPUT_LIMIT = 4000


@dataclass(frozen=True)
class CheckResult:
    command: str
    exit_code: int | None
    output: str
    seconds: float
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


def failure_reason(result: CheckResult) -> str:
    outcome = (
        f"timed out after {result.seconds:.0f}s" if result.timed_out else f"exit {result.exit_code}"
    )
    return f"verification failed: `{result.command}` ({outcome})\n{result.output}".rstrip()


async def run_check(command: str, worktree: Path, repo: Path, timeout: float) -> CheckResult:
    started = time.monotonic()
    # Commands come from the plan, never from worker output; a new session lets a timeout stop
    # the whole process group (a test runner and its children), not only the shell.
    process = await asyncio.create_subprocess_exec(
        "sh",
        "-c",
        command,
        cwd=worktree,
        env={**os.environ, "PWD": str(worktree), "CONDUCTOR_REPO": str(repo)},
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        start_new_session=True,
    )
    try:
        output, _ = await asyncio.wait_for(process.communicate(), timeout)
    except TimeoutError:
        os.killpg(process.pid, signal.SIGKILL)
        await process.wait()
        return CheckResult(command, None, "", time.monotonic() - started, timed_out=True)
    return CheckResult(
        command,
        process.returncode,
        output.decode(errors="replace")[-OUTPUT_LIMIT:],
        time.monotonic() - started,
    )


async def run_checks(
    commands: tuple[str, ...], worktree: Path, repo: Path, timeout: float
) -> list[CheckResult]:
    results: list[CheckResult] = []
    for command in commands:
        result = await run_check(command, worktree, repo, timeout)
        results.append(result)
        if not result.ok:
            break
    return results
