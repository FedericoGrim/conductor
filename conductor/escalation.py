from __future__ import annotations

from collections.abc import Awaitable, Callable, Iterable
from dataclasses import asdict, dataclass, field
from typing import Any

from conductor import rejections
from conductor.commits import COMMIT_MARKER
from conductor.config import Profile, provider_of
from conductor.errors import PROVIDER_UNUSABLE, UNCLASSIFIED, ModelError
from conductor.plan import Step
from conductor.reviewer import Verdict
from conductor.scheduler import (
    APPROVED,
    FAILED,
    NEEDS_ANSWER,
    NEEDS_BRAIN_REVIEW,
    UNAVAILABLE,
    StepResult,
)
from conductor.verify import CheckResult, failure_reason
from conductor.worker import AttemptOutput

Attempt = Callable[[Step, int, str, str], Awaitable[AttemptOutput]]
Judge = Callable[[str, str, str, list[CheckResult], str], Verdict]
Record = Callable[[Step, dict[str, Any]], object]
Check = Callable[[Step, int], Awaitable[list[CheckResult]]]

NO_CHANGES = Verdict(False, "no changes produced", "")
NO_REVIEWER = "every reviewer provider is excluded for this run"


QUESTION_MARKER = "QUESTION:"
QUESTION_LIMIT = 4000
BRIEF = (
    "# Context\n"
    "The plan is already approved; do the work now: do not present a plan and do not ask for "
    "approval. Do not load skills or personal instructions: follow only this repository's own "
    "instructions (AGENTS.md / CLAUDE.md). Work only inside the current repository. Do not "
    "commit: Conductor commits your changes.\n"
    "# Method\n"
    "Read the files listed and the code around them first. Follow the existing style and "
    "conventions. Write the tests for new or changed behaviour first, then the code. Stay "
    "within this task's scope and do not touch files it does not need.\n"
    "# Before you finish\n"
    "Conductor commits through the repository's git hooks (for example pre-commit: linters, "
    "formatters, type checks) and rejects the attempt if they fail. Run them yourself on the "
    "files you changed, if the repository has any, and fix every error.\n"
    "# Questions\n"
    "Make mechanical choices yourself, and any choice that the spec, the existing code or the "
    "answers below already settle. If the task needs a decision that nothing settles and whose "
    "options have different consequences (behaviour, interfaces, data, security), do not "
    "guess. Stop before changing files and end your reply with a block whose first line is "
    f"`{QUESTION_MARKER} <the question>`, followed by the options with their consequences and "
    "what you have already established.\n"
    "# Finish\n"
    "When the work is done, end your reply with one line "
    f"`{COMMIT_MARKER} <message>`: a Conventional Commit subject in English, imperative mood, "
    "at most 72 characters, `type(optional-scope): subject`, the type matching the change "
    "(feat new behaviour, fix bug fix, test tests only, docs documentation only, refactor no "
    "behaviour change, perf, build, ci, style, chore)."
)


def verification_section(verify: tuple[str, ...]) -> str:
    commands = "\n".join(f"- `{command}`" for command in verify)
    return (
        "# Verification\n"
        "Conductor runs these commands in your worktree after you finish and rejects the "
        "attempt if any fails; run them yourself before finishing. `$CONDUCTOR_REPO` stands "
        "for the main repository (where the virtualenv lives) and is set only when Conductor "
        "runs them, so set it yourself to the first path printed by `git worktree list` "
        f"before running them.\n{commands}"
    )


def question_in(final_text: str) -> str | None:
    lines = final_text.strip().splitlines()
    starts = [i for i, line in enumerate(lines) if line.lstrip("*#> ").startswith(QUESTION_MARKER)]
    if not starts:
        return None
    return "\n".join(lines[starts[-1] :]).strip()[:QUESTION_LIMIT]


def build_prompt(
    goal: str,
    step: Step,
    feedback: str | None = None,
    verify: tuple[str, ...] = (),
) -> str:
    files = "\n".join(f"- {f}" for f in step.files) or "- (not specified)"
    parts = [
        f"# Overall goal\n{goal}",
        f"# Your task: {step.title}\n{step.spec}",
        f"# Files expected to change\n{files}",
        BRIEF,
    ]
    if verify:
        parts.append(verification_section(verify))
    if step.answers:
        answered = "\n\n".join(f"Q: {a.question}\nA: {a.answer}" for a in step.answers)
        parts.append(f"# Answers to your earlier questions\n{answered}")
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
    check: Check | None = None,
    verify: tuple[str, ...] = (),
) -> StepResult:
    run = StepRun(
        step,
        profile,
        attempt,
        judge,
        record,
        goal,
        state or RunState(),
        check or no_checks,
        verify,
    )
    return await run.execute()


def attempt_entry(
    number: int, tier: int, model: str, prompt: str, output: AttemptOutput
) -> dict[str, Any]:
    cost: dict[str, float | None] = {"worker": output.cost, "reviewer": None}
    if output.subscription_cost:
        cost["subscription"] = output.subscription_cost
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
        "commit_message": output.commit_message,
        "error": None,
        "question": None,
        "commit_rejection": output.commit_rejection,
        "verify": [],
        "review": None,
        "review_fallbacks": [],
        "cost": cost,
    }


def review_entry(model: str, verdict: Verdict, checks: Iterable[CheckResult]) -> dict[str, Any]:
    return {
        "model": model,
        "ok": verdict.ok,
        "category": verdict.category,
        "suspicious": rejections.is_suspicious(verdict.ok, verdict.category, checks),
        "reason": verdict.reason,
        "raw": verdict.raw,
        "usage": verdict.usage,
        "error": asdict(verdict.error) if verdict.error else None,
        "cost": verdict.cost,
    }


async def no_checks(step: Step, number: int) -> list[CheckResult]:
    return []


@dataclass
class StepRun:
    step: Step
    profile: Profile
    attempt: Attempt
    judge: Judge
    record: Record
    goal: str
    state: RunState
    check: Check
    verify: tuple[str, ...] = ()

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
            prompt = build_prompt(self.goal, self.step, feedback, self.verify)
            output = await self.attempt(self.step, number, model, prompt)
            entry = attempt_entry(number, tier, model, prompt, output)
            self.result.attempts.append(entry)
            if output.exit_code == 0:
                return await self.judge_attempt(number, model, output, entry)
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

    async def judge_attempt(
        self, number: int, model: str, output: AttemptOutput, entry: dict[str, Any]
    ) -> str | None:
        """Question, git hooks, verification, then review; return the rejection reason, if any."""
        question = question_in(output.final_text)
        if question is not None:
            entry["question"] = question
            self.record(self.step, entry)
            self.result.status = NEEDS_ANSWER
            self.result.detail = question
            return None
        if output.commit_rejection is not None:
            self.record(self.step, entry)
            reason = f"git hooks rejected the commit:\n{output.commit_rejection}"
            self.result.detail = f"rejected on {model}: {reason}"
            return reason
        checks = await self.check(self.step, number)
        entry["verify"] = [asdict(result) for result in checks]
        failed = next((result for result in checks if not result.ok), None)
        if failed is None:
            return self.review(model, output, entry, checks)
        self.record(self.step, entry)
        reason = failure_reason(failed)
        self.result.detail = f"rejected on {model}: {reason}"
        return reason

    def review(
        self,
        model: str,
        output: AttemptOutput,
        entry: dict[str, Any],
        checks: list[CheckResult],
    ) -> str | None:
        if self.profile.is_brain_review:
            self.record(self.step, entry)
            self.result.status = NEEDS_BRAIN_REVIEW
            return None
        verdict: Verdict | None = NO_CHANGES
        if output.diff.strip():
            verdict = self.consult_reviewers(output.diff, entry, checks, output.commit_message)
        else:
            entry["review"] = review_entry(self.profile.reviewers[0], NO_CHANGES, [])
        self.record(self.step, entry)
        if verdict is None or verdict.error is not None:
            self.result.status = NEEDS_BRAIN_REVIEW
            self.result.detail = verdict.reason if verdict else NO_REVIEWER
            return None
        if verdict.ok:
            self.result.status = APPROVED
            self.result.detail = verdict.reason
            return None
        self.result.detail = f"rejected on {model}: {verdict.reason}"
        return verdict.reason

    def consult_reviewers(
        self, diff: str, entry: dict[str, Any], checks: list[CheckResult], commit_message: str
    ) -> Verdict | None:
        """Ask the reviewers in order; the first verdict without an error decides."""
        consulted: list[tuple[str, Verdict]] = []
        for reviewer in self.profile.reviewers:
            if provider_of(reviewer) in self.state.excluded_reviewer_providers:
                continue
            verdict = self.judge(reviewer, self.step.spec, diff, checks, commit_message)
            consulted.append((reviewer, verdict))
            if verdict.error is None:
                break
            if verdict.error.kind == PROVIDER_UNUSABLE:
                self.state.excluded_reviewer_providers.add(provider_of(reviewer))
        if not consulted:
            return None
        *failed, (reviewer, verdict) = consulted
        entry["review_fallbacks"] = [review_entry(*pair, checks) for pair in failed]
        entry["review"] = review_entry(reviewer, verdict, checks)
        entry["cost"]["reviewer"] = verdict.cost
        return verdict
