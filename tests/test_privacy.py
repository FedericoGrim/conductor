from conductor.privacy import api_model_id, opencode_config
from tests.factories import make_profile

PROFILE = make_profile(
    base_url="https://eu.openrouter.ai/api/v1",
    api_key_env="OPENROUTER_API_KEY",
    tiers=("openrouter/deepseek/v4", "openrouter/anthropic/sonnet"),
    reviewer="openrouter/deepseek/v4",
    request_options={"provider": {"data_collection": "deny"}},
)


def test_opencode_config_routes_every_tier_through_profile() -> None:
    config = opencode_config(PROFILE)
    provider = config["provider"]["openrouter"]
    assert provider["options"]["baseURL"] == "https://eu.openrouter.ai/api/v1"
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
    assert api_model_id("openrouter", "openrouter/deepseek/v4") == "deepseek/v4"
    assert api_model_id("openrouter", "deepseek/v4") == "deepseek/v4"


def test_opencode_config_carries_every_provider_with_its_own_models() -> None:
    from conductor.config import Profile, Provider

    profile = Profile(
        "medium",
        {
            "openrouter": Provider("openrouter", "https://openrouter.ai/api/v1", "A"),
            "scaleway": Provider("scaleway", "https://api.scaleway.ai/v1", "B"),
        },
        (("openrouter/deepseek/v4",), ("scaleway/glm-5.3",)),
        ("scaleway/glm-5.3",),
    )
    config = opencode_config(profile)
    assert config["provider"]["openrouter"] == {
        "options": {"baseURL": "https://openrouter.ai/api/v1"},
        "models": {"deepseek/v4": {"options": {}}},
    }
    assert config["provider"]["scaleway"] == {
        "options": {"baseURL": "https://api.scaleway.ai/v1"},
        "models": {"glm-5.3": {"options": {}}},
    }


def test_model_options_are_merged_over_the_provider_options() -> None:
    from conductor.config import Profile, Provider

    profile = Profile(
        "medium",
        {
            "openrouter": Provider(
                "openrouter",
                "https://openrouter.ai/api/v1",
                "K",
                {"provider": {"data_collection": "deny"}},
                {
                    "deepseek/v4": {"provider": {"order": ["relace"], "allow_fallbacks": True}},
                },
            )
        },
        (("openrouter/deepseek/v4",), ("openrouter/other/model",)),
        ("openrouter/deepseek/v4",),
    )
    provider = opencode_config(profile)["provider"]["openrouter"]
    assert provider["models"]["deepseek/v4"]["options"] == {
        "provider": {"data_collection": "deny", "order": ["relace"], "allow_fallbacks": True}
    }
    assert provider["models"]["other/model"]["options"] == {"provider": {"data_collection": "deny"}}


def test_opencode_config_includes_the_fallback_models_of_every_level() -> None:
    from conductor.config import Profile, Provider

    profile = Profile(
        "medium",
        {
            "openrouter": Provider("openrouter", "https://openrouter.ai/api/v1", "A"),
            "deepseek": Provider("deepseek", "https://api.deepseek.com/v1", "B"),
        },
        (("openrouter/a",), ("openrouter/b", "deepseek/b2")),
        ("openrouter/a",),
    )
    config = opencode_config(profile)
    assert set(config["provider"]["openrouter"]["models"]) == {"a", "b"}
    assert set(config["provider"]["deepseek"]["models"]) == {"b2"}


def test_provider_options_also_cover_models_that_opencode_picks_itself() -> None:
    provider = opencode_config(PROFILE)["provider"]["openrouter"]
    assert provider["options"] == {
        "baseURL": "https://eu.openrouter.ai/api/v1",
        "provider": {"data_collection": "deny"},
    }


def test_the_small_model_is_the_first_model_of_the_easiest_level() -> None:
    assert opencode_config(PROFILE)["small_model"] == "openrouter/deepseek/v4"


def test_vercel_gateway_options_are_unwrapped_for_opencode() -> None:
    from conductor.config import Profile, Provider

    no_training = {"providerOptions": {"gateway": {"disallowPromptTraining": True}}}
    profile = Profile(
        "medium",
        {"vercel": Provider("vercel", "https://ai-gateway.vercel.sh/v1", "V", no_training)},
        (("vercel/openai/gpt-5.6-luna",),),
        ("vercel/openai/gpt-5.6-luna",),
    )
    provider = opencode_config(profile)["provider"]["vercel"]
    gateway = {"gateway": {"disallowPromptTraining": True}}
    assert provider["options"] == {"baseURL": "https://ai-gateway.vercel.sh/v1", **gateway}
    assert provider["models"] == {"openai/gpt-5.6-luna": {"options": gateway}}


def test_providers_without_url_are_left_to_the_harness() -> None:
    from conductor.config import Profile, Provider

    profile = Profile(
        "medium",
        {
            "subscription": Provider("subscription", "", ""),
            "openrouter": Provider("openrouter", "https://openrouter.ai/api/v1", "K"),
        },
        (("subscription/opus", "openrouter/a"),),
        ("openrouter/a",),
    )
    config = opencode_config(profile)
    assert set(config["provider"]) == {"openrouter"}
