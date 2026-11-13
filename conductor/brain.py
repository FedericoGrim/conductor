from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TokenUsage:
    replies: int = 0
    input: int = 0
    output: int = 0
    reasoning: int = 0
    cache_read: int = 0
    cache_write: int = 0

    def plus(self, other: TokenUsage) -> TokenUsage:
        return TokenUsage(
            replies=self.replies + other.replies,
            input=self.input + other.input,
            output=self.output + other.output,
            reasoning=self.reasoning + other.reasoning,
            cache_read=self.cache_read + other.cache_read,
            cache_write=self.cache_write + other.cache_write,
        )


Exporter = Callable[[str], str | None]


def opencode_export(session_id: str) -> str | None:
    try:
        result = subprocess.run(
            ["opencode", "session", "export", session_id],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def _token_count(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return 0


def _model_name(info: dict[str, Any]) -> str | None:
    model = info.get("model")
    if not isinstance(model, dict):
        return None
    provider_id = model.get("providerID")
    model_id = model.get("id")
    if isinstance(provider_id, str) and provider_id and isinstance(model_id, str) and model_id:
        return f"{provider_id}/{model_id}"
    return None


def _usage(info: dict[str, Any]) -> TokenUsage:
    tokens = info.get("tokens")
    if not isinstance(tokens, dict):
        tokens = {}
    cache = tokens.get("cache")
    if not isinstance(cache, dict):
        cache = {}
    return TokenUsage(
        replies=1,
        input=_token_count(tokens.get("input")),
        output=_token_count(tokens.get("output")),
        reasoning=_token_count(tokens.get("reasoning")),
        cache_read=_token_count(cache.get("read")),
        cache_write=_token_count(cache.get("write")),
    )


def session_tokens(
    session_id: str, export: Exporter = opencode_export
) -> dict[str, TokenUsage] | None:
    text = export(session_id)
    if text is None:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    messages = data.get("messages")
    if not isinstance(messages, list):
        return None
    totals: dict[str, TokenUsage] = {}
    for message in messages:
        if not isinstance(message, dict):
            continue
        info = message.get("info", message)
        if not isinstance(info, dict) or info.get("type") != "assistant":
            continue
        model_name = _model_name(info)
        if model_name is None:
            continue
        totals[model_name] = totals.get(model_name, TokenUsage()).plus(_usage(info))
    return totals
