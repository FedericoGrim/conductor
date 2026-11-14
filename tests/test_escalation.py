import asyncio
from dataclasses import replace
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
from conductor.plan import Answer, Step
from conductor.reviewer import Verdict
from conductor.verify import CheckResult
from conductor.worker import AttemptOutput
from tests.factories import make_profile

PROFILE = make_profile(api_key_env="K")
STEP = Step("s1", "Parser", "write a parser", ("parser.py",), 2, ())


def output(
    diff: str = "+code",
    exit_code: int = 0,
    cost: float = 0.0,
    error: ModelError | None = None,
    commit_rejection: str | None = None,
    commit_message: str = "",
) -> AttemptOutput:
    return AttemptOutput(
        exit_code=exit_code,
        session_id="ses",
        events=[],
        diff=diff,
        cost=cost,
        error=error,
        commit_rejection=commit_rejection,
        commit_message=commit_message,
    )


def run(
    verdicts: list[Verdict],
    outputs: list[AttemptOutput] | None = None,
    profile: Profile = PROFILE,
    state: RunState | None = None,
    reviewed: list[str] | None = None,
    checks: list[list[CheckResult]] | None = None,
    checked: list[int] | None = None,
    judged_checks: list[list[CheckResult]] | None = None,
    judged_messages: list[str] | None = None,
) -> Any:
    calls: list[tuple[int, str, str]] = []
    recorded: list[dict[str, Any]] = []
    outputs = outputs or [output() for _ in verdicts]
    judged = list(reversed(range(len(verdicts))))
    reviewed = [] if reviewed is None else reviewed
    judged_checks = [] if judged_checks is None else judged_checks
    judged_messages = [] if judged_messages is None else judged_messages

    async def attempt(step: Step, number: int, model: str, prompt: str) -> AttemptOutput:
        calls.append((number, model, prompt))
        return outputs[number - 1]

    def judge(
        model: str, spec: str, diff: str, checks: list[CheckResult], commit_message: str
    ) -> Verdict:
        reviewed.append(model)
        judged_checks.append(checks)
        judged_messages.append(commit_message)
        return verdicts[judged.pop()]

    def record(step: Step, data: dict[str, Any]) -> None:
        recorded.append(data)

    async def check(step: Step, number: int) -> list[CheckResult]:
        if checked is not None:
            checked.append(number)
        return checks.pop(0) if checks else []

    result = asyncio.run(
        run_step(
            STEP,
            profile,
            attempt=attempt,
            judge=judge,
            record=record,
            state=state or RunState(),
            check=check,
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

    def judge(
        model: str, spec: str, diff: str, checks: list[CheckResult], commit_message: str
    ) -> Verdict:
        raise AssertionError("brain profile must not call the reviewer")

    result = asyncio.run(
        run_step(STEP, profile, attempt=attempt, judge=judge, record=lambda s, d: None)
    )
    assert result.status == "needs_brain_review"


def test_prompt_contains_goal_spec_files_and_feedback() -> None:
    prompt = build_prompt("ship v1", STEP, feedback="missing edge case")
    for text in ("ship v1", "Parser", "write a parser", "parser.py", "missing edge case"):
        assert text in prompt


def test_the_brief_sets_context_method_hooks_questions_and_commit() -> None:
    prompt = build_prompt("ship v1", STEP)
    assert "already approved" in prompt
    assert "tests for new or changed behaviour first" in prompt
    assert "git hooks" in prompt
    assert "QUESTION:" in prompt
    assert "COMMIT:" in prompt


def test_verify_commands_appear_in_the_prompt() -> None:
    prompt = build_prompt("ship v1", STEP, verify=("pytest -q", "ruff check ."))
    assert "# Verification" in prompt
    assert "- `pytest -q`" in prompt
    assert "- `ruff check .`" in prompt
    assert "run them yourself before finishing" in prompt
    assert "$CONDUCTOR_REPO" in prompt
    assert "git worktree list" in prompt


def test_no_verification_section_without_verify_commands() -> None:
    prompt = build_prompt("ship v1", STEP)
    assert "# Verification" not in prompt


def test_run_step_forwards_the_verify_commands_to_the_prompt() -> None:
    prompts: list[str] = []

    async def attempt(step: Step, number: int, model: str, prompt: str) -> AttemptOutput:
        prompts.append(prompt)
        return output()

    result = asyncio.run(
        run_step(
            STEP,
            PROFILE,
            attempt=attempt,
            judge=lambda *args: Verdict(True, "ok", "{}"),
            record=lambda s, d: None,
            verify=("pytest -q",),
        )
    )
    assert result.status == "approved"
    assert "# Verification" in prompts[0]
    assert "- `pytest -q`" in prompts[0]


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


def test_a_classified_error_with_exit_code_zero_is_a_failed_attempt() -> None:
    result, calls, recorded = run(
        [Verdict(True, "ok", "{}")],
        outputs=[
            output(diff="", exit_code=0, error=ModelError(TRANSIENT, "pi-429", "rate limited")),
            output(),
        ],
        profile=FALLBACK_PROFILE,
    )
    assert result.status == "approved"
    assert models(calls) == ["openrouter/t1", "openrouter/t1b"]
    assert recorded[0]["error"]["type"] == "pi-429"


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


REVIEWERS_PROFILE = Profile(
    "medium",
    {
        "openrouter": Provider("openrouter", "https://openrouter.ai/api/v1", "K"),
        "deepseek": Provider("deepseek", "https://api.deepseek.com/v1", "D"),
    },
    (("openrouter/t0",), ("openrouter/t1",), ("openrouter/t2",)),
    ("openrouter/r", "openrouter/r2", "deepseek/r3"),
)


def reviewer_error(kind: str, reason: str = "reviewer broke") -> Verdict:
    return Verdict(False, reason, "", usage={"cost": 0.001}, error=ModelError(kind, "x", reason))


def test_an_unparseable_verdict_moves_to_the_next_reviewer_without_costing_a_level() -> None:
    reviewed: list[str] = []
    result, calls, recorded = run(
        [reviewer_error(MODEL_UNSUITABLE, "unparseable verdict"), Verdict(True, "ok", "{}")],
        profile=REVIEWERS_PROFILE,
        reviewed=reviewed,
    )
    assert result.status == "approved"
    assert models(calls) == ["openrouter/t1"]
    assert reviewed == ["openrouter/r", "openrouter/r2"]
    assert recorded[0]["review"]["model"] == "openrouter/r2"
    fallback = recorded[0]["review_fallbacks"][0]
    assert fallback["model"] == "openrouter/r"
    assert fallback["error"]["kind"] == MODEL_UNSUITABLE
    assert fallback["cost"] == 0.001


def test_an_unusable_reviewer_provider_is_skipped_for_the_rest_of_the_run() -> None:
    state = RunState()
    reviewed: list[str] = []
    run(
        [reviewer_error(PROVIDER_UNUSABLE), Verdict(True, "ok", "{}")],
        profile=REVIEWERS_PROFILE,
        state=state,
        reviewed=reviewed,
    )
    assert reviewed == ["openrouter/r", "deepseek/r3"]
    assert state.excluded_reviewer_providers == {"openrouter"}
    assert state.excluded_worker_providers == set()


def test_every_reviewer_failing_hands_the_diff_to_the_brain() -> None:
    result, calls, recorded = run(
        [reviewer_error(TRANSIENT), reviewer_error(TRANSIENT), reviewer_error(TRANSIENT, "last")],
        profile=REVIEWERS_PROFILE,
    )
    assert result.status == "needs_brain_review"
    assert len(calls) == 1
    assert "last" in result.detail
    assert recorded[0]["review"]["model"] == "deepseek/r3"
    assert recorded[0]["review"]["error"]["kind"] == TRANSIENT
    assert len(recorded[0]["review_fallbacks"]) == 2


def test_no_usable_reviewer_hands_the_diff_to_the_brain_without_a_call() -> None:
    state = RunState(excluded_reviewer_providers={"openrouter", "deepseek"})
    reviewed: list[str] = []
    result, _, recorded = run(
        [], outputs=[output()], profile=REVIEWERS_PROFILE, state=state, reviewed=reviewed
    )
    assert result.status == "needs_brain_review"
    assert reviewed == []
    assert "excluded" in result.detail
    assert recorded[0]["review"] is None


QUESTION = "QUESTION: Should names be case-sensitive?\nA) yes: simpler\nB) no: fold case"


def asking(question: str = QUESTION) -> AttemptOutput:
    answer = output(diff="+partial")
    answer.final_text = f"I read parser.py and the tests.\n\n{question}"
    return answer


def test_a_worker_question_stops_the_step_without_review_or_escalation() -> None:
    reviewed: list[str] = []
    result, calls, recorded = run([], outputs=[asking()], reviewed=reviewed)
    assert result.status == "needs_answer"
    assert result.detail == QUESTION
    assert len(calls) == 1
    assert reviewed == []
    assert recorded[0]["question"] == QUESTION
    assert recorded[0]["review"] is None


def test_a_question_wins_over_the_brain_review() -> None:
    profile = make_profile(name="low", api_key_env="K", tiers=("openrouter/t0",), reviewer="brain")
    result, _, _ = run([], outputs=[asking()], profile=profile)
    assert result.status == "needs_answer"


def test_a_question_that_is_not_the_final_text_does_not_stop_the_step() -> None:
    finished = output()
    finished.final_text = "Done. Earlier I wondered (QUESTION: inline) but the spec settles it."
    result, _, _ = run([Verdict(True, "ok", "{}")], outputs=[finished])
    assert result.status == "approved"


def test_a_step_with_answers_puts_them_in_the_prompt_and_reaches_the_reviewer() -> None:
    answered = replace(STEP, answers=(Answer("Should names be case-sensitive?", "No, fold case."),))
    reviewed: list[str] = []
    calls: list[str] = []

    async def attempt(step: Step, number: int, model: str, prompt: str) -> AttemptOutput:
        calls.append(prompt)
        return output()

    def judge(
        model: str, spec: str, diff: str, checks: list[CheckResult], commit_message: str
    ) -> Verdict:
        reviewed.append(model)
        return Verdict(True, "ok", "{}")

    result = asyncio.run(
        run_step(answered, PROFILE, attempt=attempt, judge=judge, record=lambda s, d: None)
    )
    assert result.status == "approved"
    assert reviewed == ["openrouter/r"]
    assert "Should names be case-sensitive?" in calls[0]
    assert "No, fold case." in calls[0]


def test_the_prompt_asks_for_a_question_instead_of_a_guess() -> None:
    prompt = build_prompt("ship v1", STEP)
    assert "Do not ask questions" not in prompt
    assert "QUESTION:" in prompt
    assert "Answers to your earlier questions" not in prompt


PASSED = CheckResult("pytest -q", 0, "3 passed", 1.0)
FAILED_CHECK = CheckResult("pytest -q", 1, "1 failed: test_total_is_never_negative", 1.0)


def test_a_failed_check_rejects_the_attempt_without_calling_the_reviewer() -> None:
    reviewed: list[str] = []
    result, calls, recorded = run(
        [Verdict(True, "ok", "{}")],
        outputs=[output(), output()],
        reviewed=reviewed,
        checks=[[PASSED, FAILED_CHECK], [PASSED]],
    )
    assert result.status == "approved"
    assert [c[1] for c in calls] == ["openrouter/t1", "openrouter/t2"]
    assert reviewed == ["openrouter/r"]
    assert recorded[0]["review"] is None
    assert recorded[0]["verify"][1]["exit_code"] == 1
    assert "test_total_is_never_negative" in calls[1][2]


def test_a_failed_check_on_the_last_level_fails_the_step() -> None:
    result, _, _ = run([], checks=[[FAILED_CHECK], [FAILED_CHECK]], outputs=[output(), output()])
    assert result.status == "failed"
    assert "verification failed: `pytest -q` (exit 1)" in result.detail


def test_passing_checks_are_recorded_before_the_review() -> None:
    _, _, recorded = run([Verdict(True, "ok", "{}")], checks=[[PASSED]])
    assert recorded[0]["verify"] == [
        {
            "command": "pytest -q",
            "exit_code": 0,
            "output": "3 passed",
            "seconds": 1.0,
            "timed_out": False,
        }
    ]


def test_the_brain_only_receives_verified_diffs() -> None:
    profile = make_profile(
        name="low",
        api_key_env="K",
        tiers=("openrouter/t0", "openrouter/t1", "openrouter/t2"),
        reviewer="brain",
    )
    result, calls, _ = run(
        [], outputs=[output(), output()], profile=profile, checks=[[FAILED_CHECK], [PASSED]]
    )
    assert result.status == "needs_brain_review"
    assert len(calls) == 2


def test_a_question_runs_no_checks() -> None:
    checked: list[int] = []
    run([], outputs=[asking()], checked=checked)
    assert checked == []


def test_the_reviewer_receives_the_checks_that_passed() -> None:
    judged_checks: list[list[CheckResult]] = []
    run([Verdict(True, "ok", "{}")], checks=[[PASSED]], judged_checks=judged_checks)
    assert judged_checks == [[PASSED]]


def test_a_subscription_cost_is_recorded_apart_from_the_billed_cost() -> None:
    subscribed = output(cost=0.0)
    subscribed.subscription_cost = 0.012
    _, _, recorded = run([Verdict(True, "ok", "{}")], outputs=[subscribed])
    assert recorded[0]["cost"] == {
        "worker": 0.0,
        "reviewer": None,
        "subscription": pytest.approx(0.012),
    }


def test_a_commit_rejected_by_a_hook_rejects_the_attempt_with_the_hook_output() -> None:
    reviewed: list[str] = []
    checked: list[int] = []
    result, calls, recorded = run(
        [Verdict(True, "ok", "{}")],
        outputs=[output(diff="", commit_rejection="ruff: F401 unused import"), output()],
        reviewed=reviewed,
        checked=checked,
    )
    assert result.status == "approved"
    assert [c[1] for c in calls] == ["openrouter/t1", "openrouter/t2"]
    assert reviewed == ["openrouter/r"]
    assert checked == [2]
    assert recorded[0]["commit_rejection"] == "ruff: F401 unused import"
    assert "git hooks rejected the commit" in calls[1][2]
    assert "ruff: F401 unused import" in calls[1][2]


def test_a_commit_rejected_on_the_last_level_fails_the_step() -> None:
    rejected = output(diff="", commit_rejection="mypy: error")
    result, _, _ = run([], outputs=[rejected, rejected])
    assert result.status == "failed"
    assert "git hooks rejected the commit" in result.detail


def test_the_attempt_entry_records_the_commit_message() -> None:
    _, _, recorded = run(
        [Verdict(True, "ok", "{}")],
        outputs=[output(commit_message="feat(parser): scan the input")],
    )
    assert recorded[0]["commit_message"] == "feat(parser): scan the input"


def test_the_judge_receives_the_attempts_commit_message() -> None:
    judged_messages: list[str] = []
    run(
        [Verdict(True, "ok", "{}")],
        outputs=[output(commit_message="feat(parser): scan the input")],
        judged_messages=judged_messages,
    )
    assert judged_messages == ["feat(parser): scan the input"]


def test_the_attempt_entry_records_the_rejection_category_and_suspicion() -> None:
    passed = CheckResult("mypy conductor", 0, "", 1.0)
    verdict = Verdict(False, "wrong type", "{}", category="types")
    _, _, recorded = run([verdict, Verdict(True, "ok", "{}")], checks=[[passed], []])
    review = recorded[0]["review"]
    assert review["category"] == "types"
    assert review["suspicious"] is True


def test_a_judgement_rejection_is_not_suspicious() -> None:
    passed = CheckResult("mypy conductor", 0, "", 1.0)
    verdict = Verdict(False, "misses the spec", "{}", category="spec")
    _, _, recorded = run([verdict, Verdict(True, "ok", "{}")], checks=[[passed], []])
    review = recorded[0]["review"]
    assert review["category"] == "spec"
    assert review["suspicious"] is False


def suspicious_rejection(reason: str, cost: float) -> Verdict:
    return Verdict(False, reason, "{}", usage={"cost": cost}, category="imports")


def test_a_suspicious_rejection_asks_the_next_reviewer_for_a_second_opinion() -> None:
    passed = CheckResult("mypy --strict .", 0, "", 1.0)
    reviewed: list[str] = []
    result, _, recorded = run(
        [
            suspicious_rejection("bad imports", 0.1),
            Verdict(True, "actually fine", "{}", usage={"cost": 0.2}),
        ],
        profile=REVIEWERS_PROFILE,
        reviewed=reviewed,
        checks=[[passed]],
    )
    assert result.status == "approved"
    assert reviewed == ["openrouter/r", "openrouter/r2"]
    assert recorded[0]["review"]["model"] == "openrouter/r2"
    assert recorded[0]["review_fallbacks"][0]["model"] == "openrouter/r"
    assert recorded[0]["second_opinion"]["model"] == "openrouter/r2"
    assert recorded[0]["second_opinion"]["ok"] is True
    assert recorded[0]["cost"]["reviewer"] == 0.2


def test_a_suspicious_rejection_escalates_when_the_second_opinion_also_rejects() -> None:
    passed = CheckResult("mypy --strict .", 0, "", 1.0)
    reviewed: list[str] = []
    result, calls, recorded = run(
        [
            suspicious_rejection("bad imports", 0.1),
            suspicious_rejection("still bad imports", 0.2),
            Verdict(True, "ok", "{}"),
        ],
        profile=REVIEWERS_PROFILE,
        reviewed=reviewed,
        checks=[[passed], [passed]],
    )
    assert result.status == "approved"
    assert models(calls) == ["openrouter/t1", "openrouter/t2"]
    assert "still bad imports" in calls[1][2]
    assert recorded[0]["review"]["model"] == "openrouter/r2"
    assert recorded[0]["second_opinion"]["ok"] is False


def test_a_rejection_that_is_not_suspicious_gets_no_second_opinion() -> None:
    passed = CheckResult("mypy --strict .", 0, "", 1.0)
    reviewed: list[str] = []
    profile = replace(REVIEWERS_PROFILE, tiers=(("openrouter/t0",),))
    result, _, recorded = run(
        [Verdict(False, "bad logic", "{}", category="logic")],
        profile=profile,
        reviewed=reviewed,
        checks=[[passed]],
    )
    assert result.status == "failed"
    assert reviewed == ["openrouter/r"]
    assert recorded[0]["second_opinion"] is None


def test_a_single_reviewer_never_asks_for_a_second_opinion() -> None:
    passed = CheckResult("mypy --strict .", 0, "", 1.0)
    reviewed: list[str] = []
    profile = replace(PROFILE, tiers=(("openrouter/t0",),))
    result, _, recorded = run(
        [suspicious_rejection("bad imports", 0.1)],
        profile=profile,
        reviewed=reviewed,
        checks=[[passed]],
    )
    assert result.status == "failed"
    assert reviewed == ["openrouter/r"]
    assert recorded[0]["second_opinion"] is None


def test_an_errored_second_opinion_does_not_overrule_the_first_rejection() -> None:
    passed = CheckResult("mypy --strict .", 0, "", 1.0)
    reviewed: list[str] = []
    result, calls, recorded = run(
        [
            suspicious_rejection("bad imports", 0.1),
            reviewer_error(TRANSIENT),
            Verdict(True, "ok", "{}"),
        ],
        profile=REVIEWERS_PROFILE,
        reviewed=reviewed,
        checks=[[passed], [passed]],
    )
    assert result.status == "approved"
    assert reviewed == ["openrouter/r", "openrouter/r2", "openrouter/r"]
    assert "bad imports" in calls[1][2]
    assert recorded[0]["review"]["model"] == "openrouter/r"
    assert recorded[0]["second_opinion"]["error"]["kind"] == TRANSIENT
