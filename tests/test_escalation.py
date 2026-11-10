import asyncio
from typing import Any

from conductor.config import Profile
from conductor.escalation import build_prompt, run_step
from conductor.plan import Step
from conductor.reviewer import Verdict
from conductor.worker import AttemptOutput

PROFILE = Profile(
    name="medium",
    provider="openrouter",
    base_url="u",
    api_key_env="K",
    tiers=("openrouter/t0", "openrouter/t1", "openrouter/t2"),
    reviewer="openrouter/r",
)
STEP = Step("s1", "Parser", "write a parser", ("parser.py",), 2, ())


def output(diff: str = "+code", exit_code: int = 0) -> AttemptOutput:
    return AttemptOutput(exit_code=exit_code, session_id="ses", events=[], diff=diff)


def run(verdicts: list[Verdict], outputs: list[AttemptOutput] | None = None) -> Any:
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

    result = asyncio.run(run_step(STEP, PROFILE, attempt=attempt, judge=judge, record=record))
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


def test_opencode_failure_does_not_retry() -> None:
    result, calls, _ = run([], outputs=[output(exit_code=3)])
    assert result.status == "failed"
    assert "exit code 3" in result.detail
    assert len(calls) == 1


def test_brain_reviewer_hands_the_diff_back_without_judging() -> None:
    profile = Profile("low", "openrouter", "u", "K", ("openrouter/t0",), reviewer="brain")

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
