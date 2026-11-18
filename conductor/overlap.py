from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import PurePosixPath

from conductor.plan import Plan, Step


@dataclass(frozen=True)
class Overlap:
    first: str
    second: str
    files: tuple[str, ...]


def parallel_overlaps(plan: Plan) -> list[Overlap]:
    ancestors = {step.id: _ancestors(plan, step) for step in plan.steps}
    overlaps: list[Overlap] = []
    for i, first in enumerate(plan.steps):
        for second in plan.steps[i + 1 :]:
            if first.id in ancestors[second.id] or second.id in ancestors[first.id]:
                continue
            files = _shared_files(first.files, second.files)
            if files:
                overlaps.append(Overlap(first.id, second.id, files))
    return overlaps


def describe(overlap: Overlap) -> str:
    return (
        f"steps '{overlap.first}' and '{overlap.second}' can run in parallel "
        f"and both list {', '.join(overlap.files)}"
    )


def _ancestors(plan: Plan, step: Step) -> set[str]:
    by_id = {s.id: s for s in plan.steps}
    found: set[str] = set()
    pending = list(step.depends_on)
    while pending:
        dep = pending.pop()
        if dep not in found:
            found.add(dep)
            pending.extend(by_id[dep].depends_on)
    return found


def _shared_files(first: tuple[str, ...], second: tuple[str, ...]) -> tuple[str, ...]:
    shared: set[str] = set()
    for a in map(_normalise, first):
        for b in map(_normalise, second):
            if _overlaps(a, b):
                shared.update((a, b))
    return tuple(sorted(shared))


def _normalise(path: str) -> str:
    normal = PurePosixPath(path).as_posix()
    return normal + "/" if path.endswith("/") else normal


def _overlaps(a: str, b: str) -> bool:
    return _covers(a, b) or _covers(b, a)


def _covers(entry: str, target: str) -> bool:
    if entry.endswith("/"):
        return target.startswith(entry)
    if _is_glob(entry):
        return fnmatch(target, entry)
    return entry == target


def _is_glob(path: str) -> bool:
    return any(char in path for char in "*?[")
