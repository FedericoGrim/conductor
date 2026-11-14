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
from conductor.reviewer import Verdict, review, review_request
from conductor.verify import CheckResult
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

    verdict = review(
        PROFILE, PROFILE.reviewers[0], spec="add parser", diff="+def parse(): ...", post=fake_post
    )
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

    verdict = review(PROFILE, PROFILE.reviewers[0], spec="s", diff="d", post=fake_post)
    assert verdict.ok is False
    assert verdict.reason == "unparseable verdict"
    assert verdict.raw == "Looks fine to me!"
    assert verdict.error == ModelError(MODEL_UNSUITABLE, "unparseable-verdict", "Looks fine to me!")


def test_fenced_json_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_REVIEW_KEY", "k")

    def fake_post(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        return completion('```json\n{"ok": true, "reason": "good"}\n```')

    assert review(PROFILE, PROFILE.reviewers[0], spec="s", diff="d", post=fake_post).ok is True


def test_missing_api_key_makes_the_provider_unusable_before_any_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TEST_REVIEW_KEY", raising=False)

    def fake_post(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        raise AssertionError("must not be called")

    verdict = review(PROFILE, PROFILE.reviewers[0], spec="s", diff="d", post=fake_post)
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

    verdict = review(PROFILE, PROFILE.reviewers[0], spec="s", diff="d", post=fake_post)
    assert verdict.ok is False
    assert verdict.error is not None
    assert (verdict.error.kind, verdict.error.type) == (kind, error_type)


def test_a_malformed_response_is_an_unclassified_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_REVIEW_KEY", "k")

    def fake_post(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        return {"unexpected": True}

    verdict = review(PROFILE, PROFILE.reviewers[0], spec="s", diff="d", post=fake_post)
    assert verdict.ok is False
    assert verdict.error is not None
    assert verdict.error.kind == UNCLASSIFIED


def test_a_parsed_verdict_has_no_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TEST_REVIEW_KEY", "k")

    def fake_post(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        return completion('{"ok": false, "reason": "no tests"}')

    assert review(PROFILE, PROFILE.reviewers[0], spec="s", diff="d", post=fake_post).error is None


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

    assert review(PROFILE, PROFILE.reviewers[0], spec="s", diff="+x", post=fake_post).ok is True
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

    review(profile, profile.reviewers[0], spec="s", diff="+x", post=fake_post)
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

    review(profile, profile.reviewers[0], spec="s", diff="+x", post=fake_post)
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

    verdict = review(insecure, insecure.reviewers[0], spec="s", diff="d", post=fake_post)
    assert verdict.ok is False
    assert verdict.error is not None
    assert (verdict.error.kind, verdict.error.type) == (PROVIDER_UNUSABLE, "insecure-base-url")
    assert "sk-secret" not in verdict.reason


def test_the_review_uses_the_reviewer_it_is_given(monkeypatch: pytest.MonkeyPatch) -> None:
    from conductor.config import Profile, Provider

    profile = Profile(
        "medium",
        {
            "openrouter": Provider("openrouter", "https://openrouter.ai/api/v1", "K1"),
            "scaleway": Provider("scaleway", "https://api.scaleway.ai/v1", "K2"),
        },
        (("openrouter/a",),),
        ("openrouter/r", "scaleway/r2"),
    )
    monkeypatch.setenv("K2", "sk-two")
    captured: dict[str, Any] = {}

    def fake_post(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        captured.update(url=url, body=body)
        return completion(json.dumps({"ok": True, "reason": "fine"}))

    review(profile, "scaleway/r2", spec="s", diff="+x", post=fake_post)
    assert captured["url"] == "https://api.scaleway.ai/v1/chat/completions"
    assert captured["body"]["model"] == "r2"


def captured_request(monkeypatch: pytest.MonkeyPatch, **context: Any) -> dict[str, Any]:
    monkeypatch.setenv("TEST_REVIEW_KEY", "k")
    captured: dict[str, Any] = {}

    def fake_post(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
        captured.update(body=body)
        return completion('{"ok": true, "reason": "fine"}')

    review(PROFILE, PROFILE.reviewers[0], spec="s", diff="+x", post=fake_post, **context)
    body: dict[str, Any] = captured["body"]
    return body


def test_the_domain_rules_reach_the_reviewer_as_their_own_section(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = captured_request(monkeypatch, rules=("Totals never go negative", "No ORM in domain/"))
    prompt = body["messages"][-1]["content"]
    assert "## Domain rules\n- Totals never go negative\n- No ORM in domain/" in prompt
    assert prompt.index("## Domain rules") < prompt.index("## Diff")


def test_the_verification_results_reach_the_reviewer(monkeypatch: pytest.MonkeyPatch) -> None:
    passed = CheckResult("pytest -q", 0, "x" * 5000 + "12 passed", 3.0)
    body = captured_request(monkeypatch, checks=[passed])
    prompt = body["messages"][-1]["content"]
    assert (
        "## Verification (run by Conductor)\n"
        "All verification commands passed (exit 0); what they check is settled.\n"
        "- `pytest -q`: exit 0"
    ) in prompt
    assert "12 passed" in prompt
    assert len(prompt) < 2500


def test_the_verification_summary_precedes_the_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    passed = CheckResult("ruff check .", 0, "All checks passed", 1.0)
    prompt = review_request("spec", "+diff", (), [passed])
    summary = "All verification commands passed (exit 0); what they check is settled."
    assert summary in prompt
    assert prompt.index(summary) < prompt.index("`ruff check .`")


def test_without_rules_or_checks_the_sections_are_left_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prompt = captured_request(monkeypatch)["messages"][-1]["content"]
    assert "## Domain rules" not in prompt
    assert "## Verification" not in prompt
    assert "All verification commands passed" not in prompt


def test_the_reviewer_judges_tests_and_domain_rules_explicitly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    system = captured_request(monkeypatch)["messages"][0]["content"]
    for criterion in ("tests", "domain rules", "JSON only"):
        assert criterion in system


def test_review_request_includes_the_commit_message_when_given() -> None:
    prompt = review_request("spec", "+diff", (), [], "feat(parser): scan the input")
    assert "## Commit message" in prompt
    assert "feat(parser): scan the input" in prompt
    assert prompt.index("## Commit message") < prompt.index("## Diff")


def test_review_request_omits_the_commit_message_when_empty() -> None:
    prompt = review_request("spec", "+diff", (), [])
    assert "## Commit message" not in prompt


def test_the_system_prompt_names_the_commit_message_criterion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    system = captured_request(monkeypatch)["messages"][0]["content"]
    assert "commit message" in system
    assert "Conventional Commit type" in system


def test_the_system_prompt_says_what_passed_checks_settle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    system = captured_request(monkeypatch)["messages"][0]["content"]
    assert "never a reason to reject" in system
    assert "is not missing" in system
