from conductor.overlap import Overlap, describe, parallel_overlaps
from conductor.plan import Plan


def step(id: str, files: list[str], depends_on: list[str] | None = None) -> dict[str, object]:
    return {
        "id": id,
        "spec": f"Do {id}",
        "files": files,
        "depends_on": depends_on or [],
    }


def plan(*steps: dict[str, object]) -> Plan:
    return Plan.from_dict({"goal": "g", "steps": list(steps)})


def test_independent_steps_sharing_a_file_overlap() -> None:
    overlaps = parallel_overlaps(plan(step("a", ["x.py", "a.py"]), step("b", ["x.py"])))
    assert overlaps == [Overlap("a", "b", ("x.py",))]


def test_a_direct_dependency_is_not_a_parallel_overlap() -> None:
    overlaps = parallel_overlaps(plan(step("a", ["x.py"]), step("b", ["x.py"], ["a"])))
    assert overlaps == []


def test_a_transitive_dependency_is_not_a_parallel_overlap() -> None:
    overlaps = parallel_overlaps(
        plan(step("a", ["x.py"]), step("b", ["y.py"], ["a"]), step("c", ["x.py"], ["b"]))
    )
    assert overlaps == []


def test_a_dot_slash_path_matches_the_same_file() -> None:
    overlaps = parallel_overlaps(plan(step("a", ["./a.py"]), step("b", ["a.py"])))
    assert overlaps == [Overlap("a", "b", ("a.py",))]


def test_a_directory_covers_the_files_under_it() -> None:
    overlaps = parallel_overlaps(plan(step("a", ["docs/"]), step("b", ["docs/x.md"])))
    assert overlaps == [Overlap("a", "b", ("docs/", "docs/x.md"))]


def test_a_glob_covers_the_matching_files() -> None:
    overlaps = parallel_overlaps(
        plan(step("a", ["tests/test_*.py"]), step("b", ["tests/test_plan.py"]))
    )
    assert overlaps == [Overlap("a", "b", ("tests/test_*.py", "tests/test_plan.py"))]


def test_three_steps_give_two_pairs_in_plan_order() -> None:
    overlaps = parallel_overlaps(
        plan(
            step("a", ["x.py"]),
            step("b", ["x.py"], ["a"]),
            step("c", ["x.py"]),
        )
    )
    assert overlaps == [Overlap("a", "c", ("x.py",)), Overlap("b", "c", ("x.py",))]


def test_describe_names_both_steps_and_the_files() -> None:
    overlap = Overlap("a", "b", ("docs/", "x.py"))
    assert describe(overlap) == ("steps 'a' and 'b' can run in parallel and both list docs/, x.py")
