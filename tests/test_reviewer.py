import io
import json
from email.message import Message
from typing import Any
from urllib.error import HTTPError, URLError

import pytest

from conductor.credentials import store_key
from conductor.errors import (
    MODEL_UNSUITABLE,
    PROVIDER_UNUSABLE,
    TRANSIENT,
    UNCLASSIFIED,
    ModelError,
)
from conductor.reviewer import Verdict, review
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
    assert verdict.error == ModelError(MODEL_UNSUITABLE, "unparseable-verdict", "Looks fine to me!")


def test_fenced_json_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_REVIEW_KEY", "k")

    def fake_post(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        return completion('```json\n{"ok": true, "reason": "good"}\n```')

    assert review(PROFILE, spec="s", diff="d", post=fake_post).ok is True


def test_missing_api_key_makes_the_provider_unusable_before_any_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TEST_REVIEW_KEY", raising=False)

    def fake_post(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("must not be called")

    verdict = review(PROFILE, spec="s", diff="d", post=fake_post)
    assert verdict.ok is False
    assert verdict.error is not None
    assert verdict.error.kind == PROVIDER_UNUSABLE
    assert "TEST_REVIEW_KEY" in verdict.reason


def http_error(code: int, body: str = '{"error": {"message": "nope"}}') -> HTTPError:
    return HTTPError("https://x", code, "status", Message(), io.BytesIO(body.encode()))


@pytest.mark.parametrize(
    ("failure", "kind", "error_type"),
    [
        (http_error(429), TRANSIENT, "http-429"),
        (http_error(503), TRANSIENT, "http-503"),
        (http_error(401), PROVIDER_UNUSABLE, "http-401"),
        (http_error(402), PROVIDER_UNUSABLE, "http-402"),
        (http_error(404), MODEL_UNSUITABLE, "http-404"),
        (http_error(400, "maximum context length exceeded"), MODEL_UNSUITABLE, "http-400"),
        (http_error(400), UNCLASSIFIED, "http-400"),
        (URLError("connection refused"), TRANSIENT, "network"),
        (TimeoutError("timed out"), TRANSIENT, "network"),
    ],
)
def test_request_failures_become_classified_errors_instead_of_raising(
    monkeypatch: pytest.MonkeyPatch, failure: Exception, kind: str, error_type: str
) -> None:
    monkeypatch.setenv("TEST_REVIEW_KEY", "k")

    def fake_post(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        raise failure

    verdict = review(PROFILE, spec="s", diff="d", post=fake_post)
    assert verdict.ok is False
    assert verdict.error is not None
    assert (verdict.error.kind, verdict.error.type) == (kind, error_type)


def test_a_malformed_response_is_an_unclassified_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_REVIEW_KEY", "k")

    def fake_post(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        return {"unexpected": True}

    verdict = review(PROFILE, spec="s", diff="d", post=fake_post)
    assert verdict.ok is False
    assert verdict.error is not None
    assert verdict.error.kind == UNCLASSIFIED


def test_a_parsed_verdict_has_no_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_REVIEW_KEY", "k")

    def fake_post(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        return completion('{"ok": false, "reason": "no tests"}')

    assert review(PROFILE, spec="s", diff="d", post=fake_post).error is None


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
        (("openrouter/a",),),
        ("scaleway/glm-5.3",),
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


def test_the_reviewer_receives_the_options_of_its_model(monkeypatch: pytest.MonkeyPatch) -> None:
    from conductor.config import Profile, Provider

    profile = Profile(
        "medium",
        {
            "openrouter": Provider(
                "openrouter",
                "https://openrouter.ai/api/v1",
                "K",
                {"provider": {"data_collection": "deny"}},
                {"deepseek/flash": {"provider": {"order": ["relace"]}}},
            )
        },
        (("openrouter/a",),),
        ("openrouter/deepseek/flash",),
    )
    monkeypatch.setenv("K", "sk")
    captured: dict[str, Any] = {}

    def fake_post(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        captured.update(body=body)
        return completion(json.dumps({"ok": True, "reason": "fine"}))

    review(profile, spec="s", diff="+x", post=fake_post)
    assert captured["body"]["provider"] == {
        "data_collection": "deny",
        "order": ["relace"],
    }


def test_the_key_is_never_sent_to_a_base_url_that_is_not_https(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TEST_REVIEW_KEY", "sk-secret")
    insecure = make_profile(
        api_key_env="TEST_REVIEW_KEY",
        base_url="http://openrouter.ai/api/v1",
        tiers=("openrouter/a/b",),
        reviewer="openrouter/deepseek/flash",
    )

    def fake_post(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("must not be called")

    verdict = review(insecure, spec="s", diff="d", post=fake_post)
    assert verdict.ok is False
    assert verdict.error is not None
    assert (verdict.error.kind, verdict.error.type) == (PROVIDER_UNUSABLE, "insecure-base-url")
    assert "sk-secret" not in verdict.reason
