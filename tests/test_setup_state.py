from pathlib import Path

import pytest

from conductor.config import Config, Profile
from conductor.setup_state import (
    KNOWN_PROVIDERS,
    KnownProvider,
    ProfileDraft,
    SetupError,
    SetupState,
)

CONFIG = Config(
    "medium",
    {
        "low": Profile(
            "low",
            "openrouter",
            "https://openrouter.ai/api/v1",
            "OPENROUTER_API_KEY",
            ("openrouter/a:free", "openrouter/b"),
            "openrouter/a:free",
            2,
        ),
        "medium": Profile(
            "medium",
            "openrouter",
            "https://openrouter.ai/api/v1",
            "OPENROUTER_API_KEY",
            ("openrouter/b", "openrouter/c"),
            "openrouter/c",
            4,
            {"provider": {"data_collection": "deny"}},
        ),
    },
)


def state() -> SetupState:
    return SetupState.from_config(CONFIG)


def test_known_providers_cover_the_gateways_conductor_supports() -> None:
    labels = {known.label: known for known in KNOWN_PROVIDERS}
    assert set(labels) == {
        "OpenRouter",
        "OpenRouter (EU)",
        "Vercel AI Gateway",
        "Scaleway (EU)",
        "OpenCode Zen",
        "DeepSeek",
        "Other (fill in by hand)",
    }
    assert labels["OpenRouter (EU)"].provider == "openrouter"
    assert labels["OpenRouter (EU)"].base_url.startswith("https://eu.openrouter.ai")
    assert all(known.api_key_env.isupper() for known in labels.values())
    assert all(
        known.base_url == "" or known.base_url.startswith("https://") for known in labels.values()
    )


def test_from_config_keeps_order_values_and_selection() -> None:
    model = state()
    assert [profile.name for profile in model.profiles] == ["low", "medium"]
    assert model.default_privacy == "medium"
    assert model.selected == 0
    assert model.selected_profile() == ProfileDraft(
        "low",
        "openrouter",
        "https://openrouter.ai/api/v1",
        "OPENROUTER_API_KEY",
        2,
        ["openrouter/a:free", "openrouter/b"],
        "openrouter/a:free",
        {},
    )


def test_to_config_round_trips_through_dump_and_load(tmp_path: Path) -> None:
    written = tmp_path / "conductor.toml"
    written.write_text(state().to_config().dump())
    assert Config.load(written) == CONFIG


def test_select_clamps_to_the_available_profiles() -> None:
    model = state()
    model.select(1)
    assert model.selected == 1
    model.select(99)
    assert model.selected == 1
    model.select(-5)
    assert model.selected == 0


def test_add_profile_appends_it_and_selects_it() -> None:
    model = state()
    known = KnownProvider(
        "Scaleway (EU)", "scaleway", "https://api.scaleway.ai/v1", "SCALEWAY_API_KEY"
    )
    profile = model.add_profile("high", known)
    assert profile.tiers == []
    assert profile.reviewer == ""
    assert profile.request_options == {}
    assert model.profiles[-1] is profile
    assert model.selected == 2


def test_add_profile_refuses_duplicates_and_bad_names() -> None:
    model = state()
    known = KNOWN_PROVIDERS[0]
    with pytest.raises(SetupError, match="already exists"):
        model.add_profile("low", known)
    for name in ("", "with space", "UPPER", "dot.name"):
        with pytest.raises(SetupError, match="lower-case"):
            model.add_profile(name, known)


def test_remove_profile_keeps_the_selection_inside_the_list() -> None:
    model = state()
    model.select(1)
    model.remove_profile("medium")
    assert [profile.name for profile in model.profiles] == ["low"]
    assert model.selected == 0
    with pytest.raises(SetupError, match="unknown profile"):
        model.remove_profile("medium")


def test_tiers_can_be_added_removed_and_reordered() -> None:
    model = state()
    model.select(1)
    model.add_tier("openrouter/d")
    assert model.draft().tiers[-1] == "openrouter/d"
    model.move_tier(2, -1)
    assert model.draft().tiers == ["openrouter/b", "openrouter/d", "openrouter/c"]
    model.move_tier(0, -1)
    assert model.draft().tiers == ["openrouter/b", "openrouter/d", "openrouter/c"]
    model.remove_tier(1)
    assert model.draft().tiers == ["openrouter/b", "openrouter/c"]
    model.profiles.clear()
    with pytest.raises(SetupError, match="no profile selected"):
        model.add_tier("openrouter/e")


def test_a_tier_cannot_be_added_twice_and_an_index_must_exist() -> None:
    model = state()
    with pytest.raises(SetupError, match="already a tier"):
        model.add_tier("openrouter/b")
    with pytest.raises(SetupError, match="no tier"):
        model.remove_tier(9)
    with pytest.raises(SetupError, match="no tier"):
        model.move_tier(9, 1)


def test_set_reviewer_accepts_a_model_or_the_brain() -> None:
    model = state()
    assert model.set_reviewer("brain").reviewer == "brain"
    assert model.set_reviewer("openrouter/c").reviewer == "openrouter/c"
    with pytest.raises(SetupError, match="reviewer"):
        model.set_reviewer("  ")


def test_default_privacy_must_be_a_profile() -> None:
    model = state()
    model.set_default_privacy("low")
    assert model.default_privacy == "low"
    with pytest.raises(SetupError, match="unknown profile"):
        model.set_default_privacy("high")


def test_problems_lists_everything_that_blocks_a_save() -> None:
    assert state().problems() == []
    model = state()
    model.add_profile("empty", KNOWN_PROVIDERS[0])
    model.set_default_privacy("low")
    assert model.problems() == [
        "profiles.empty: tiers must not be empty",
        "profiles.empty: reviewer must be set",
    ]
    model.remove_profile("medium")
    assert model.problems() == [
        "profiles.empty: tiers must not be empty",
        "profiles.empty: reviewer must be set",
    ]
    model.set_default_privacy("empty")
    assert model.problems() == [
        "profiles.empty: tiers must not be empty",
        "profiles.empty: reviewer must be set",
    ]
    model.remove_profile("empty")
    model.remove_profile("low")
    assert model.profiles == []
    assert model.problems() == ["at least one profile is required"]
