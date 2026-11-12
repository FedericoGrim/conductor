import asyncio
from typing import Any

import pytest

from conductor.config import Profile, Provider
from conductor.errors import (
    MODEL_UNSUITABLE,
    PROVIDER_UNUSABLE,
    TRANSIENT,
    UNCLASSIFIED,
    ModelError,
)
from conductor.escalation import RunState, build_prompt, run_step
from conductor.plan import Step
from conductor.reviewer import Verdict
from conductor.worker import AttemptOutput
from tests.factories import make_profile

PROFILE = make_profile(api_key_env="K")
STEP = Step("s1", "Parser", "write a parser", ("parser.py",), 2, ())


def output(
    diff: str = "+code", exit_code: int = 0, cost: float = 0.0, error: ModelError | None = None
) -> AttemptOutput:
    return AttemptOutput(
        exit_code=exit_code, session_id="ses", events=[], diff=diff, cost=cost, error=error
    )


def run(
    verdicts: list[Verdict],
    outputs: list[AttemptOutput] | None = None,
    profile: Profile = PROFILE,
    state: RunState | None = None,
) -> Any:
    calls: list[tuple[int, str, str]] = []
    recorded: list[dict[str, Any]] = []
    outputs = outputs or [output() for _ in verdicts]
    judged = list(reversed(range(len(verdicts))))

    async def attempt(step: Step, number: int, model: str, prompt: str) -> AttemptOutput:
        calls.append((number, model, prompt))
        return outputs[number - 1]

    def judge(spec: str, diff: str) -> Verdict:
        return verdicts[judged.pop()]

    def record(step: Step, data: dict[str, Any]) -> None:
        recorded.append(data)

    result = asyncio.run(
        run_step(
            STEP,
            profile,
            attempt=attempt,
            judge=judge,
            record=record,
            state=state or RunState(),
        )
    )
    return result, calls, recorded


def test_starts_at_the_tier_matching_difficulty_and_approves() -> None:
    result, calls, recorded = run([Verdict(True, "fine", "{}")])
    assert result.status == "approved"
    assert [c[1] for c in calls] == ["openrouter/t1"]
    assert recorded[0]["model"] == "openrouter/t1"
    assert recorded[0]["review"]["ok"] is True


def test_rejection_escalates_with_the_reason_in_the_prompt() -> None:
    result, calls, _ = run([Verdict(False, "no tests", "{}"), Verdict(True, "ok", "{}")])
    assert result.status == "approved"
    assert [c[1] for c in calls] == ["openrouter/t1", "openrouter/t2"]
    assert "no tests" in calls[1][2]
    assert "no tests" not in calls[0][2]


def test_rejection_on_strongest_tier_fails_the_step() -> None:
    result, calls, _ = run([Verdict(False, "bad", "{}"), Verdict(False, "still bad", "{}")])
    assert result.status == "failed"
    assert "still bad" in result.detail
    assert len(calls) == 2


def test_empty_diff_counts_as_rejection() -> None:
    result, calls, recorded = run([Verdict(True, "ok", "{}")], outputs=[output(diff=""), output()])
    assert result.status == "approved"
    assert len(calls) == 2
    assert recorded[0]["review"]["reason"] == "no changes produced"


def test_each_attempt_records_worker_and_reviewer_cost() -> None:
    verdicts = [
        Verdict(False, "weak", "{}", usage={"cost": 0.001}),
        Verdict(True, "ok", "{}", usage={"total_tokens": 5}),
    ]
    _, _, recorded = run(verdicts, outputs=[output(cost=0.01), output(cost=0.2)])
    assert recorded[0]["cost"] == {"worker": 0.01, "reviewer": 0.001}
    assert recorded[1]["cost"] == {"worker": 0.2, "reviewer": None}


def test_a_failed_attempt_still_records_what_the_worker_spent() -> None:
    _, _, recorded = run([], outputs=[output(exit_code=3, cost=0.07)])
    assert recorded[0]["cost"] == {"worker": 0.07, "reviewer": None}


def test_opencode_failure_does_not_retry() -> None:
    result, calls, _ = run([], outputs=[output(exit_code=3)])
    assert result.status == "failed"
    assert "exit 3" in result.detail
    assert len(calls) == 1


@pytest.mark.parametrize("kind", [TRANSIENT, PROVIDER_UNUSABLE, MODEL_UNSUITABLE])
def test_a_classified_model_error_makes_the_step_unavailable_without_escalating(
    kind: str,
) -> None:
    error = ModelError(kind, "provider.x", "it broke")
    result, calls, recorded = run([], outputs=[output(exit_code=1, error=error)])
    assert result.status == "unavailable"
    assert len(calls) == 1
    assert "it broke" in result.detail
    assert recorded[0]["error"] == {"kind": kind, "type": "provider.x", "message": "it broke"}


def test_an_unclassified_model_error_fails_the_step() -> None:
    error = ModelError(UNCLASSIFIED, "tool.crashed", "boom")
    result, calls, recorded = run([], outputs=[output(exit_code=1, error=error)])
    assert result.status == "failed"
    assert len(calls) == 1
    assert recorded[0]["error"]["kind"] == UNCLASSIFIED


def test_a_successful_attempt_records_no_error() -> None:
    _, _, recorded = run([Verdict(True, "fine", "{}")])
    assert recorded[0]["error"] is None


def test_brain_reviewer_hands_the_diff_back_without_judging() -> None:
    profile = make_profile(name="low", api_key_env="K", tiers=("openrouter/t0",), reviewer="brain")

    async def attempt(step: Step, number: int, model: str, prompt: str) -> AttemptOutput:
        return output()

    def judge(spec: str, diff: str) -> Verdict:
        raise AssertionError("brain profile must not call the reviewer")

    result = asyncio.run(
        run_step(STEP, profile, attempt=attempt, judge=judge, record=lambda s, d: None)
    )
    assert result.status == "needs_brain_review"


def test_prompt_contains_goal_spec_files_and_feedback() -> None:
    prompt = build_prompt("ship v1", STEP, feedback="missing edge case")
    for text in ("ship v1", "Parser", "write a parser", "parser.py", "missing edge case"):
        assert text in prompt


def test_a_reviewer_error_hands_the_diff_to_the_brain_without_escalating() -> None:
    error = ModelError(TRANSIENT, "http-503", "unavailable")
    result, calls, recorded = run([Verdict(False, "reviewer unavailable", "", error=error)])
    assert result.status == "needs_brain_review"
    assert len(calls) == 1
    assert "unavailable" in result.detail
    assert recorded[0]["review"]["error"] == {
        "kind": TRANSIENT,
        "type": "http-503",
        "message": "unavailable",
    }


def test_a_reviewer_verdict_records_no_error() -> None:
    _, _, recorded = run([Verdict(True, "fine", "{}")])
    assert recorded[0]["review"]["error"] is None


FALLBACK_PROFILE = Profile(
    "medium",
    {
        "openrouter": Provider("openrouter", "https://openrouter.ai/api/v1", "K"),
        "deepseek": Provider("deepseek", "https://api.deepseek.com/v1", "D"),
    },
    (
        ("openrouter/t0",),
        ("openrouter/t1", "openrouter/t1b", "deepseek/t1c"),
        ("openrouter/t2", "deepseek/t2b"),
    ),
    ("openrouter/r",),
)


def failure(kind: str, error_type: str = "provider.x") -> AttemptOutput:
    return output(exit_code=1, error=ModelError(kind, error_type, f"{kind} happened"))


def models(calls: list[tuple[int, str, str]]) -> list[str]:
    return [call[1] for call in calls]


def test_a_transient_error_moves_to_the_next_model_of_the_same_level() -> None:
    result, calls, recorded = run(
        [Verdict(True, "ok", "{}")],
        outputs=[failure(TRANSIENT), output()],
        profile=FALLBACK_PROFILE,
    )
    assert result.status == "approved"
    assert models(calls) == ["openrouter/t1", "openrouter/t1b"]
    assert [entry["tier"] for entry in recorded] == [1, 1]
    assert recorded[0]["error"]["kind"] == TRANSIENT


def test_an_unsuitable_model_moves_to_the_next_model_of_the_same_level() -> None:
    result, calls, _ = run(
        [Verdict(True, "ok", "{}")],
        outputs=[failure(MODEL_UNSUITABLE), output()],
        profile=FALLBACK_PROFILE,
    )
    assert result.status == "approved"
    assert models(calls) == ["openrouter/t1", "openrouter/t1b"]


def test_an_unusable_provider_is_skipped_for_the_rest_of_the_run() -> None:
    state = RunState()
    result, calls, _ = run(
        [Verdict(True, "ok", "{}")],
        outputs=[failure(PROVIDER_UNUSABLE), output()],
        profile=FALLBACK_PROFILE,
        state=state,
    )
    assert result.status == "approved"
    assert models(calls) == ["openrouter/t1", "deepseek/t1c"]
    assert state.excluded_worker_providers == {"openrouter"}

    _, later_calls, _ = run([Verdict(True, "ok", "{}")], profile=FALLBACK_PROFILE, state=state)
    assert models(later_calls) == ["deepseek/t1c"]


def test_a_level_exhausted_by_errors_makes_the_step_unavailable() -> None:
    result, calls, _ = run(
        [],
        outputs=[failure(TRANSIENT), failure(MODEL_UNSUITABLE), failure(TRANSIENT)],
        profile=FALLBACK_PROFILE,
    )
    assert result.status == "unavailable"
    assert models(calls) == ["openrouter/t1", "openrouter/t1b", "deepseek/t1c"]
    assert "deepseek/t1c" in result.detail


def test_a_level_whose_providers_are_all_excluded_is_unavailable_without_attempts() -> None:
    state = RunState(excluded_worker_providers={"openrouter", "deepseek"})
    result, calls, _ = run([], profile=FALLBACK_PROFILE, state=state)
    assert result.status == "unavailable"
    assert calls == []
    assert "excluded" in result.detail


def test_an_unclassified_error_fails_without_trying_the_fallbacks() -> None:
    result, calls, _ = run([], outputs=[failure(UNCLASSIFIED)], profile=FALLBACK_PROFILE)
    assert result.status == "failed"
    assert models(calls) == ["openrouter/t1"]


def test_a_rejection_escalates_to_the_first_model_of_the_next_level() -> None:
    result, calls, _ = run(
        [Verdict(False, "no tests", "{}"), Verdict(True, "ok", "{}")],
        profile=FALLBACK_PROFILE,
    )
    assert result.status == "approved"
    assert models(calls) == ["openrouter/t1", "openrouter/t2"]


def test_a_fallback_after_a_rejection_keeps_the_review_feedback() -> None:
    result, calls, _ = run(
        [Verdict(False, "no tests", "{}"), Verdict(True, "ok", "{}")],
        outputs=[output(), failure(TRANSIENT), output()],
        profile=FALLBACK_PROFILE,
    )
    assert result.status == "approved"
    assert models(calls) == ["openrouter/t1", "openrouter/t2", "deepseek/t2b"]
    assert "no tests" in calls[2][2]
