from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import asdict
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from conductor import reviewer
from conductor.errors import TRANSIENT, ModelError
from conductor.reviewer import Verdict
from conductor.verify import CheckResult

SCRIPT = Path(__file__).parent.parent / "scripts" / "replay-review.py"
CHECK = CheckResult("mypy --strict .", 0, "Success: no issues found", 1.5)
CONFIG = """
[privacy.medium]
tiers = [["testprov/t1"]]
reviewer = "testprov/rev"

[privacy.medium.providers.testprov]
base_url = "https://api.example.invalid/v1"
api_key_env = "TEST_REPLAY_KEY"

[privacy.high]
tiers = [["testprov/t2"]]
reviewer = "testprov/rev-high"

[privacy.high.providers.testprov]
base_url = "https://api.example.invalid/v1"
api_key_env = "TEST_REPLAY_KEY"
"""


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("replay-review", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


replay = load_script()


def write_attempt(
    tmp_path: Path,
    *,
    rules: list[str] | None = None,
    rules_file: str | None = None,
    commit_message: str | None = None,
    attempt_step: str = "s1",
) -> Path:
    plan: dict[str, Any] = {
        "goal": "ship the replay",
        "steps": [
            {"id": "s1", "title": "Add the parser", "spec": "Add the parser", "difficulty": 1}
        ],
        "rules": rules or [],
    }
    if rules_file is not None:
        plan["rules_file"] = rules_file
    run_dir = tmp_path / "2026-01-01T00-00-00"
    (run_dir / "step-s1").mkdir(parents=True)
    (run_dir / "run.json").write_text(json.dumps({"plan": plan}))
    attempt: dict[str, Any] = {
        "step": {"id": attempt_step, "title": "Add the parser"},
        "attempt": 1,
        "diff": "+def parse(): ...",
        "verify": [asdict(CHECK)],
    }
    if commit_message is not None:
        attempt["commit_message"] = commit_message
    path = run_dir / "step-s1" / "attempt-1.json"
    path.write_text(json.dumps(attempt))
    return path


def install_review(
    monkeypatch: pytest.MonkeyPatch, verdicts: list[Verdict]
) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    def fake_review(
        profile: object, model: str, spec: str, diff: str, **context: object
    ) -> Verdict:
        calls.append({"profile": profile, "model": model, "spec": spec, "diff": diff, **context})
        return verdicts[(len(calls) - 1) % len(verdicts)]

    monkeypatch.setattr(reviewer, "review", fake_review)
    return calls


def write_config(tmp_path: Path) -> Path:
    config = tmp_path / "conductor.toml"
    config.write_text(CONFIG)
    return config


def test_load_attempt_reads_the_recorded_review_input(tmp_path: Path) -> None:
    path = write_attempt(
        tmp_path, rules=["Totals never go negative"], commit_message="feat(parser): parse input"
    )
    loaded = replay.load_attempt(path)
    assert loaded.spec == "Add the parser"
    assert loaded.rules == ("Totals never go negative",)
    assert loaded.checks == [CHECK]
    assert loaded.commit_message == "feat(parser): parse input"
    assert loaded.diff == "+def parse(): ..."


def test_load_attempt_defaults_the_commit_message_of_older_attempts(tmp_path: Path) -> None:
    assert replay.load_attempt(write_attempt(tmp_path)).commit_message == ""


def test_load_attempt_accepts_an_attempt_that_names_the_step_plainly(tmp_path: Path) -> None:
    path = write_attempt(tmp_path)
    attempt = json.loads(path.read_text())
    attempt["step"] = "s1"
    path.write_text(json.dumps(attempt))
    assert replay.load_attempt(path).spec == "Add the parser"


def test_main_returns_2_for_a_missing_attempt_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert replay.main([str(tmp_path / "step-s1" / "attempt-9.json")]) == 2
    assert "error:" in capsys.readouterr().err


def test_main_returns_2_when_run_json_is_missing(tmp_path: Path) -> None:
    path = write_attempt(tmp_path)
    (path.parent.parent / "run.json").unlink()
    assert replay.main([str(path)]) == 2


def test_main_returns_2_when_the_step_is_not_in_the_plan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_attempt(tmp_path, attempt_step="s9")
    assert replay.main([str(path)]) == 2
    message = capsys.readouterr().err
    assert "'s9'" in message
    assert "not in the plan" in message


def test_summary_counts_verdicts_by_outcome() -> None:
    verdicts = [
        Verdict(True, "fine", "{}"),
        Verdict(False, "no tests for the new behaviour", "{}", category="spec"),
        Verdict(False, "types broken", "{}", category="types"),
        Verdict.failed(ModelError(TRANSIENT, "http-500", "provider down")),
    ]
    line = replay.summary(verdicts, [CHECK])
    assert "approvals 1" in line
    assert "rejections 2" in line
    assert "suspicious rejections 1" in line
    assert "errors 1" in line


def test_summary_totals_the_costs_the_provider_reported() -> None:
    verdicts = [
        Verdict(True, "fine", "{}", usage={"cost": 0.01}),
        Verdict(False, "types broken", "{}", category="types"),
        Verdict(True, "fine", "{}", usage={"cost": 0.02}),
    ]
    assert "cost 0.0300 USD" in replay.summary(verdicts, [])


def test_summary_reports_no_cost_when_no_verdict_has_one() -> None:
    assert "cost -" in replay.summary([Verdict(True, "fine", "{}")], [])


def test_verdict_line_shows_category_cost_and_suspicion() -> None:
    rejected = replay.verdict_line(2, Verdict(False, "no tests", "{}", category="spec"), [CHECK])
    assert "rejected" in rejected
    assert "spec" in rejected
    assert "suspicious" not in rejected
    assert "  -  " in rejected
    suspicious = replay.verdict_line(
        3, Verdict(False, "types broken", "{}", category="types"), [CHECK]
    )
    assert "suspicious" in suspicious
    approved = replay.verdict_line(1, Verdict(True, "fine", "{}", usage={"cost": 2.0}), [CHECK])
    assert "approved" in approved
    assert "2.0000 USD" in approved


def test_verdict_line_truncates_the_reason_to_200_characters() -> None:
    line = replay.verdict_line(1, Verdict(False, "x" * 300, "{}", category="spec"), [])
    assert "x" * 200 in line
    assert "x" * 201 not in line


def test_main_replays_the_same_review_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = write_attempt(
        tmp_path, rules=["Totals never go negative"], commit_message="feat(parser): parse input"
    )
    config = write_config(tmp_path)
    verdicts = [
        Verdict(True, "fine", "{}", usage={"cost": 0.01}),
        Verdict(False, "types broken", "{}", category="types"),
        Verdict.failed(ModelError(TRANSIENT, "http-500", "provider down")),
    ]
    calls = install_review(monkeypatch, verdicts)
    assert replay.main([str(path), "--config", str(config), "--times", "3"]) == 0
    assert len(calls) == 3
    assert calls[0] == calls[1] == calls[2]
    assert calls[0]["model"] == "testprov/rev"
    assert calls[0]["profile"].name == "medium"
    assert calls[0]["spec"] == "Add the parser"
    assert calls[0]["diff"] == "+def parse(): ..."
    assert calls[0]["rules"] == ("Totals never go negative",)
    assert calls[0]["checks"] == [CHECK]
    assert calls[0]["commit_message"] == "feat(parser): parse input"
    out = capsys.readouterr().out
    assert "rules_file" not in out
    lines = out.splitlines()
    assert len(lines) == 4
    assert "approved" in lines[0]
    assert "0.0100 USD" in lines[0]
    assert "rejected" in lines[1]
    assert "types suspicious" in lines[1]
    assert "error" in lines[2]
    assert "suspicious rejections 1" in lines[3]


def test_main_selects_the_profile_and_the_reviewer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write_attempt(tmp_path)
    config = write_config(tmp_path)
    calls = install_review(monkeypatch, [Verdict(True, "fine", "{}")])
    assert replay.main([str(path), "--config", str(config), "--times", "1"]) == 0
    assert calls[0]["model"] == "testprov/rev"
    assert calls[0]["profile"].name == "medium"
    assert (
        replay.main([str(path), "--config", str(config), "--privacy", "high", "--times", "1"]) == 0
    )
    assert calls[1]["model"] == "testprov/rev-high"
    assert calls[1]["profile"].name == "high"
    assert (
        replay.main(
            [str(path), "--config", str(config), "--reviewer", "testprov/benchmark", "--times", "1"]
        )
        == 0
    )
    assert calls[2]["model"] == "testprov/benchmark"


def test_main_returns_2_for_an_unknown_privacy_level(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = write_attempt(tmp_path)
    config = write_config(tmp_path)
    calls = install_review(monkeypatch, [Verdict(True, "fine", "{}")])
    assert replay.main([str(path), "--config", str(config), "--privacy", "nope"]) == 2
    assert calls == []
    assert "unknown privacy level 'nope'" in capsys.readouterr().err


def test_main_notes_and_ignores_a_rules_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = write_attempt(tmp_path, rules=["Totals never go negative"], rules_file="AGENTS.md")
    config = write_config(tmp_path)
    calls = install_review(monkeypatch, [Verdict(True, "fine", "{}")])
    assert replay.main([str(path), "--config", str(config), "--times", "1"]) == 0
    assert calls[0]["rules"] == ("Totals never go negative",)
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 3
    assert "rules_file 'AGENTS.md'" in lines[0]


def test_main_sends_the_recorded_review_to_the_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = write_attempt(tmp_path, commit_message="feat(parser): parse input")
    config = write_config(tmp_path)
    monkeypatch.setenv("TEST_REPLAY_KEY", "sk-test")
    captured: dict[str, Any] = {}

    def fake_post(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        captured.update(url=url, headers=headers, body=body)
        return {
            "choices": [{"message": {"content": '{"ok": true, "reason": "fine"}'}}],
            "usage": {},
        }

    monkeypatch.setattr(reviewer, "http_post", fake_post)
    assert replay.main([str(path), "--config", str(config), "--times", "1"]) == 0
    assert captured["url"] == "https://api.example.invalid/v1/chat/completions"
    assert captured["body"]["model"] == "rev"
    prompt = captured["body"]["messages"][-1]["content"]
    assert "Add the parser" in prompt
    assert "feat(parser): parse input" in prompt
    out = capsys.readouterr().out
    assert "approved" in out
    assert "sk-test" not in out
