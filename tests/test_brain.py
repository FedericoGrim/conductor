import json
from pathlib import Path
from typing import Any

import pytest

from conductor.brain import Exporter, TokenUsage, opencode_export, session_tokens


def messages(*items: dict[str, Any]) -> str:
    return json.dumps({"messages": list(items)})


def exporter_for(text: str) -> Exporter:
    return lambda _session_id: text


def assistant(model: dict[str, Any], tokens: dict[str, Any] | None = None) -> dict[str, Any]:
    info: dict[str, Any] = {"type": "assistant", "model": model}
    if tokens is not None:
        info["tokens"] = tokens
    return {"info": info}


def test_totals_are_summed_per_model_across_messages() -> None:
    text = messages(
        assistant(
            {"providerID": "openrouter", "id": "opus"},
            {"input": 10, "output": 5, "reasoning": 2, "cache": {"read": 1, "write": 0}},
        ),
        assistant(
            {"providerID": "openrouter", "id": "opus"},
            {"input": 20, "output": 8, "reasoning": 0, "cache": {"read": 3, "write": 4}},
        ),
        assistant(
            {"providerID": "anthropic", "id": "sonnet"},
            {"input": 7, "output": 3, "reasoning": 1, "cache": {"read": 0, "write": 2}},
        ),
    )
    assert session_tokens("session", exporter_for(text)) == {
        "openrouter/opus": TokenUsage(
            replies=2, input=30, output=13, reasoning=2, cache_read=4, cache_write=4
        ),
        "anthropic/sonnet": TokenUsage(
            replies=1, input=7, output=3, reasoning=1, cache_read=0, cache_write=2
        ),
    }


def test_the_info_wrapper_and_the_flat_form_are_both_read() -> None:
    text = json.dumps(
        {
            "messages": [
                {
                    "info": assistant(
                        {"providerID": "p", "id": "m"},
                        {
                            "input": 1,
                            "output": 2,
                            "reasoning": 3,
                            "cache": {"read": 4, "write": 5},
                        },
                    )["info"]
                },
                {
                    "type": "assistant",
                    "model": {"providerID": "p", "id": "m"},
                    "tokens": {
                        "input": 1,
                        "output": 2,
                        "reasoning": 3,
                        "cache": {"read": 4, "write": 5},
                    },
                },
            ]
        }
    )
    assert session_tokens("session", exporter_for(text)) == {
        "p/m": TokenUsage(replies=2, input=2, output=4, reasoning=6, cache_read=8, cache_write=10)
    }


def test_user_messages_and_messages_without_a_model_are_ignored() -> None:
    text = messages(
        {
            "info": {
                "type": "user",
                "model": {"providerID": "p", "id": "m"},
                "tokens": {"input": 99},
            }
        },
        {"info": {"type": "assistant", "tokens": {"input": 99}}},
        assistant({"providerID": "p", "id": "m"}, {"input": 1}),
    )
    assert session_tokens("session", exporter_for(text)) == {"p/m": TokenUsage(replies=1, input=1)}


def test_missing_and_malformed_token_fields_count_as_zero() -> None:
    text = messages(
        assistant(
            {"providerID": "p", "id": "m"},
            {
                "input": "10",
                "output": None,
                "reasoning": True,
                "cache": {"read": 5.5, "write": "2"},
            },
        ),
        assistant({"providerID": "p", "id": "m"}),
    )
    assert session_tokens("session", exporter_for(text)) == {"p/m": TokenUsage(replies=2)}


def test_malformed_model_fields_are_skipped() -> None:
    text = messages(
        assistant({"providerID": 1, "id": "m"}, {"input": 99}),
        assistant({"providerID": "p", "id": None}, {"input": 99}),
        assistant({"providerID": "", "id": "m"}, {"input": 99}),
        assistant({"providerID": "p", "id": ""}, {"input": 99}),
        assistant({"providerID": "p", "id": "m"}, {"input": 1}),
    )
    assert session_tokens("session", exporter_for(text)) == {"p/m": TokenUsage(replies=1, input=1)}


def test_none_when_the_exporter_returns_none() -> None:
    assert session_tokens("session", lambda _session_id: None) is None


def test_none_for_invalid_json() -> None:
    assert session_tokens("session", exporter_for("not json")) is None


def test_none_for_json_without_a_messages_list() -> None:
    assert session_tokens("session", exporter_for('{"info": {}}')) is None
    assert session_tokens("session", exporter_for("[1, 2, 3]")) is None
    assert session_tokens("session", exporter_for('{"messages": "nope"}')) is None


def test_plus_adds_every_field() -> None:
    left = TokenUsage(replies=1, input=2, output=3, reasoning=4, cache_read=5, cache_write=6)
    right = TokenUsage(replies=10, input=20, output=30, reasoning=40, cache_read=50, cache_write=60)
    assert left.plus(right) == TokenUsage(
        replies=11, input=22, output=33, reasoning=44, cache_read=55, cache_write=66
    )


def test_opencode_export_is_none_when_opencode_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    assert opencode_export("session") is None


def test_opencode_export_returns_the_stdout_of_opencode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    script = bindir / "opencode"
    script.write_text("#!/bin/sh\nprintf '{\"messages\": []}'\n")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", str(bindir))
    assert opencode_export("session") == '{"messages": []}'
