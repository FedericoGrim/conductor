import asyncio

from conductor.plan import Plan, Step
from conductor.scheduler import NEEDS_ANSWER, UNAVAILABLE, StepResult, run_plan


def make_plan(*steps: tuple[str, list[str]]) -> Plan:
    return Plan(
        goal="g",
        steps=tuple(Step(id, id, f"do {id}", (), 1, tuple(deps)) for id, deps in steps),
    )


def test_runs_independent_steps_concurrently_up_to_max_parallel() -> None:
    plan = make_plan(("a", []), ("b", []), ("c", []))
    running = 0
    peak = 0

    async def execute(step: Step) -> StepResult:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.01)
        running -= 1
        return StepResult(step.id, "approved")

    results = asyncio.run(run_plan(plan, max_parallel=2, execute=execute))
    assert peak == 2
    assert {id: r.status for id, r in results.items()} == {
        "a": "approved",
        "b": "approved",
        "c": "approved",
    }


def test_dependent_step_starts_only_after_its_dependency() -> None:
    plan = make_plan(("a", []), ("b", ["a"]))
    order: list[str] = []

    async def execute(step: Step) -> StepResult:
        order.append(f"start {step.id}")
        await asyncio.sleep(0.01)
        order.append(f"end {step.id}")
        return StepResult(step.id, "approved")

    asyncio.run(run_plan(plan, max_parallel=4, execute=execute))
    assert order == ["start a", "end a", "start b", "end b"]


def test_dependents_of_a_failed_step_are_skipped() -> None:
    plan = make_plan(("a", []), ("b", ["a"]), ("c", ["b"]), ("d", []))

    async def execute(step: Step) -> StepResult:
        return StepResult(step.id, "failed" if step.id == "a" else "approved")

    results = asyncio.run(run_plan(plan, max_parallel=4, execute=execute))
    assert results["a"].status == "failed"
    assert results["b"].status == "skipped"
    assert results["c"].status == "skipped"
    assert results["d"].status == "approved"


def test_dependents_of_an_unavailable_step_are_skipped() -> None:
    plan = make_plan(("a", []), ("b", ["a"]))

    async def execute(step: Step) -> StepResult:
        return StepResult(step.id, UNAVAILABLE if step.id == "a" else "approved")

    results = asyncio.run(run_plan(plan, max_parallel=4, execute=execute))
    assert results["b"].status == "skipped"
    assert "'a' not approved" in results["b"].detail


def test_dependents_of_a_step_waiting_for_an_answer_are_skipped() -> None:
    plan = make_plan(("a", []), ("b", ["a"]))

    async def execute(step: Step) -> StepResult:
        return StepResult(step.id, NEEDS_ANSWER if step.id == "a" else "approved")

    results = asyncio.run(run_plan(plan, max_parallel=4, execute=execute))
    assert results["b"].status == "skipped"


def test_an_unexpected_error_in_a_step_fails_it_and_the_run_goes_on() -> None:
    plan = make_plan(("a", []), ("b", ["a"]), ("c", []))

    async def execute(step: Step) -> StepResult:
        if step.id == "a":
            raise RuntimeError("git exploded")
        return StepResult(step.id, "approved")

    results = asyncio.run(run_plan(plan, max_parallel=4, execute=execute))
    assert results["a"].status == "failed"
    assert results["a"].detail == "internal error: RuntimeError: git exploded"
    assert results["b"].status == "skipped"
    assert results["c"].status == "approved"
