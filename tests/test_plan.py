import pytest

from conductor.plan import Answer, Plan, PlanError, Step


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


def test_a_step_carries_the_answers_to_earlier_questions() -> None:
    answered = step("a")
    answered["answers"] = [{"question": "Case-sensitive names?", "answer": "No, fold case."}]
    plan = Plan.from_dict({"goal": "g", "steps": [answered]})
    assert plan.steps[0].answers == (Answer("Case-sensitive names?", "No, fold case."),)


def test_answers_default_to_none() -> None:
    assert Plan.from_dict({"goal": "g", "steps": [step("a")]}).steps[0].answers == ()


@pytest.mark.parametrize(
    "answers",
    [
        "not a list",
        ["not an object"],
        [{"question": "q"}],
        [{"question": " ", "answer": "a"}],
        [{"question": "q", "answer": 3}],
    ],
)
def test_rejects_malformed_answers(answers: object) -> None:
    bad = step("a")
    bad["answers"] = answers
    with pytest.raises(PlanError, match="step 'a': answers"):
        Plan.from_dict({"goal": "g", "steps": [bad]})
