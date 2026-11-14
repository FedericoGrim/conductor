from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from conductor.config import Profile, provider_of
from conductor.errors import (
    MODEL_UNSUITABLE,
    PROVIDER_UNUSABLE,
    TRANSIENT,
    UNCLASSIFIED,
    ModelError,
    mentions_context_limit,
)
from conductor.privacy import (
    PI_AGENT_DIR,
    api_model_id,
    opencode_config,
    pi_config,
    write_pi_config,
)
from conductor.worker import Events, Harness, exclude_from_git, no_environment

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


def repository_instructions(worktree: Path) -> dict[str, Any]:
    """OpenCode 2 reads AGENTS.md only: point it at CLAUDE.md when that is all there is."""
    if (worktree / "CLAUDE.md").is_file() and not (worktree / "AGENTS.md").is_file():
        return {"instructions": ["CLAUDE.md"]}
    return {}


def prepare_opencode(worktree: Path, profile: Profile) -> None:
    write_opencode_config(worktree, opencode_config(profile) | repository_instructions(worktree))


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


CLAUDE_RETRY_SUBTYPE = "api_retry"
CLAUDE_RESULT = "result"
CLAUDE_ASSISTANT = "assistant"
CLAUDE_NETWORK_WORDS = ("network", "timeout", "econn", "connection", "socket")


def prepare_claude_code(worktree: Path, profile: Profile) -> None:
    return None


def claude_build_command(model: str, prompt: str, extra_args: list[str]) -> list[str]:
    return [
        "claude",
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "--no-session-persistence",
        # Load the repository's own rules only: the user's personal skills, commands and
        # hooks must not reach a worker of an unrelated repository.
        "--setting-sources",
        "project",
        "--disable-slash-commands",
        # Writes stay inside the working directories; Bash is the one extra permission a
        # worker needs, and the worktree bounds what it can touch.
        "--permission-mode",
        "acceptEdits",
        "--allowedTools=Bash",
        "--model",
        model.split("/", 1)[-1],
        *extra_args,
        prompt,
    ]


def claude_session_id(events: Events) -> str | None:
    return next((str(event["session_id"]) for event in events if event.get("session_id")), None)


def claude_is_retry(event: dict[str, Any]) -> bool:
    return event.get("type") == "system" and event.get("subtype") == CLAUDE_RETRY_SUBTYPE


def claude_billed_cost(events: Events) -> float:
    # A subscription has no per-token charge: what Claude Code reports is an estimate.
    return 0.0


def claude_subscription_cost(events: Events) -> float:
    for event in reversed(events):
        if event.get("type") == CLAUDE_RESULT:
            reported = event.get("total_cost_usd")
            if isinstance(reported, int | float):
                return float(reported)
    return 0.0


def claude_final_text(events: Events) -> str:
    for event in reversed(events):
        if event.get("type") == CLAUDE_ASSISTANT:
            content = event.get("message", {}).get("content")
            texts = [
                str(block["text"])
                for block in content or []
                if isinstance(block, dict) and block.get("type") == "text"
            ]
            if texts:
                return "\n".join(texts)
        if event.get("type") == CLAUDE_RESULT and isinstance(event.get("result"), str):
            return str(event["result"])
    return ""


def claude_kind(status: Any, message: str) -> str:
    if status in (401, 402, 403):
        return PROVIDER_UNUSABLE
    if status == 429 or (isinstance(status, int) and status >= 500):
        return TRANSIENT
    if status in (400, 413, 404) and mentions_context_limit(message):
        return MODEL_UNSUITABLE
    if status == 404:
        return MODEL_UNSUITABLE
    if status is None and any(word in message.lower() for word in CLAUDE_NETWORK_WORDS):
        return TRANSIENT
    return UNCLASSIFIED


def claude_error(events: Events, exit_code: int, stderr: str) -> ModelError | None:
    result = next((e for e in reversed(events) if e.get("type") == CLAUDE_RESULT), None)
    if result is not None and result.get("is_error"):
        status = result.get("api_error_status")
        message = str(result.get("result") or result.get("terminal_reason") or "")
        label = status or result.get("terminal_reason") or "error"
        return ModelError.of(claude_kind(status, message), f"claude-{label}", message)
    if exit_code != 0:
        retries = [event for event in events if claude_is_retry(event)]
        if retries:
            last = retries[-1]
            status, message = last.get("error_status"), str(last.get("error", ""))
            return ModelError.of(
                claude_kind(status, message), f"claude-{status or message}", message
            )
        return ModelError.of(UNCLASSIFIED, f"exit {exit_code}", stderr)
    return None


PI_SESSION = "session"
PI_TURN_END = "turn_end"
PI_AGENT_END = "agent_end"
PI_RETRY_START = "auto_retry_start"
PI_RETRY_END = "auto_retry_end"
PI_ASSISTANT = "assistant"
PI_TEXT_BLOCK = "text"
# Pi reports API errors as strings, and the OpenAI-compatible client prefixes the HTTP
# status to the text ("401 Incorrect API key provided", "Connection error.").
PI_STATUS_CODE = re.compile(r"\b[45]\d{2}\b")


def pi_command(model: str, prompt: str, extra_args: list[str]) -> list[str]:
    return [
        "pi",
        "--mode",
        "json",
        "--no-session",
        # The user's personal skills, extensions, prompt templates and themes must not reach
        # a worker of an unrelated repository; the target's AGENTS.md/CLAUDE.md stay on.
        "--no-skills",
        "--no-extensions",
        "--no-prompt-templates",
        "--no-themes",
        "--tools",
        "read,bash,edit,write",
        "--model",
        api_model_id(provider_of(model), model),
        *extra_args,
        prompt,
    ]


def pi_environment(worktree: Path) -> dict[str, str]:
    return {"PI_CODING_AGENT_DIR": str(worktree / PI_AGENT_DIR)}


def pi_prepare(worktree: Path, profile: Profile) -> None:
    write_pi_config(worktree, pi_config(profile))


def pi_session_id(events: Events) -> str | None:
    return next(
        (
            str(event["id"])
            for event in events
            if event.get("type") == PI_SESSION and event.get("id")
        ),
        None,
    )


def pi_is_retry(event: dict[str, Any]) -> bool:
    return event.get("type") == PI_RETRY_START


def pi_cost(events: Events) -> float:
    total = 0.0
    for event in events:
        if event.get("type") != PI_TURN_END:
            continue
        message = event.get("message")
        usage = message.get("usage") if isinstance(message, dict) else None
        cost = usage.get("cost") if isinstance(usage, dict) else None
        reported = cost.get("total") if isinstance(cost, dict) else None
        if isinstance(reported, int | float):
            total += float(reported)
    return total


def pi_assistant_messages(events: Events) -> list[dict[str, Any]]:
    """Assistant messages, newest first: each turn's message, then agent_end's transcript."""
    messages: list[dict[str, Any]] = []
    for event in reversed(events):
        if event.get("type") != PI_TURN_END:
            continue
        message = event.get("message")
        if isinstance(message, dict) and message.get("role") == PI_ASSISTANT:
            messages.append(message)
    for event in reversed(events):
        if event.get("type") != PI_AGENT_END:
            continue
        transcript = event.get("messages")
        if isinstance(transcript, list):
            messages.extend(
                message
                for message in reversed(transcript)
                if isinstance(message, dict) and message.get("role") == PI_ASSISTANT
            )
    return messages


def pi_message_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    texts = [
        str(block["text"])
        for block in content or []
        if isinstance(block, dict) and block.get("type") == PI_TEXT_BLOCK
    ]
    return "\n".join(texts)


def pi_final_text(events: Events) -> str:
    for message in pi_assistant_messages(events):
        text = pi_message_text(message)
        if text:
            return text
    return ""


def pi_status(message: str) -> int | None:
    match = PI_STATUS_CODE.search(message)
    return int(match[0]) if match else None


def pi_kind(status: Any, message: str) -> str:
    """The same word and status tests as the Claude Code classifier."""
    return claude_kind(status, message)


def pi_error(events: Events, exit_code: int, stderr: str) -> ModelError | None:
    """Classify a failed attempt from the final error text in its stream.

    Pi reports errors as strings that carry the HTTP status in their text when there is
    one: the last auto_retry_end's finalError first, then the last assistant messages'
    stopReason/errorMessage; nothing at all is an unclassified exit.
    """
    if exit_code == 0:
        return None
    retry_end = next(
        (event for event in reversed(events) if event.get("type") == PI_RETRY_END),
        None,
    )
    reported: list[str] = []
    if retry_end is not None and retry_end.get("finalError"):
        reported.append(str(retry_end["finalError"]))
    reported.extend(
        str(message.get("errorMessage") or message.get("stopReason") or "")
        for message in pi_assistant_messages(events)
    )
    for message in reported:
        if not message:
            continue
        status = pi_status(message)
        return ModelError.of(pi_kind(status, message), f"pi-{status or 'error'}", message)
    return ModelError.of(UNCLASSIFIED, f"exit {exit_code}", stderr)


OPENCODE = Harness(
    name="opencode",
    prepare=prepare_opencode,
    environment=no_environment,
    command=build_command,
    session_id=session_id,
    is_retry=is_retry,
    cost=events_cost,
    error=attempt_error,
    final_text=final_text,
)

CLAUDE_CODE = Harness(
    name="claude-code",
    prepare=prepare_claude_code,
    environment=no_environment,
    command=claude_build_command,
    session_id=claude_session_id,
    is_retry=claude_is_retry,
    cost=claude_billed_cost,
    error=claude_error,
    final_text=claude_final_text,
    subscription_cost=claude_subscription_cost,
)

PI = Harness(
    name="pi",
    prepare=pi_prepare,
    environment=pi_environment,
    command=pi_command,
    session_id=pi_session_id,
    is_retry=pi_is_retry,
    cost=pi_cost,
    error=pi_error,
    final_text=pi_final_text,
)

HARNESSES = {harness.name: harness for harness in (OPENCODE, CLAUDE_CODE, PI)}


def harness_for(profile: Profile, model: str) -> Harness:
    return HARNESSES[profile.provider_for(model).harness]
