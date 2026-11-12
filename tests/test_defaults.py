from conductor.config import provider_of
from conductor.defaults import DIFFICULTY_LEVELS, default_config

LEVELS = range(DIFFICULTY_LEVELS)


def test_low_starts_with_free_models_and_ends_on_paid_ones() -> None:
    low = default_config().profile("low")
    assert all(model.endswith(":free") for model in low.tiers[0])
    assert all(model.endswith(":free") for model in low.tiers[1])
    assert not any(model.endswith(":free") for tier in low.tiers[2:] for model in tier)


def test_medium_and_high_never_use_free_models() -> None:
    config = default_config()
    for name in ("medium", "high"):
        assert not any(model.endswith(":free") for model in config.profile(name).models())


def test_high_stays_on_eu_endpoints() -> None:
    high = default_config().profile("high")
    assert {provider.base_url for provider in high.providers.values()} == {
        "https://eu.openrouter.ai/api/v1",
        "https://api.scaleway.ai/v1",
    }


def test_every_paid_level_and_reviewer_falls_back_on_another_provider() -> None:
    for profile in default_config().profiles.values():
        for tier in profile.tiers:
            if all(model.endswith(":free") for model in tier):
                continue
            assert len({provider_of(model) for model in tier}) > 1, (profile.name, tier)
        assert len({provider_of(model) for model in profile.reviewers}) > 1


def test_free_levels_fall_back_on_free_models_only() -> None:
    low = default_config().profile("low")
    for tier in low.tiers[:2]:
        assert len(tier) > 1
        assert all(model.endswith(":free") for model in tier)


def test_medium_never_trains_on_prompts() -> None:
    providers = default_config().profile("medium").providers
    assert providers["openrouter"].request_options == {"provider": {"data_collection": "deny"}}
    assert providers["vercel"].request_options == {
        "providerOptions": {"gateway": {"disallowPromptTraining": True}}
    }


def test_every_profile_has_five_distinct_levels_and_a_reviewer() -> None:
    config = default_config()
    for name in ("low", "medium", "high"):
        profile = config.profile(name)
        assert len(profile.tiers) == DIFFICULTY_LEVELS
        assert len(set(profile.tiers)) == DIFFICULTY_LEVELS
        assert profile.reviewers
