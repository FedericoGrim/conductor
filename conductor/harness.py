from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from conductor.config import Profile
from conductor.errors import (
    MODEL_UNSUITABLE,
    PROVIDER_UNUSABLE,
    TRANSIENT,
    UNCLASSIFIED,
    ModelError,
    mentions_context_limit,
)
from conductor.privacy import opencode_config
from conductor.worker import Events, Harness, exclude_from_git

OPENCODE_CONFIG_NAME = "opencode.json"
ERROR_EVENT = "error"
RETRY_EVENT = "retry"
TEXT_EVENT = "text"

ERROR_KINDS = {
    "provider.rate-limit": TRANSIENT,
    "provider.internal": TRANSIENT,
    "provider.transport": TRANSIENT,
    "provider.auth": PROVIDER_UNUSABLE,
    "provider.quota": PROVIDER_UNUSABLE,
    "provider.no-route": MODEL_UNSUITABLE,
}


def write_opencode_config(worktree: Path, config: dict[str, Any]) -> None:
    (worktree / OPENCODE_CONFIG_NAME).write_text(json.dumps(config, indent=2) + "\n")
    exclude_from_git(worktree, OPENCODE_CONFIG_NAME)


def prepare_opencode(worktree: Path, profile: Profile) -> None:
    write_opencode_config(worktree, opencode_config(profile))


def build_command(model: str, prompt: str, extra_args: list[str]) -> list[str]:
    return [
        "opencode",
        "run",
        "--format",
        "json",
        "-m",
        model,
        "--auto",
        "--archived",
        *extra_args,
        prompt,
    ]


def session_id(events: Events) -> str | None:
    return next((str(e["sessionID"]) for e in events if e.get("sessionID")), None)


def is_retry(event: dict[str, Any]) -> bool:
    return event.get("type") == RETRY_EVENT


def events_cost(events: Events) -> float:
    total = 0.0
    for event in events:
        part = event.get("part")
        cost = part.get("cost") if isinstance(part, dict) else None
        if event.get("type") == "step_finish" and isinstance(cost, int | float):
            total += cost
    return total


def final_text(events: Events) -> str:
    for event in reversed(events):
        part = event.get("part")
        if event.get("type") == TEXT_EVENT and isinstance(part, dict):
            return str(part.get("text", ""))
    return ""


def classify_opencode_error(error: dict[str, Any]) -> ModelError:
    error_type = str(error.get("type", ""))
    message = str(error.get("message", ""))
    kind = ERROR_KINDS.get(error_type, UNCLASSIFIED)
    if error_type == "provider.invalid-request" and mentions_context_limit(message):
        kind = MODEL_UNSUITABLE
    return ModelError.of(kind, error_type, message)


def attempt_error(events: Events, exit_code: int, stderr: str) -> ModelError | None:
    if exit_code == 0:
        return None
    reported = [
        event["error"]
        for event in events
        if event.get("type") in (ERROR_EVENT, RETRY_EVENT) and isinstance(event.get("error"), dict)
    ]
    if reported:
        return classify_opencode_error(reported[-1])
    return ModelError.of(UNCLASSIFIED, f"exit {exit_code}", stderr)


OPENCODE = Harness(
    name="opencode",
    prepare=prepare_opencode,
    command=build_command,
    session_id=session_id,
    is_retry=is_retry,
    cost=events_cost,
    error=attempt_error,
    final_text=final_text,
)

HARNESSES = {harness.name: harness for harness in (OPENCODE,)}


def harness_for(profile: Profile, model: str) -> Harness:
    return HARNESSES[profile.provider_for(model).harness]
