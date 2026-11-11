from conductor.defaults import DIFFICULTY_LEVELS, default_config

LEVELS = range(DIFFICULTY_LEVELS)


def test_low_starts_with_free_models_and_ends_on_paid_ones() -> None:
    low = default_config().profile("low")
    assert low.tiers[0].endswith(":free")
    assert low.tiers[1].endswith(":free")
    assert not any(tier.endswith(":free") for tier in low.tiers[2:])


def test_medium_and_high_never_use_free_models() -> None:
    config = default_config()
    for name in ("medium", "high"):
        assert not any(tier.endswith(":free") for tier in config.profile(name).tiers)


def test_high_stays_on_the_eu_endpoint() -> None:
    high = default_config().profile("high")
    assert all(
        provider.base_url.startswith("https://eu.openrouter.ai")
        for provider in high.providers.values()
    )


def test_every_profile_has_five_distinct_levels_and_a_reviewer() -> None:
    config = default_config()
    for name in ("low", "medium", "high"):
        profile = config.profile(name)
        assert len(profile.tiers) == DIFFICULTY_LEVELS
        assert len(set(profile.tiers)) == DIFFICULTY_LEVELS
        assert profile.reviewer
