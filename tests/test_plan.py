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


def test_the_plan_declares_rules_a_rules_file_and_default_verify_commands() -> None:
    plan = Plan.from_dict(
        {
            "goal": "g",
            "rules": ["Totals never go negative"],
            "rules_file": "docs/rules.md",
            "verify": ["pytest -q"],
            "verify_timeout": 120,
            "steps": [step("a")],
        }
    )
    assert plan.rules == ("Totals never go negative",)
    assert plan.rules_file == "docs/rules.md"
    assert plan.verify == ("pytest -q",)
    assert plan.verify_timeout == 120


def test_a_step_inherits_the_plan_verify_unless_it_has_its_own() -> None:
    own, none, inherits = step("own"), step("none"), step("inherits")
    own["verify"] = ["pytest -q tests/test_own.py"]
    none["verify"] = []
    plan = Plan.from_dict({"goal": "g", "verify": ["pytest -q"], "steps": [own, none, inherits]})
    assert [plan.verify_for(s) for s in plan.steps] == [
        ("pytest -q tests/test_own.py",),
        (),
        ("pytest -q",),
    ]


def test_the_new_fields_are_optional() -> None:
    plan = Plan.from_dict({"goal": "g", "steps": [step("a")]})
    assert (plan.rules, plan.rules_file, plan.verify) == ((), None, ())
    assert plan.verify_timeout == 600
    assert plan.verify_for(plan.steps[0]) == ()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("rules", "one rule", "rules must be a list of non-empty strings"),
        ("rules", [""], "rules must be a list of non-empty strings"),
        ("verify", ["ok", 3], "verify must be a list of non-empty strings"),
        ("rules_file", "/etc/passwd", "rules_file must be a relative path inside the repository"),
        ("rules_file", "../outside.md", "rules_file must be a relative path inside the repository"),
        ("verify_timeout", 0, "verify_timeout must be a positive number of seconds"),
        ("verify_timeout", True, "verify_timeout must be a positive number of seconds"),
    ],
)
def test_rejects_malformed_plan_fields(field: str, value: object, message: str) -> None:
    with pytest.raises(PlanError, match=message):
        Plan.from_dict({"goal": "g", field: value, "steps": [step("a")]})


def test_rejects_a_malformed_step_verify() -> None:
    bad = step("a")
    bad["verify"] = "pytest"
    with pytest.raises(PlanError, match="step 'a': verify must be a list of non-empty strings"):
        Plan.from_dict({"goal": "g", "steps": [bad]})
