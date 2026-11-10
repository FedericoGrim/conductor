from __future__ import annotations

import subprocess
from pathlib import Path

from conductor.worker import git


def merge_branch(repo: Path, branch: str, into: str) -> str | None:
    """Merge `branch` into `into` inside `repo`; returns the conflict description or None."""
    git(repo, "checkout", "-q", into)
    try:
        git(
            repo,
            "-c",
            "user.name=conductor",
            "-c",
            "user.email=conductor@local",
            "merge",
            "--no-ff",
            "-q",
            "-m",
            f"conductor: merge {branch}",
            branch,
        )
    except subprocess.CalledProcessError:
        conflicted = git(repo, "diff", "--name-only", "--diff-filter=U").strip()
        git(repo, "merge", "--abort")
        return f"conflict in: {conflicted or 'unknown files'}"
    return None
