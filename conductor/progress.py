from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

WAITING = "waiting"
RUNNING = "running"
APPROVED = "approved"


@dataclass
class _StepState:
    status: str = WAITING
    attempt: int = 0
    level: int = 0
    model: str = ""
    started: float = 0.0


@dataclass
class Progress:
    step_ids: list[str]
    max_parallel: int
    clock: Callable[[], float] = time.monotonic
    _steps: dict[str, _StepState] = field(init=False)
    _created: float = field(init=False)
    _durations: list[float] = field(init=False, default_factory=list)

    def __post_init__(self) -> None:
        self._steps = {step_id: _StepState() for step_id in self.step_ids}
        self._created = self.clock()

    def attempt_started(self, step_id: str, number: int, level: int, model: str) -> None:
        self._steps[step_id] = _StepState(
            status=RUNNING,
            attempt=number,
            level=level,
            model=model,
            started=self.clock(),
        )

    def attempt_finished(self, step_id: str) -> None:
        step = self._steps[step_id]
        if step.status != RUNNING:
            raise ValueError(f"step {step_id} has no running attempt")
        self._durations.append(self.clock() - step.started)

    def step_finished(self, step_id: str, status: str) -> None:
        self._steps[step_id].status = status

    def elapsed(self) -> float:
        return self.clock() - self._created

    def remaining(self) -> float | None:
        if not self._durations:
            return None
        mean = sum(self._durations) / len(self._durations)
        waiting = self._count(lambda status: status == WAITING)
        running = self._count(lambda status: status == RUNNING)
        parallel = max(1, min(self.max_parallel, waiting + running))
        return max(0.0, mean * (waiting + running) / parallel)

    def summary(self) -> str:
        total = len(self.step_ids)
        waiting = self._count(lambda status: status == WAITING)
        running = self._count(lambda status: status == RUNNING)
        done = total - waiting - running
        approved = self._count(lambda status: status == APPROVED)
        remaining = self.remaining()
        left = "n/a" if remaining is None else f"~{_format_duration(remaining)} (estimate)"
        parts = [
            f"progress: {done}/{total} done ({approved} approved), "
            f"{running} running, {waiting} waiting",
            f"elapsed {_format_duration(self.elapsed())}",
            f"left {left}",
        ]
        for step_id in self.step_ids:
            step = self._steps[step_id]
            if step.status == RUNNING:
                parts.append(f"{step_id} #{step.attempt} L{step.level} {step.model}")
        return " | ".join(parts)

    def _count(self, predicate: Callable[[str], bool]) -> int:
        return sum(1 for step in self._steps.values() if predicate(step.status))


def _format_duration(seconds: float) -> str:
    whole = max(0, int(seconds))
    if whole >= 3600:
        hours, rest = divmod(whole, 3600)
        return f"{hours}h{rest // 60:02d}m"
    if whole >= 60:
        minutes, rest = divmod(whole, 60)
        return f"{minutes}m{rest:02d}s"
    return f"{whole}s"


CLEAR_LINE = "\r\x1b[2K"


@dataclass
class StatusLine:
    write: Callable[[str], None]
    is_terminal: bool
    shown: str = ""

    def update(self, summary: str) -> None:
        self.shown = summary
        if self.is_terminal:
            self.write(CLEAR_LINE + summary)

    def step_done(self, summary: str) -> None:
        self.shown = ""
        self.write((CLEAR_LINE if self.is_terminal else "") + summary + "\n")

    def clear(self) -> None:
        if self.is_terminal and self.shown:
            self.write(CLEAR_LINE)
