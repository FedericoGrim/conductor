from __future__ import annotations

ASK = "ask"
GUIDED = "guided"
FREE = "free"
LEVELS = (ASK, GUIDED, FREE)
DEFAULT_AUTONOMY = FREE

PROTECTED_BRANCHES = ("main", "develop")

PUBLISHING_COMMANDS = (
    "git push *",
    "git * push *",
    "gh release *",
    "gh pr merge *",
    "npm publish *",
    "pnpm publish *",
    "yarn publish *",
    "yarn npm publish *",
    "poetry publish *",
    "twine upload *",
    "uv publish *",
    "cargo publish *",
)

BRANCH_COMMANDS = (
    "git checkout {branch} *",
    "git switch {branch} *",
    "git branch -f {branch} *",
    "git update-ref refs/heads/{branch} *",
)


def rank(level: str) -> int:
    return LEVELS.index(level)


def exceeds(requested: str, ceiling: str) -> bool:
    return rank(requested) > rank(ceiling)


def effective(ceiling: str, requested: str | None) -> str:
    if requested is None or exceeds(requested, ceiling):
        return ceiling
    return requested


def is_protected(branch: str) -> bool:
    return branch in PROTECTED_BRANCHES


def forbidden_commands() -> tuple[str, ...]:
    """Shell patterns no worker may run at any autonomy level (OpenCode wildcard syntax)."""
    branch_commands = tuple(
        command.format(branch=branch)
        for branch in PROTECTED_BRANCHES
        for command in BRANCH_COMMANDS
    )
    return PUBLISHING_COMMANDS + branch_commands
