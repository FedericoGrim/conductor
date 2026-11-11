from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from conductor.config import Profile
from conductor.plan import Step
from conductor.reviewer import Verdict
from conductor.scheduler import APPROVED, FAILED, NEEDS_BRAIN_REVIEW, StepResult
from conductor.worker import AttemptOutput

BRAIN = "brain"

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


async def run_step(
    step: Step,
    profile: Profile,
    attempt: Attempt,
    judge: Judge,
    record: Record,
    goal: str = "",
) -> StepResult:
    result = StepResult(step.id, FAILED)
    tier = min(step.difficulty - 1, len(profile.tiers) - 1)
    feedback: str | None = None
    number = 0
    while (model := profile.model_for_tier(tier)) is not None:
        number += 1
        prompt = build_prompt(goal, step, feedback)
        output = await attempt(step, number, model, prompt)
        entry: dict[str, Any] = {
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
            "review": None,
            "cost": {"worker": output.cost, "reviewer": None},
        }
        result.attempts.append(entry)
        if output.exit_code != 0:
            result.detail = f"opencode exit code {output.exit_code}: {output.stderr.strip()[-500:]}"
            record(step, entry)
            return result
        if profile.reviewer == BRAIN:
            record(step, entry)
            result.status = NEEDS_BRAIN_REVIEW
            return result
        verdict = (
            Verdict(False, "no changes produced", "")
            if not output.diff.strip()
            else judge(step.spec, output.diff)
        )
        entry["review"] = {
            "model": profile.reviewer,
            "ok": verdict.ok,
            "reason": verdict.reason,
            "raw": verdict.raw,
            "usage": verdict.usage,
        }
        entry["cost"]["reviewer"] = verdict.cost
        record(step, entry)
        if verdict.ok:
            result.status = APPROVED
            result.detail = verdict.reason
            return result
        feedback = verdict.reason
        result.detail = f"rejected on {model}: {verdict.reason}"
        tier += 1
    return result
