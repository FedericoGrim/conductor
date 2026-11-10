from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
from typing import Any


class PlanError(ValueError):
    pass


@dataclass(frozen=True)
class Step:
    id: str
    title: str
    spec: str
    files: tuple[str, ...]
    difficulty: int
    depends_on: tuple[str, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Step:
        step = cls(
            id=str(data["id"]),
            title=str(data.get("title", data["id"])),
            spec=str(data.get("spec", "")),
            files=tuple(str(f) for f in data.get("files", [])),
            difficulty=int(data.get("difficulty", 1)),
            depends_on=tuple(str(d) for d in data.get("depends_on", [])),
        )
        if not step.spec.strip():
            raise PlanError(f"step '{step.id}' has an empty spec")
        if step.difficulty < 1:
            raise PlanError(f"step '{step.id}': difficulty must be >= 1")
        return step


@dataclass(frozen=True)
class Plan:
    goal: str
    steps: tuple[Step, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Plan:
        steps = tuple(Step.from_dict(s) for s in data.get("steps", []))
        ids: set[str] = set()
        for step in steps:
            if step.id in ids:
                raise PlanError(f"duplicate step id '{step.id}'")
            ids.add(step.id)
        for step in steps:
            for dep in step.depends_on:
                if dep not in ids:
                    raise PlanError(f"step '{step.id}' depends on unknown step '{dep}'")
        try:
            TopologicalSorter({s.id: s.depends_on for s in steps}).prepare()
        except CycleError as error:
            raise PlanError(f"dependency cycle: {error.args[1]}") from error
        return cls(goal=str(data.get("goal", "")), steps=steps)

    @classmethod
    def load(cls, path: Path) -> Plan:
        return cls.from_dict(json.loads(path.read_text()))

    def ready(self, done: Iterable[str]) -> list[Step]:
        finished = set(done)
        return [s for s in self.steps if s.id not in finished and set(s.depends_on) <= finished]
