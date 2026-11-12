from dataclasses import replace
from pathlib import Path

import pytest

from conductor.config import Config, Provider
from conductor.defaults import DIFFICULTY_LEVELS
from conductor.setup_state import (
    KNOWN_PROVIDERS,
    KnownProvider,
    ProfileDraft,
    ProviderDraft,
    SetupError,
    SetupState,
)
from tests.factories import make_profile

TIERS = tuple(f"openrouter/m{level}" for level in range(1, 6))

CONFIG = Config(
    "medium",
    {
        "low": make_profile(name="low", tiers=TIERS, reviewer="openrouter/m5", max_parallel=2),
        "medium": make_profile(name="medium", tiers=TIERS, reviewer="openrouter/m4"),
    },
)


def state() -> SetupState:
    return SetupState.from_config(CONFIG)


def scaleway() -> KnownProvider:
    return KnownProvider(
        "Scaleway (EU)", "scaleway", "https://api.scaleway.ai/v1", "SCALEWAY_API_KEY"
    )


def test_known_providers_are_either_https_with_a_key_or_managed_by_their_harness() -> None:
    assert [known.name for known in KNOWN_PROVIDERS] == [
        "openrouter",
        "openrouter",
        "vercel",
        "scaleway",
        "opencode",
        "deepseek",
        "claude-code",
    ]
    for known in KNOWN_PROVIDERS:
        if known.is_managed:
            assert known.base_url == "" and known.api_key_env == ""
            assert known.harness == "claude-code"
        else:
            assert known.base_url.startswith("https://")
            assert known.api_key_env.isupper()
            assert known.harness == "opencode"


def test_adding_the_claude_code_provider_keeps_it_endpointless() -> None:
    model = state()
    provider = model.add_provider(next(k for k in KNOWN_PROVIDERS if k.name == "claude-code"))
    assert (provider.base_url, provider.api_key_env, provider.harness) == ("", "", "claude-code")
    model.set_tier(1, "claude-code/sonnet")
    assert model.to_config().profile("low").tiers[0] == ("claude-code/sonnet",)


def test_a_managed_provider_cannot_review() -> None:
    model = state()
    model.add_provider(next(k for k in KNOWN_PROVIDERS if k.name == "claude-code"))
    model.set_reviewer("claude-code/sonnet")
    assert any("no endpoint" in problem for problem in model.problems())


def test_defaults_carry_three_profiles_with_five_filled_levels() -> None:
    model = SetupState.defaults()
    assert [profile.name for profile in model.profiles] == ["low", "medium", "high"]
    assert all(len(profile.filled()) == DIFFICULTY_LEVELS for profile in model.profiles)
    assert model.problems() == []
    assert model.default_privacy == "medium"


def test_from_config_pads_missing_levels_and_keeps_providers() -> None:
    short = SetupState.from_config(
        Config("low", {"low": make_profile(name="low", tiers=("openrouter/a",))})
    )
    draft = short.draft()
    assert draft.tiers == ["openrouter/a", "", "", "", ""]
    assert list(draft.providers) == ["openrouter"]
    assert draft.providers["openrouter"].base_url == "https://openrouter.ai/api/v1"


def test_to_config_round_trips_through_dump_and_load(tmp_path: Path) -> None:
    written = tmp_path / "conductor.toml"
    written.write_text(state().to_config().dump())
    assert Config.load(written) == CONFIG


def test_drafts_keep_the_retry_limit_of_a_profile() -> None:
    profile = replace(make_profile(name="low", tiers=TIERS), transient_attempts=7)
    draft = ProfileDraft.from_profile(profile)
    assert draft.to_profile() == profile


def test_select_clamps_to_the_available_profiles() -> None:
    model = state()
    model.select(1)
    assert model.selected == 1
    model.select(99)
    assert model.selected == 1
    model.select(-5)
    assert model.selected == 0


def test_add_profile_starts_with_the_chosen_provider_and_empty_levels() -> None:
    model = state()
    profile = model.add_profile("high", scaleway())
    assert list(profile.providers) == ["scaleway"]
    assert profile.tiers == [""] * DIFFICULTY_LEVELS
    assert profile.reviewer == ""
    assert model.profiles[-1] is profile
    assert model.selected == 2


def test_add_profile_refuses_duplicates_and_bad_names() -> None:
    model = state()
    with pytest.raises(SetupError, match="already exists"):
        model.add_profile("low", scaleway())
    for name in ("", "with space", "UPPER", "dot.name"):
        with pytest.raises(SetupError, match="lower-case"):
            model.add_profile(name, scaleway())


def test_remove_profile_keeps_the_selection_inside_the_list() -> None:
    model = state()
    model.select(1)
    model.remove_profile("medium")
    assert [profile.name for profile in model.profiles] == ["low"]
    assert model.selected == 0
    with pytest.raises(SetupError, match="unknown profile"):
        model.remove_profile("medium")


def test_providers_can_be_added_and_removed() -> None:
    model = state()
    provider = model.add_provider(scaleway())
    assert isinstance(provider, ProviderDraft)
    assert list(model.draft().providers) == ["openrouter", "scaleway"]
    with pytest.raises(SetupError, match="already exists"):
        model.add_provider(scaleway())
    model.remove_provider("scaleway")
    assert list(model.draft().providers) == ["openrouter"]
    with pytest.raises(SetupError, match="unknown provider"):
        model.remove_provider("scaleway")


def test_removing_a_provider_clears_the_levels_that_used_it() -> None:
    model = state()
    model.add_provider(scaleway())
    model.set_tier(3, "scaleway/glm-5.3")
    model.set_reviewer("scaleway/glm-5.3")
    model.remove_provider("scaleway")
    assert model.draft().tiers[2] == ""
    assert model.draft().reviewer == ""
    assert model.draft().tiers[0] == "openrouter/m1"


def test_a_level_needs_a_known_provider_and_a_unique_model() -> None:
    model = state()
    with pytest.raises(SetupError, match="add provider 'scaleway' first"):
        model.set_tier(1, "scaleway/glm-5.3")
    with pytest.raises(SetupError, match="already a tier"):
        model.set_tier(1, "openrouter/m2")
    with pytest.raises(SetupError, match="model must not be empty"):
        model.set_tier(1, " ")
    for level in (0, 6):
        with pytest.raises(SetupError, match="between 1 and 5"):
            model.set_tier(level, "openrouter/x")


def test_a_level_can_be_filled_and_cleared() -> None:
    model = state()
    model.set_tier(3, "openrouter/strong")
    assert model.draft().tiers[2] == "openrouter/strong"
    model.clear_tier(3)
    assert model.draft().tiers[2] == ""
    with pytest.raises(SetupError, match="between 1 and 5"):
        model.clear_tier(9)


def test_base_url_and_key_variable_are_validated() -> None:
    model = state()
    assert model.set_base_url("openrouter", "https://eu.openrouter.ai/api/v1").base_url.startswith(
        "https://eu"
    )
    with pytest.raises(SetupError, match="https"):
        model.set_base_url("openrouter", "http://insecure")
    assert model.set_api_key_env("openrouter", "MY_KEY").api_key_env == "MY_KEY"
    with pytest.raises(SetupError, match="upper-case"):
        model.set_api_key_env("openrouter", "my-key")
    with pytest.raises(SetupError, match="unknown provider"):
        model.set_base_url("nope", "https://x")


def test_reviewer_accepts_a_model_with_a_provider_or_the_brain() -> None:
    model = state()
    assert model.set_reviewer("brain").reviewer == "brain"
    assert model.set_reviewer("openrouter/m1").reviewer == "openrouter/m1"
    with pytest.raises(SetupError, match="reviewer"):
        model.set_reviewer("  ")
    with pytest.raises(SetupError, match="no provider"):
        model.set_reviewer("scaleway/glm-5.3")


def test_default_privacy_must_be_a_profile() -> None:
    model = state()
    model.set_default_privacy("low")
    assert model.default_privacy == "low"
    with pytest.raises(SetupError, match="unknown profile"):
        model.set_default_privacy("high")


def test_problems_lists_every_empty_level_and_missing_piece() -> None:
    assert state().problems() == []
    model = state()
    model.add_profile("empty", scaleway())
    assert model.problems() == [
        "profiles.empty: difficulty 1 has no model",
        "profiles.empty: difficulty 2 has no model",
        "profiles.empty: difficulty 3 has no model",
        "profiles.empty: difficulty 4 has no model",
        "profiles.empty: difficulty 5 has no model",
        "profiles.empty: reviewer must be set",
    ]
    model.select(0)
    model.clear_tier(2)
    assert "profiles.low: difficulty 2 has no model" in model.problems()
    for profile in list(model.profiles):
        model.remove_profile(profile.name)
    assert model.problems() == ["at least one profile is required"]


def test_model_options_survive_a_round_trip_through_the_editor(tmp_path: Path) -> None:
    provider = ProviderDraft("openrouter", "https://openrouter.ai/api/v1", "K")
    provider.model_options = {"m1": {"provider": {"order": ["relace"]}}}
    model = SetupState(
        [ProfileDraft("medium", {"openrouter": provider}, list(TIERS), "openrouter/m5")], "medium"
    )
    written = tmp_path / "conductor.toml"
    written.write_text(model.to_config().dump())
    again = SetupState.from_config(Config.load(written))
    assert again.draft().providers["openrouter"].model_options == {
        "m1": {"provider": {"order": ["relace"]}}
    }


def fallback_config() -> Config:
    profile = make_profile(name="medium", tiers=TIERS, reviewer="openrouter/m4")
    profile = replace(
        profile,
        providers={
            **profile.providers,
            "scaleway": Provider("scaleway", "https://api.scaleway.ai/v1", "SCALEWAY_API_KEY"),
        },
        tiers=(TIERS[0:1], (TIERS[1], "scaleway/b2", "openrouter/b3"), *[(t,) for t in TIERS[2:]]),
        reviewers=("openrouter/m4", "scaleway/r2"),
    )
    return Config("medium", {"medium": profile})


def test_drafts_keep_the_fallback_models_unchanged() -> None:
    config = fallback_config()
    assert SetupState.from_config(config).to_config() == config


def test_removing_a_provider_drops_its_fallback_models() -> None:
    model = SetupState.from_config(fallback_config())
    model.remove_provider("scaleway")
    profile = model.to_config().profile("medium")
    assert profile.tiers[1] == (TIERS[1], "openrouter/b3")
    assert profile.reviewers == ("openrouter/m4",)


def test_a_brain_reviewer_drops_the_reviewer_fallbacks() -> None:
    model = SetupState.from_config(fallback_config())
    model.set_reviewer("brain")
    assert model.to_config().profile("medium").reviewers == ("brain",)


def test_a_level_takes_fallbacks_in_order_and_drops_the_last_one() -> None:
    model = state()
    model.add_provider(scaleway())
    model.add_fallback(2, "scaleway/glm-5.3")
    model.add_fallback(2, "openrouter/m1")
    assert model.draft().fallbacks[1] == ["scaleway/glm-5.3", "openrouter/m1"]
    model.remove_fallback(2)
    assert model.to_config().profile("low").tiers[1] == ("openrouter/m2", "scaleway/glm-5.3")


def test_a_fallback_needs_a_level_model_a_known_provider_and_no_duplicate() -> None:
    model = state()
    with pytest.raises(SetupError, match="add provider 'scaleway' first"):
        model.add_fallback(1, "scaleway/glm-5.3")
    with pytest.raises(SetupError, match="already in difficulty 1"):
        model.add_fallback(1, "openrouter/m1")
    model.add_fallback(1, "openrouter/m2")
    with pytest.raises(SetupError, match="already in difficulty 1"):
        model.add_fallback(1, "openrouter/m2")
    model.clear_tier(3)
    with pytest.raises(SetupError, match="difficulty 3 has no model"):
        model.add_fallback(3, "openrouter/x")
    with pytest.raises(SetupError, match="between 1 and 5"):
        model.add_fallback(6, "openrouter/x")
    with pytest.raises(SetupError, match="no fallback"):
        model.remove_fallback(4)


def test_the_reviewer_takes_fallbacks_unless_it_is_the_brain() -> None:
    model = state()
    model.add_reviewer_fallback("openrouter/m4")
    assert model.to_config().profile("low").reviewers == ("openrouter/m5", "openrouter/m4")
    with pytest.raises(SetupError, match="already a reviewer"):
        model.add_reviewer_fallback("openrouter/m5")
    model.clear_reviewer_fallbacks()
    assert model.to_config().profile("low").reviewers == ("openrouter/m5",)
    model.set_reviewer("brain")
    with pytest.raises(SetupError, match="brain"):
        model.add_reviewer_fallback("openrouter/m4")


def test_drafts_keep_the_harness_of_a_provider() -> None:
    managed = Provider("subscription", "", "", harness="opencode")
    assert ProviderDraft.from_provider(managed).to_provider() == managed
