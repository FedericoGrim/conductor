from conductor.rejections import (
    CATEGORIES,
    JUDGEMENT,
    MACHINE_CHECKED,
    covered_categories,
    is_suspicious,
)
from conductor.verify import CheckResult


def test_categories_partition_machine_checks_and_judgement() -> None:
    assert CATEGORIES == MACHINE_CHECKED + JUDGEMENT
    assert set(MACHINE_CHECKED).isdisjoint(JUDGEMENT)


def test_covered_categories_recognises_a_venv_tool_by_basename() -> None:
    assert covered_categories(["$CONDUCTOR_REPO/.venv/bin/mypy --strict conductor"]) == frozenset(
        {"types", "imports", "syntax"}
    )


def test_covered_categories_recognises_a_python_module_invocation() -> None:
    assert covered_categories(["python -m pytest -q"]) == frozenset({"failing-tests", "syntax"})


def test_covered_categories_recognises_ruff_check() -> None:
    assert covered_categories([".venv/bin/ruff check ."]) == frozenset(
        {"lint", "imports", "syntax"}
    )


def test_covered_categories_adds_format_for_ruff_format() -> None:
    assert covered_categories(["ruff format --check"]) == frozenset(
        {"lint", "imports", "syntax", "format"}
    )


def test_covered_categories_ignores_unknown_commands() -> None:
    assert covered_categories(["make check", "pre-commit run"]) == frozenset()


def test_covered_categories_ignores_an_unparseable_command() -> None:
    assert covered_categories(["pytest 'unclosed"]) == frozenset()


def test_is_suspicious_flags_a_machine_checked_rejection_a_passed_check_covers() -> None:
    passed = CheckResult("mypy conductor", 0, "", 1.0)
    assert is_suspicious(False, "imports", [passed])


def test_is_suspicious_ignores_a_judgement_category() -> None:
    passed = CheckResult("mypy conductor", 0, "", 1.0)
    assert not is_suspicious(False, "logic", [passed])


def test_is_suspicious_needs_the_covering_check_to_have_passed() -> None:
    failed = CheckResult("mypy conductor", 1, "", 1.0)
    assert not is_suspicious(False, "imports", [failed])


def test_is_suspicious_needs_a_passed_check_that_covers_the_category() -> None:
    passed = CheckResult("black .", 0, "", 1.0)
    assert not is_suspicious(False, "imports", [passed])


def test_is_suspicious_ignores_an_approval() -> None:
    passed = CheckResult("mypy conductor", 0, "", 1.0)
    assert not is_suspicious(True, "imports", [passed])
