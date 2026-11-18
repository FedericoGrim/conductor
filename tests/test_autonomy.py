import pytest

from conductor.autonomy import (
    ASK,
    DEFAULT_AUTONOMY,
    FREE,
    GUIDED,
    LEVELS,
    PROTECTED_BRANCHES,
    effective,
    exceeds,
    forbidden_commands,
    is_protected,
)


def test_levels_go_from_the_most_to_the_least_supervised() -> None:
    assert LEVELS == (ASK, GUIDED, FREE)


def test_the_default_keeps_todays_behaviour() -> None:
    assert DEFAULT_AUTONOMY == FREE


@pytest.mark.parametrize(
    ("ceiling", "requested", "expected"),
    [
        (FREE, None, FREE),
        (FREE, GUIDED, GUIDED),
        (GUIDED, ASK, ASK),
        (GUIDED, FREE, GUIDED),
        (ASK, FREE, ASK),
    ],
)
def test_a_step_can_only_lower_the_ceiling(ceiling: str, requested: str, expected: str) -> None:
    assert effective(ceiling, requested) == expected


def test_a_level_above_the_ceiling_exceeds_it() -> None:
    assert exceeds(FREE, GUIDED)
    assert exceeds(GUIDED, ASK)
    assert not exceeds(GUIDED, GUIDED)
    assert not exceeds(ASK, FREE)


def test_main_and_develop_are_protected() -> None:
    assert PROTECTED_BRANCHES == ("main", "develop")
    assert is_protected("develop")
    assert not is_protected("feature/35-autonomy")


def test_forbidden_commands_cover_push_publish_release_and_protected_branches() -> None:
    commands = forbidden_commands()
    for expected in (
        "git push *",
        "git * push *",
        "gh release *",
        "gh pr merge *",
        "npm publish *",
        "twine upload *",
        "uv publish *",
        "cargo publish *",
        "git checkout main *",
        "git switch develop *",
        "git branch -f main *",
        "git update-ref refs/heads/develop *",
    ):
        assert expected in commands
    assert len(commands) == len(set(commands))
