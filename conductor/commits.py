from __future__ import annotations

import re

COMMIT_MARKER = "COMMIT:"
CONVENTIONAL_SUBJECT = re.compile(
    r"^(feat|fix|test|docs|refactor|perf|build|ci|style|chore)(\([a-z0-9-]+\))?!?: .{1,72}$"
)


def is_conventional(subject: str) -> bool:
    return "\n" not in subject and CONVENTIONAL_SUBJECT.fullmatch(subject.strip()) is not None


def commit_line_in(final_text: str) -> str | None:
    result: str | None = None
    for line in final_text.splitlines():
        candidate = line.lstrip("*#> `")
        if candidate.startswith(COMMIT_MARKER):
            remainder = candidate[len(COMMIT_MARKER) :].strip().strip("`*").strip()
            result = remainder or None
    return result


def fallback_subject(step_id: str, number: int) -> str:
    return f"chore(conductor): apply step {step_id} attempt {number}"


def choose_commit_message(
    step_id: str,
    number: int,
    model: str,
    final_text: str,
    planned: str | None = None,
) -> str:
    proposal = commit_line_in(final_text)
    if planned is not None:
        subject = planned
    elif proposal is not None and is_conventional(proposal):
        subject = proposal
    else:
        subject = fallback_subject(step_id, number)
    body = f"Written by a Conductor worker: step {step_id}, attempt {number}, on {model}."
    return f"{subject}\n\n{body}"
