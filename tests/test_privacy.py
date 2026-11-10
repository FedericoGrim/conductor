from conductor.config import Profile
from conductor.privacy import api_model_id, opencode_config

PROFILE = Profile(
    name="medium",
    provider="openrouter",
    base_url="https://eu.openrouter.ai/api/v1",
    api_key_env="OPENROUTER_API_KEY",
    tiers=("openrouter/deepseek/v4", "openrouter/anthropic/sonnet"),
    reviewer="openrouter/deepseek/v4",
    max_parallel=4,
    request_options={"provider": {"data_collection": "deny"}},
)


def test_opencode_config_routes_every_tier_through_profile() -> None:
    config = opencode_config(PROFILE)
    provider = config["provider"]["openrouter"]
    assert provider["options"] == {"baseURL": "https://eu.openrouter.ai/api/v1"}
    assert provider["models"] == {
        "deepseek/v4": {"options": {"provider": {"data_collection": "deny"}}},
        "anthropic/sonnet": {"options": {"provider": {"data_collection": "deny"}}},
    }


def test_opencode_config_never_contains_the_api_key(monkeypatch: object) -> None:
    import os

    os.environ["OPENROUTER_API_KEY"] = "sk-test-secret"
    try:
        assert "sk-test-secret" not in str(opencode_config(PROFILE))
    finally:
        del os.environ["OPENROUTER_API_KEY"]


def test_api_model_id_strips_the_opencode_provider_prefix() -> None:
    assert api_model_id(PROFILE, "openrouter/deepseek/v4") == "deepseek/v4"
    assert api_model_id(PROFILE, "deepseek/v4") == "deepseek/v4"
