from __future__ import annotations

import pytest

from conductor.progress import Progress


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def make(clock: FakeClock, step_ids: list[str] | None = None, max_parallel: int = 2) -> Progress:
    return Progress(
        step_ids=step_ids or ["a", "b", "c", "d", "e"],
        max_parallel=max_parallel,
        clock=clock,
    )


def test_remaining_is_none_before_the_first_finished_attempt() -> None:
    clock = FakeClock()
    progress = make(clock)
    progress.attempt_started("a", 1, 1, "p/m1")

    assert progress.remaining() is None


def test_remaining_is_none_while_an_attempt_is_running_and_unfinished() -> None:
    clock = FakeClock()
    progress = make(clock)
    progress.attempt_started("a", 1, 1, "p/m1")
    clock.now = 60.0

    assert progress.remaining() is None
    assert "left n/a" in progress.summary()


def test_remaining_estimates_from_mean_attempt_duration() -> None:
    clock = FakeClock()
    progress = make(clock)
    progress.attempt_started("a", 1, 1, "p/m1")
    clock.now = 60.0
    progress.attempt_finished("a")
    progress.step_finished("a", "approved")
    progress.attempt_started("b", 1, 1, "p/m1")
    clock.now = 180.0
    progress.attempt_finished("b")
    progress.step_finished("b", "approved")

    # mean 90 s, 3 waiting steps, max_parallel 2: 90 * 3 / 2
    assert progress.remaining() == pytest.approx(135.0)


def test_remaining_is_never_negative() -> None:
    clock = FakeClock()
    progress = make(clock, step_ids=["a"], max_parallel=4)
    progress.attempt_started("a", 1, 1, "p/m1")
    clock.now = 60.0
    progress.attempt_finished("a")
    progress.step_finished("a", "approved")

    assert progress.remaining() == 0.0


def test_summary_counts_done_approved_running_and_waiting() -> None:
    clock = FakeClock()
    progress = make(clock)
    progress.attempt_started("a", 1, 1, "p/m1")
    clock.now = 60.0
    progress.attempt_finished("a")
    progress.step_finished("a", "approved")
    progress.attempt_started("b", 1, 2, "p/m2")
    progress.attempt_finished("b")
    progress.step_finished("b", "failed")
    progress.attempt_started("c", 2, 3, "p/m3")
    progress.attempt_started("d", 1, 2, "p/m2")

    line = progress.summary()

    assert line.startswith("progress: 2/5 done (1 approved), 2 running, 1 waiting")


def test_summary_shows_attempt_level_and_model_of_running_steps() -> None:
    clock = FakeClock()
    progress = make(clock)
    progress.attempt_started("c", 2, 3, "openrouter/some-model")

    line = progress.summary()

    assert line.endswith(" | c #2 L3 openrouter/some-model")


def test_summary_full_line_with_estimate() -> None:
    clock = FakeClock()
    progress = make(clock)
    progress.attempt_started("a", 1, 1, "p/m1")
    clock.now = 60.0
    progress.attempt_finished("a")
    progress.step_finished("a", "approved")
    progress.attempt_started("b", 1, 1, "p/m1")
    clock.now = 120.0
    progress.attempt_finished("b")
    progress.step_finished("b", "approved")
    progress.attempt_started("c", 2, 3, "p/m3")
    progress.attempt_started("d", 1, 2, "p/m2")
    clock.now = 192.0

    assert progress.summary() == (
        "progress: 2/5 done (2 approved), 2 running, 1 waiting"
        " | elapsed 3m12s | left ~1m30s (estimate)"
        " | c #2 L3 p/m3 | d #1 L2 p/m2"
    )


def test_summary_says_left_is_not_available_before_first_attempt_finishes() -> None:
    clock = FakeClock()
    progress = make(clock)

    assert progress.summary() == (
        "progress: 0/5 done (0 approved), 0 running, 5 waiting | elapsed 0s | left n/a"
    )


@pytest.mark.parametrize(
    ("elapsed", "expected"),
    [
        (59.0, "59s"),
        (61.0, "1m01s"),
        (3725.0, "1h02m"),
    ],
)
def test_summary_formats_durations(elapsed: float, expected: str) -> None:
    clock = FakeClock()
    progress = make(clock)
    clock.now = elapsed

    assert f"elapsed {expected}" in progress.summary()


def test_elapsed_is_measured_from_creation() -> None:
    clock = FakeClock()
    clock.now = 100.0
    progress = make(clock)
    clock.now = 130.0

    assert progress.elapsed() == pytest.approx(30.0)
