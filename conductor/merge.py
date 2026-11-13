from __future__ import annotations

import subprocess
from pathlib import Path

from conductor.worker import HOOK_OUTPUT_LIMIT, git


def merge_branch(repo: Path, branch: str, into: str) -> str | None:
    """Merge `branch` into `into`; return why it could not (conflict, hook), or None."""
    git(repo, "checkout", "-q", into)
    completed = subprocess.run(
        [
            "git",
            "-c",
            "user.name=conductor",
            "-c",
            "user.email=conductor@local",
            "merge",
            "--no-ff",
            "-q",
            "-m",
            f"chore(conductor): merge {branch}",
            branch,
        ],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    if completed.returncode == 0:
        return None
    conflicted = git(repo, "diff", "--name-only", "--diff-filter=U").strip()
    git(repo, "merge", "--abort")
    if conflicted:
        return f"conflict in: {conflicted}"
    output = (completed.stdout + completed.stderr).strip()[-HOOK_OUTPUT_LIMIT:]
    return f"merge rejected: {output or 'unknown reason'}"
