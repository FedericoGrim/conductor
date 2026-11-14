import json
from pathlib import Path
from typing import Any

import pytest

from conductor.config import HARNESS_NAMES, Profile, Provider
from conductor.harness import (
    CLAUDE_CODE,
    HARNESSES,
    OPENCODE,
    PI,
    claude_billed_cost,
    claude_build_command,
    claude_error,
    claude_final_text,
    claude_is_retry,
    claude_session_id,
    claude_subscription_cost,
    harness_for,
    pi_command,
    pi_cost,
    pi_environment,
    pi_error,
    pi_final_text,
    pi_is_retry,
    pi_prepare,
    pi_session_id,
    prepare_opencode,
)
from conductor.worker import Events, git, parse_events
from tests.factories import make_profile


def test_every_harness_name_has_a_harness() -> None:
    assert set(HARNESSES) == set(HARNESS_NAMES)
    assert all(harness.name == name for name, harness in HARNESSES.items())


def test_the_harness_comes_from_the_provider_of_the_model() -> None:
    profile = Profile(
        "medium",
        {"openrouter": Provider("openrouter", "https://openrouter.ai/api/v1", "K")},
        (("openrouter/a",),),
        ("openrouter/a",),
    )
    assert harness_for(profile, "openrouter/a") is OPENCODE


CLAUDE_INIT: dict[str, Any] = {
    "type": "system",
    "subtype": "init",
    "session_id": "abc-123",
    "model": "claude-sonnet-5",
    "permissionMode": "acceptEdits",
}
CLAUDE_ASSISTANT: dict[str, Any] = {
    "type": "assistant",
    "session_id": "abc-123",
    "message": {"content": [{"type": "text", "text": "Done.\n\nQUESTION: fold case?"}]},
}
CLAUDE_RESULT: dict[str, Any] = {
    "type": "result",
    "subtype": "success",
    "is_error": False,
    "session_id": "abc-123",
    "result": "Done.\n\nQUESTION: fold case?",
    "total_cost_usd": 0.012,
}


def retry_event(status: object = 429, error: str = "rate_limit") -> dict[str, Any]:
    return {"type": "system", "subtype": "api_retry", "error_status": status, "error": error}


def test_the_claude_code_command_confines_and_isolates_the_worker() -> None:
    cmd = claude_build_command("subscription/sonnet", "do it", ["--effort", "high"])
    assert cmd[0] == "claude"
    assert cmd[1] == "-p"
    assert cmd[-1] == "do it"
    for flag, value in (
        ("--output-format", "stream-json"),
        ("--setting-sources", "project"),
        ("--permission-mode", "acceptEdits"),
        ("--model", "sonnet"),
    ):
        assert cmd[cmd.index(flag) + 1] == value
    assert "--no-session-persistence" in cmd
    assert "--disable-slash-commands" in cmd
    assert "--allowedTools=Bash" in cmd
    assert cmd.index("--effort") < cmd.index("do it")


def test_claude_code_event_helpers() -> None:
    events = [CLAUDE_INIT, CLAUDE_ASSISTANT, CLAUDE_RESULT]
    assert claude_session_id(events) == "abc-123"
    assert claude_final_text(events) == "Done.\n\nQUESTION: fold case?"
    assert claude_billed_cost(events) == 0.0
    assert claude_subscription_cost(events) == pytest.approx(0.012)
    assert claude_is_retry(retry_event())
    assert not claude_is_retry(CLAUDE_INIT)


def test_final_text_falls_back_to_the_result_message() -> None:
    result = dict(CLAUDE_RESULT, result="from the result event")
    assert claude_final_text([CLAUDE_INIT, result]) == "from the result event"


@pytest.mark.parametrize(
    ("event", "kind"),
    [
        (retry_event(429), "transient"),
        (retry_event(503, "server_error"), "transient"),
        (retry_event(None, "network_error"), "transient"),
        (retry_event(401, "authentication_failed"), "provider_unusable"),
        (retry_event(402, "billing_error"), "provider_unusable"),
    ],
)
def test_retry_events_are_classified(event: dict[str, Any], kind: str) -> None:
    error = claude_error([CLAUDE_INIT, event], exit_code=143, stderr="")
    assert error is not None and error.kind == kind


def test_a_result_error_is_classified_from_its_status() -> None:
    result = dict(
        CLAUDE_RESULT,
        subtype="success",
        is_error=True,
        api_error_status=400,
        result="This model's maximum context length is 8192 tokens",
    )
    error = claude_error([CLAUDE_INIT, result], exit_code=1, stderr="")
    assert error is not None
    assert (error.kind, error.type) == ("model_unsuitable", "claude-400")


def test_an_unclassified_failure_names_the_exit_code() -> None:
    error = claude_error([CLAUDE_INIT], exit_code=2, stderr="boom")
    assert error is not None
    assert (error.kind, error.type) == ("unclassified", "exit 2")


def test_a_successful_run_has_no_error() -> None:
    assert claude_error([CLAUDE_INIT, CLAUDE_RESULT], exit_code=0, stderr="") is None


def test_the_claude_code_harness_is_registered() -> None:
    assert HARNESSES["claude-code"] is CLAUDE_CODE


# Pi 0.73.1 writes one JSON object per line (LF only): the session header first, then the
# agent's events. Hand-written in the captured shape: a session line, a tool call turn, a
# final text turn, and the costs the assistant messages report.
PI_SESSION: dict[str, Any] = {
    "type": "session",
    "version": 3,
    "id": "3f9d6c7e-4a2b-4c1d-9e8f-2b7a6d5c4e3f",
    "timestamp": "2026-11-14T12:00:00.000Z",
    "cwd": "/tmp/wt",
}
PI_USER: dict[str, Any] = {
    "role": "user",
    "content": [{"type": "text", "text": "Run the tests."}],
    "timestamp": 1760421599000,
}


def pi_usage(cost: float) -> dict[str, Any]:
    return {
        "input": 1000,
        "output": 100,
        "cacheRead": 200,
        "cacheWrite": 0,
        "totalTokens": 1300,
        "cost": {
            "input": 0.0,
            "output": 0.0,
            "cacheRead": 0.0,
            "cacheWrite": 0.0,
            "total": cost,
        },
    }


PI_TOOL_ASSISTANT: dict[str, Any] = {
    "role": "assistant",
    "content": [
        {"type": "toolCall", "id": "call_1", "name": "bash", "arguments": {"command": "pytest -q"}}
    ],
    "api": "openai-completions",
    "provider": "openrouter",
    "model": "deepseek/v4",
    "usage": pi_usage(0.0003),
    "stopReason": "toolUse",
    "timestamp": 1760421600000,
}
PI_TOOL_RESULT: dict[str, Any] = {
    "role": "toolResult",
    "toolCallId": "call_1",
    "toolName": "bash",
    "content": [{"type": "text", "text": "1 passed"}],
    "isError": False,
    "timestamp": 1760421600500,
}
PI_TEXT_ASSISTANT: dict[str, Any] = {
    "role": "assistant",
    "content": [{"type": "text", "text": "Tests pass.\n\nCOMMIT: feat(pi): run workers on pi"}],
    "api": "openai-completions",
    "provider": "openrouter",
    "model": "deepseek/v4",
    "usage": pi_usage(0.0004),
    "stopReason": "stop",
    "timestamp": 1760421601000,
}
PI_STREAM: list[dict[str, Any]] = [
    PI_SESSION,
    {"type": "agent_start"},
    {"type": "turn_start"},
    {"type": "message_start", "message": PI_USER},
    {"type": "message_end", "message": PI_USER},
    {"type": "message_start", "message": PI_TOOL_ASSISTANT},
    {"type": "message_end", "message": PI_TOOL_ASSISTANT},
    {
        "type": "tool_execution_start",
        "toolCallId": "call_1",
        "toolName": "bash",
        "args": {"command": "pytest -q"},
    },
    {
        "type": "tool_execution_end",
        "toolCallId": "call_1",
        "toolName": "bash",
        "result": {"content": [{"type": "text", "text": "1 passed"}], "details": {}},
        "isError": False,
    },
    {"type": "message_start", "message": PI_TOOL_RESULT},
    {"type": "message_end", "message": PI_TOOL_RESULT},
    {"type": "turn_end", "message": PI_TOOL_ASSISTANT, "toolResults": [PI_TOOL_RESULT]},
    {"type": "turn_start"},
    {"type": "message_start", "message": PI_TEXT_ASSISTANT},
    {"type": "message_end", "message": PI_TEXT_ASSISTANT},
    {"type": "turn_end", "message": PI_TEXT_ASSISTANT, "toolResults": []},
    {
        "type": "agent_end",
        "messages": [PI_USER, PI_TOOL_ASSISTANT, PI_TOOL_RESULT, PI_TEXT_ASSISTANT],
    },
]


def test_the_pi_stream_names_the_session_the_cost_and_the_final_text() -> None:
    assert pi_session_id(PI_STREAM) == PI_SESSION["id"]
    assert pi_cost(PI_STREAM) == pytest.approx(0.0003 + 0.0004)
    assert pi_final_text(PI_STREAM) == "Tests pass.\n\nCOMMIT: feat(pi): run workers on pi"


def test_pi_final_text_returns_the_earlier_text_when_the_last_message_has_none() -> None:
    # A worker that only called tools again has no final text: the last message with text
    # is the reply Conductor reads.
    tool_only = dict(
        PI_TEXT_ASSISTANT,
        content=[{"type": "toolCall", "id": "call_2", "name": "read", "arguments": {"path": "x"}}],
        stopReason="toolUse",
    )
    events: Events = [
        PI_SESSION,
        {"type": "turn_end", "message": PI_TEXT_ASSISTANT, "toolResults": []},
        {"type": "turn_end", "message": tool_only, "toolResults": []},
        {"type": "agent_end", "messages": [PI_TEXT_ASSISTANT, tool_only]},
    ]
    assert pi_final_text(events) == "Tests pass.\n\nCOMMIT: feat(pi): run workers on pi"


def test_auto_retry_start_is_a_retry() -> None:
    retry_start = {
        "type": "auto_retry_start",
        "attempt": 1,
        "maxAttempts": 3,
        "delayMs": 2000,
        "errorMessage": "429 Too Many Requests",
    }
    assert pi_is_retry(retry_start)
    assert not pi_is_retry(PI_SESSION)


def pi_retry_end(final_error: str) -> dict[str, Any]:
    return {"type": "auto_retry_end", "success": False, "attempt": 3, "finalError": final_error}


@pytest.mark.parametrize(
    ("final_error", "kind", "label"),
    [
        ("429 Too Many Requests", "transient", "pi-429"),
        ("503 Service Unavailable", "transient", "pi-503"),
        ("Connection error.", "transient", "pi-error"),
        ("401 Incorrect API key provided", "provider_unusable", "pi-401"),
        ("402 Insufficient credits", "provider_unusable", "pi-402"),
        ("400 This model's maximum context length is 8192 tokens", "model_unsuitable", "pi-400"),
    ],
)
def test_a_final_retry_error_is_classified(final_error: str, kind: str, label: str) -> None:
    # Pi reports errors as strings; the HTTP status appears in the text when there is one.
    error = pi_error([PI_SESSION, pi_retry_end(final_error)], exit_code=1, stderr="")
    assert error is not None
    assert (error.kind, error.type, error.message) == (kind, label, final_error)


def test_a_failing_assistant_message_is_classified_without_a_retry_report() -> None:
    failed = dict(
        PI_TEXT_ASSISTANT, content=[], stopReason="error", errorMessage="500 Internal Server Error"
    )
    events: Events = [
        PI_SESSION,
        {"type": "turn_end", "message": failed, "toolResults": []},
        {"type": "agent_end", "messages": [PI_USER, failed]},
    ]
    error = pi_error(events, exit_code=1, stderr="")
    assert error is not None
    assert (error.kind, error.type) == ("transient", "pi-500")


def test_a_successful_pi_run_has_no_error() -> None:
    assert pi_error(PI_STREAM, exit_code=0, stderr="") is None


def test_a_pi_exit_with_nothing_to_classify_is_unclassified() -> None:
    error = pi_error([PI_SESSION], exit_code=2, stderr="boom")
    assert error is not None
    assert (error.kind, error.type) == ("unclassified", "exit 2")


def test_pi_stream_drops_noise_lines_and_keeps_unicode_line_separators() -> None:
    # U+2028 is a line separator to str.splitlines() but text inside a JSON string: the
    # stream splits on \n only, so the event survives whole and a non-JSON line is noise.
    assistant = {
        "role": "assistant",
        "content": [{"type": "text", "text": "before\u2028after"}],
        "usage": pi_usage(0.0001),
        "stopReason": "stop",
        "timestamp": 1760421602000,
    }
    raw = "\n".join(
        [
            json.dumps(PI_SESSION),
            "pi 0.73.1",
            json.dumps(
                {"type": "turn_end", "message": assistant, "toolResults": []},
                ensure_ascii=False,
            ),
        ]
    )
    events = parse_events(raw)
    assert pi_session_id(events) == PI_SESSION["id"]
    assert pi_final_text(events) == "before\u2028after"


def test_the_pi_command_isolates_the_worker_and_names_the_api_model() -> None:
    cmd = pi_command("openrouter/deepseek/v4", "do it", ["--effort", "high"])
    assert cmd[0] == "pi"
    assert cmd[-1] == "do it"
    assert cmd[cmd.index("--model") + 1] == "deepseek/v4"
    for flag in (
        "--mode",
        "json",
        "--no-session",
        "--no-skills",
        "--no-extensions",
        "--no-prompt-templates",
        "--no-themes",
    ):
        assert flag in cmd
    assert cmd[cmd.index("--tools") + 1] == "read,bash,edit,write"
    assert cmd.index("--effort") < cmd.index("do it")
    # The key travels in the worktree's models.json and the environment, never as an argument.
    assert all("API_KEY" not in part.upper() and part != "--api-key" for part in cmd)


def test_pi_environment_points_at_the_agent_dir_in_the_worktree(tmp_path: Path) -> None:
    assert pi_environment(tmp_path) == {"PI_CODING_AGENT_DIR": str(tmp_path / ".pi-agent")}


def pi_profile() -> Profile:
    return Profile(
        "medium",
        {
            "piprovider": Provider(
                "piprovider", "https://example.com/v1", "PI_TEST_KEY", harness="pi"
            )
        },
        (("piprovider/m1",),),
        ("piprovider/m1",),
    )


def test_the_pi_harness_is_registered() -> None:
    assert HARNESSES["pi"] is PI


def test_harness_for_returns_pi_for_a_pi_provider() -> None:
    assert harness_for(pi_profile(), "piprovider/m1") is PI


def init_worktree(tmp_path: Path, *files: str) -> Path:
    worktree = tmp_path / "wt"
    worktree.mkdir()
    git(worktree, "init", "-q")
    for name in files:
        (worktree / name).write_text("# instructions\n")
    return worktree


def written_config(worktree: Path) -> dict[str, Any]:
    config: dict[str, Any] = json.loads((worktree / "opencode.json").read_text())
    return config


def test_opencode_workers_read_claude_md_when_there_is_no_agents_md(tmp_path: Path) -> None:
    worktree = init_worktree(tmp_path, "CLAUDE.md")
    prepare_opencode(worktree, make_profile())
    assert written_config(worktree)["instructions"] == ["CLAUDE.md"]


@pytest.mark.parametrize("files", [("AGENTS.md", "CLAUDE.md"), ("AGENTS.md",), ()])
def test_opencode_workers_get_no_extra_instructions_otherwise(
    tmp_path: Path, files: tuple[str, ...]
) -> None:
    worktree = init_worktree(tmp_path, *files)
    prepare_opencode(worktree, make_profile())
    assert "instructions" not in written_config(worktree)


def test_pi_prepare_writes_the_profile_into_the_worktrees_agent_dir(tmp_path: Path) -> None:
    worktree = init_worktree(tmp_path)
    pi_prepare(worktree, pi_profile())
    config: dict[str, Any] = json.loads((worktree / ".pi-agent" / "models.json").read_text())
    assert config["providers"]["piprovider"]["apiKey"] == "PI_TEST_KEY"
    assert ".pi-agent/" in (worktree / ".git" / "info" / "exclude").read_text()
