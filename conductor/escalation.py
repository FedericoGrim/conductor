from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from typing import Any

from conductor.config import Profile, provider_of
from conductor.errors import PROVIDER_UNUSABLE, UNCLASSIFIED, ModelError
from conductor.plan import Step
from conductor.reviewer import Verdict
from conductor.scheduler import APPROVED, FAILED, NEEDS_BRAIN_REVIEW, UNAVAILABLE, StepResult
from conductor.worker import AttemptOutput

Attempt = Callable[[Step, int, str, str], Awaitable[AttemptOutput]]
Judge = Callable[[str, str], Verdict]
Record = Callable[[Step, dict[str, Any]], object]


def build_prompt(goal: str, step: Step, feedback: str | None = None) -> str:
    files = "\n".join(f"- {f}" for f in step.files) or "- (not specified)"
    parts = [
        f"# Overall goal\n{goal}",
        f"# Your task: {step.title}\n{step.spec}",
        f"# Files expected to change\n{files}",
        "Work only inside the current repository. Do not ask questions; make reasonable "
        "choices and finish the task. Do not commit.",
    ]
    if feedback:
        parts.append(
            "# Review feedback on a previous attempt\n"
            f"A reviewer rejected an earlier implementation for this reason:\n{feedback}\n"
            "Address it."
        )
    return "\n\n".join(parts)


@dataclass
class RunState:
    excluded_worker_providers: set[str] = field(default_factory=set)
    excluded_reviewer_providers: set[str] = field(default_factory=set)


async def run_step(
    step: Step,
    profile: Profile,
    attempt: Attempt,
    judge: Judge,
    record: Record,
    goal: str = "",
    state: RunState | None = None,
) -> StepResult:
    run = StepRun(step, profile, attempt, judge, record, goal, state or RunState())
    return await run.execute()


def attempt_entry(
    number: int, tier: int, model: str, prompt: str, output: AttemptOutput
) -> dict[str, Any]:
    return {
        "attempt": number,
        "tier": tier,
        "model": model,
        "prompt": prompt,
        "exit_code": output.exit_code,
        "session_id": output.session_id,
        "command": output.command,
        "events": output.events,
        "stderr": output.stderr,
        "diff": output.diff,
        "error": None,
        "review": None,
        "cost": {"worker": output.cost, "reviewer": None},
    }


@dataclass
class StepRun:
    step: Step
    profile: Profile
    attempt: Attempt
    judge: Judge
    record: Record
    goal: str
    state: RunState

    def __post_init__(self) -> None:
        self.result = StepResult(self.step.id, FAILED)

    async def execute(self) -> StepResult:
        tier = min(self.step.difficulty - 1, len(self.profile.tiers) - 1)
        feedback: str | None = None
        while tier < len(self.profile.tiers):
            rejection = await self.run_level(tier, feedback)
            if rejection is None:
                return self.result
            feedback = rejection
            tier += 1
        return self.result

    async def run_level(self, tier: int, feedback: str | None) -> str | None:
        """Try the models of one level in order; return the rejection reason, or None when done."""
        last_error = f"level {tier + 1}: every provider is excluded for this run"
        for model in self.profile.models_for_tier(tier):
            if provider_of(model) in self.state.excluded_worker_providers:
                continue
            number = len(self.result.attempts) + 1
            prompt = build_prompt(self.goal, self.step, feedback)
            output = await self.attempt(self.step, number, model, prompt)
            entry = attempt_entry(number, tier, model, prompt, output)
            self.result.attempts.append(entry)
            if output.exit_code == 0:
                return self.review(model, output, entry)
            error = output.error or ModelError.of(
                UNCLASSIFIED, f"exit {output.exit_code}", output.stderr
            )
            entry["error"] = asdict(error)
            self.record(self.step, entry)
            last_error = f"{model}: {error.describe()}"
            if error.kind == UNCLASSIFIED:
                self.result.detail = last_error
                return None
            if error.kind == PROVIDER_UNUSABLE:
                self.state.excluded_worker_providers.add(provider_of(model))
        self.result.status = UNAVAILABLE
        self.result.detail = last_error
        return None

    def review(self, model: str, output: AttemptOutput, entry: dict[str, Any]) -> str | None:
        if self.profile.is_brain_review:
            self.record(self.step, entry)
            self.result.status = NEEDS_BRAIN_REVIEW
            return None
        verdict = (
            Verdict(False, "no changes produced", "")
            if not output.diff.strip()
            else self.judge(self.step.spec, output.diff)
        )
        entry["review"] = {
            "model": self.profile.reviewers[0],
            "ok": verdict.ok,
            "reason": verdict.reason,
            "raw": verdict.raw,
            "usage": verdict.usage,
            "error": asdict(verdict.error) if verdict.error else None,
        }
        entry["cost"]["reviewer"] = verdict.cost
        self.record(self.step, entry)
        if verdict.error is not None:
            self.result.status = NEEDS_BRAIN_REVIEW
            self.result.detail = verdict.reason
            return None
        if verdict.ok:
            self.result.status = APPROVED
            self.result.detail = verdict.reason
            return None
        self.result.detail = f"rejected on {model}: {verdict.reason}"
        return verdict.reason
