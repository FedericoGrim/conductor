from __future__ import annotations

import shlex
from collections.abc import Iterable
from pathlib import PurePosixPath

from conductor.verify import CheckResult

MACHINE_CHECKED = ("types", "imports", "syntax", "format", "lint", "failing-tests")
JUDGEMENT = ("spec", "missing-tests", "domain", "logic", "security", "commit")
CATEGORIES = MACHINE_CHECKED + JUDGEMENT

TOOL_CATEGORIES: dict[str, frozenset[str]] = {
    "mypy": frozenset({"types", "imports", "syntax"}),
    "pyright": frozenset({"types", "imports", "syntax"}),
    "tsc": frozenset({"types", "imports", "syntax"}),
    "ruff": frozenset({"lint", "imports", "syntax"}),
    "flake8": frozenset({"lint", "imports", "syntax"}),
    "pylint": frozenset({"lint", "imports", "syntax"}),
    "eslint": frozenset({"lint", "imports", "syntax"}),
    "black": frozenset({"format"}),
    "prettier": frozenset({"format"}),
    "pytest": frozenset({"failing-tests", "syntax"}),
    "jest": frozenset({"failing-tests", "syntax"}),
    "vitest": frozenset({"failing-tests", "syntax"}),
}
RUFF_FORMAT = frozenset({"format", "syntax"})


def tool_categories(tokens: list[str]) -> frozenset[str]:
    names = [PurePosixPath(token).name for token in tokens]
    if "ruff" in names and "format" in names:
        return RUFF_FORMAT
    covered: set[str] = set()
    for name in names:
        covered.update(TOOL_CATEGORIES.get(name, frozenset()))
    return frozenset(covered)


def covered_categories(commands: Iterable[str]) -> frozenset[str]:
    covered: set[str] = set()
    for command in commands:
        try:
            tokens = shlex.split(command)
        except ValueError:
            continue
        covered.update(tool_categories(tokens))
    return frozenset(covered)


def is_suspicious(ok: bool, category: str | None, checks: Iterable[CheckResult]) -> bool:
    if ok or category not in MACHINE_CHECKED:
        return False
    passed = (check.command for check in checks if check.ok)
    return category in covered_categories(passed)
