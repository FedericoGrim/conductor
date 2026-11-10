from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from conductor.plan import Plan, Step

Status = str
APPROVED = "approved"
FAILED = "failed"
SKIPPED = "skipped"
CONFLICT = "conflict"
NEEDS_BRAIN_REVIEW = "needs_brain_review"


@dataclass
class StepResult:
    step_id: str
    status: Status
    detail: str = ""
    attempts: list[dict[str, Any]] = field(default_factory=list)


Executor = Callable[[Step], Awaitable[StepResult]]


async def run_plan(plan: Plan, max_parallel: int, execute: Executor) -> dict[str, StepResult]:
    results: dict[str, StepResult] = {}
    gate = asyncio.Semaphore(max_parallel)
    running: dict[str, asyncio.Task[StepResult]] = {}

    async def guarded(step: Step) -> StepResult:
        async with gate:
            return await execute(step)

    while len(results) < len(plan.steps):
        for step in plan.ready(done=results):
            if step.id in running:
                continue
            blocked = next((d for d in step.depends_on if results[d].status != APPROVED), None)
            if blocked is not None:
                results[step.id] = StepResult(
                    step.id, SKIPPED, f"dependency '{blocked}' not approved"
                )
                continue
            running[step.id] = asyncio.create_task(guarded(step))
        if not running:
            continue
        done, _ = await asyncio.wait(running.values(), return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            result = task.result()
            results[result.step_id] = result
            del running[result.step_id]
    return results
