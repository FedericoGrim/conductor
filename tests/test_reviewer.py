import json
from typing import Any

import pytest

from conductor.credentials import store_key
from conductor.reviewer import ReviewerError, Verdict, review
from tests.factories import make_profile

PROFILE = make_profile(
    api_key_env="TEST_REVIEW_KEY",
    tiers=("openrouter/a/b",),
    reviewer="openrouter/deepseek/flash",
    request_options={"provider": {"data_collection": "deny"}},
)


def completion(content: str) -> dict[str, Any]:
    return {"choices": [{"message": {"content": content}}], "usage": {"total_tokens": 42}}


def test_sends_spec_and_diff_and_parses_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_REVIEW_KEY", "sk-secret")
    captured: dict[str, Any] = {}

    def fake_post(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        captured.update(url=url, headers=headers, body=body)
        return completion(json.dumps({"ok": False, "reason": "missing null check"}))

    verdict = review(PROFILE, spec="add parser", diff="+def parse(): ...", post=fake_post)
    assert verdict.ok is False
    assert verdict.reason == "missing null check"
    assert verdict.usage == {"total_tokens": 42}
    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer sk-secret"
    assert captured["body"]["model"] == "deepseek/flash"
    assert captured["body"]["provider"] == {"data_collection": "deny"}
    prompt = captured["body"]["messages"][-1]["content"]
    assert "add parser" in prompt
    assert "+def parse(): ..." in prompt


def test_unparseable_verdict_is_a_rejection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_REVIEW_KEY", "k")

    def fake_post(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        return completion("Looks fine to me!")

    verdict = review(PROFILE, spec="s", diff="d", post=fake_post)
    assert verdict.ok is False
    assert verdict.reason == "unparseable verdict"
    assert verdict.raw == "Looks fine to me!"


def test_fenced_json_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_REVIEW_KEY", "k")

    def fake_post(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        return completion('```json\n{"ok": true, "reason": "good"}\n```')

    assert review(PROFILE, spec="s", diff="d", post=fake_post).ok is True


def test_missing_api_key_fails_before_any_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TEST_REVIEW_KEY", raising=False)

    def fake_post(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("must not be called")

    with pytest.raises(ReviewerError, match="TEST_REVIEW_KEY"):
        review(PROFILE, spec="s", diff="d", post=fake_post)


def test_verdict_cost_comes_from_the_usage_reported_by_the_provider() -> None:
    assert Verdict(True, "ok", "{}", usage={"total_tokens": 9, "cost": 0.0031}).cost == 0.0031


def test_verdict_cost_is_unknown_when_the_provider_does_not_report_it() -> None:
    assert Verdict(True, "ok", "{}", usage={"total_tokens": 9}).cost is None
    assert Verdict(True, "ok", "{}", usage={"cost": "n/a"}).cost is None


def test_a_stored_key_is_used_when_the_environment_has_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TEST_REVIEW_KEY", raising=False)
    store_key("TEST_REVIEW_KEY", "sk-stored")
    captured: dict[str, Any] = {}

    def fake_post(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        captured.update(headers=headers)
        return completion(json.dumps({"ok": True, "reason": "fine"}))

    assert review(PROFILE, spec="s", diff="+x", post=fake_post).ok is True
    assert captured["headers"]["Authorization"] == "Bearer sk-stored"


def test_the_reviewer_uses_the_provider_of_its_model(monkeypatch: pytest.MonkeyPatch) -> None:
    from conductor.config import Profile, Provider

    profile = Profile(
        "medium",
        {
            "openrouter": Provider("openrouter", "https://openrouter.ai/api/v1", "K1"),
            "scaleway": Provider("scaleway", "https://api.scaleway.ai/v1", "K2"),
        },
        ("openrouter/a",),
        "scaleway/glm-5.3",
    )
    monkeypatch.setenv("K1", "sk-one")
    monkeypatch.setenv("K2", "sk-two")
    captured: dict[str, Any] = {}

    def fake_post(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        captured.update(url=url, headers=headers, body=body)
        return completion(json.dumps({"ok": True, "reason": "fine"}))

    review(profile, spec="s", diff="+x", post=fake_post)
    assert captured["url"] == "https://api.scaleway.ai/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer sk-two"
    assert captured["body"]["model"] == "glm-5.3"
