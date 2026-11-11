import pytest

from conductor.plan import Plan, PlanError, Step


def step(id: str, depends_on: list[str] | None = None, difficulty: int = 1) -> dict[str, object]:
    return {
        "id": id,
        "title": f"Step {id}",
        "spec": f"Do {id}",
        "files": [f"{id}.py"],
        "difficulty": difficulty,
        "depends_on": depends_on or [],
    }


def test_parses_steps_in_order() -> None:
    plan = Plan.from_dict({"goal": "g", "steps": [step("a"), step("b", ["a"], 2)]})
    assert plan.goal == "g"
    assert [s.id for s in plan.steps] == ["a", "b"]
    assert plan.steps[1] == Step("b", "Step b", "Do b", ("b.py",), 2, ("a",))


def test_rejects_duplicate_ids() -> None:
    with pytest.raises(PlanError, match="duplicate step id 'a'"):
        Plan.from_dict({"goal": "g", "steps": [step("a"), step("a")]})


def test_rejects_unknown_dependency() -> None:
    with pytest.raises(PlanError, match="step 'a' depends on unknown step 'zz'"):
        Plan.from_dict({"goal": "g", "steps": [step("a", ["zz"])]})


def test_rejects_cycle() -> None:
    with pytest.raises(PlanError, match="dependency cycle"):
        Plan.from_dict({"goal": "g", "steps": [step("a", ["b"]), step("b", ["a"])]})


def test_rejects_difficulty_outside_the_five_levels() -> None:
    for difficulty in (0, 6):
        with pytest.raises(PlanError, match="between 1 and 5"):
            Plan.from_dict({"goal": "g", "steps": [step("a", difficulty=difficulty)]})


def test_rejects_empty_spec() -> None:
    bad = step("a")
    bad["spec"] = " "
    with pytest.raises(PlanError, match="step 'a' has an empty spec"):
        Plan.from_dict({"goal": "g", "steps": [bad]})


def test_ready_steps_follow_dependencies() -> None:
    plan = Plan.from_dict({"goal": "g", "steps": [step("a"), step("b", ["a"]), step("c")]})
    assert [s.id for s in plan.ready(done=set())] == ["a", "c"]
    assert [s.id for s in plan.ready(done={"a"})] == ["b", "c"]
