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


def covered_categories(commands: Iterable[str]) -> frozenset[str]:
    covered: set[str] = set()
    for command in commands:
        try:
            tokens = shlex.split(command)
        except ValueError:
            continue
        if "ruff" in tokens and "format" in tokens:
            covered.add("format")
        for token in tokens:
            categories = TOOL_CATEGORIES.get(PurePosixPath(token).name)
            if categories is not None:
                covered.update(categories)
    return frozenset(covered)


def is_suspicious(ok: bool, category: str | None, checks: Iterable[CheckResult]) -> bool:
    if ok or category not in MACHINE_CHECKED:
        return False
    passed = (check.command for check in checks if check.ok)
    return category in covered_categories(passed)
