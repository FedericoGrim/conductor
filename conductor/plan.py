from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
from typing import Any

from conductor.commits import is_conventional

DIFFICULTY_LEVELS = 5
DEFAULT_VERIFY_TIMEOUT = 600


class PlanError(ValueError):
    pass


@dataclass(frozen=True)
class Answer:
    question: str
    answer: str


def parse_answers(step_id: str, data: object) -> tuple[Answer, ...]:
    problem = PlanError(
        f"step '{step_id}': answers must be a list of {{question, answer}} non-empty strings"
    )
    if not isinstance(data, list):
        raise problem
    answers = []
    for entry in data:
        if not isinstance(entry, dict):
            raise problem
        question, answer = entry.get("question"), entry.get("answer")
        if not (isinstance(question, str) and question.strip()):
            raise problem
        if not (isinstance(answer, str) and answer.strip()):
            raise problem
        answers.append(Answer(question, answer))
    return tuple(answers)


def string_list(data: object, where: str) -> tuple[str, ...]:
    if not isinstance(data, list) or not all(isinstance(i, str) and i.strip() for i in data):
        raise PlanError(f"{where} must be a list of non-empty strings")
    return tuple(data)


def relative_path(data: object) -> str | None:
    if data is None:
        return None
    path = Path(str(data))
    if not str(data).strip() or path.is_absolute() or ".." in path.parts:
        raise PlanError("rules_file must be a relative path inside the repository")
    return str(data)


def positive_seconds(data: object) -> float:
    if isinstance(data, bool) or not isinstance(data, int | float) or data <= 0:
        raise PlanError("verify_timeout must be a positive number of seconds")
    return float(data)


@dataclass(frozen=True)
class Step:
    id: str
    title: str
    spec: str
    files: tuple[str, ...]
    difficulty: int
    depends_on: tuple[str, ...]
    answers: tuple[Answer, ...] = ()
    verify: tuple[str, ...] | None = None
    commit: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Step:
        step_id = str(data["id"])
        verify = data.get("verify")
        commit = data.get("commit")
        if commit is not None and (not isinstance(commit, str) or not is_conventional(commit)):
            raise PlanError(
                f"step '{step_id}': commit must be a Conventional Commit subject "
                "(type(scope): subject, at most 72 characters)"
            )
        step = cls(
            id=str(data["id"]),
            title=str(data.get("title", data["id"])),
            spec=str(data.get("spec", "")),
            files=tuple(str(f) for f in data.get("files", [])),
            difficulty=int(data.get("difficulty", 1)),
            depends_on=tuple(str(d) for d in data.get("depends_on", [])),
            answers=parse_answers(step_id, data.get("answers", [])),
            verify=None if verify is None else string_list(verify, f"step '{step_id}': verify"),
            commit=commit,
        )
        if not step.spec.strip():
            raise PlanError(f"step '{step.id}' has an empty spec")
        if not 1 <= step.difficulty <= DIFFICULTY_LEVELS:
            raise PlanError(
                f"step '{step.id}': difficulty must be between 1 and {DIFFICULTY_LEVELS}"
            )
        return step


@dataclass(frozen=True)
class Plan:
    goal: str
    steps: tuple[Step, ...]
    rules: tuple[str, ...] = ()
    rules_file: str | None = None
    verify: tuple[str, ...] = ()
    verify_timeout: float = DEFAULT_VERIFY_TIMEOUT

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
        return cls(
            goal=str(data.get("goal", "")),
            steps=steps,
            rules=string_list(data.get("rules", []), "rules"),
            rules_file=relative_path(data.get("rules_file")),
            verify=string_list(data.get("verify", []), "verify"),
            verify_timeout=positive_seconds(data.get("verify_timeout", DEFAULT_VERIFY_TIMEOUT)),
        )

    @classmethod
    def load(cls, path: Path) -> Plan:
        return cls.from_dict(json.loads(path.read_text()))

    def verify_for(self, step: Step) -> tuple[str, ...]:
        return self.verify if step.verify is None else step.verify

    def ready(self, done: Iterable[str]) -> list[Step]:
        finished = set(done)
        return [s for s in self.steps if s.id not in finished and set(s.depends_on) <= finished]
