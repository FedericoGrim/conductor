import json
from pathlib import Path
from typing import Any

import pytest

from conductor.config import HARNESS_NAMES, Profile, Provider
from conductor.harness import (
    CLAUDE_CODE,
    HARNESSES,
    OPENCODE,
    claude_billed_cost,
    claude_build_command,
    claude_error,
    claude_final_text,
    claude_is_retry,
    claude_session_id,
    claude_subscription_cost,
    harness_for,
    prepare_opencode,
)
from conductor.worker import git
from tests.factories import make_profile


def test_every_harness_name_has_a_harness() -> None:
    # "pi" is a known name already; its Harness (command and event stream) lands with the
    # Pi worker step, so for now it is the one name without a harness.
    assert set(HARNESSES) == set(HARNESS_NAMES) - {"pi"}
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
