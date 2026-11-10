from pathlib import Path

import pytest

from conductor.config import Config, ConfigError

TOML = """
default_privacy = "medium"

[privacy.low]
provider = "openrouter"
base_url = "https://openrouter.ai/api/v1"
api_key_env = "OPENROUTER_API_KEY"
max_parallel = 2
tiers = ["openrouter/free/model:free", "openrouter/cheap/model"]
reviewer = "openrouter/cheap/model"

[privacy.medium]
provider = "openrouter"
base_url = "https://openrouter.ai/api/v1"
api_key_env = "OPENROUTER_API_KEY"
tiers = ["openrouter/cheap/model", "openrouter/mid/model", "openrouter/strong/model"]
reviewer = "openrouter/mid/model"
request_options = { provider = { data_collection = "deny" } }
"""


def write(tmp_path: Path, text: str = TOML) -> Path:
    path = tmp_path / "conductor.toml"
    path.write_text(text)
    return path


def test_loads_profile_with_defaults(tmp_path: Path) -> None:
    config = Config.load(write(tmp_path))
    medium = config.profile("medium")
    assert medium.name == "medium"
    assert medium.tiers == (
        "openrouter/cheap/model",
        "openrouter/mid/model",
        "openrouter/strong/model",
    )
    assert medium.max_parallel == 4
    assert medium.request_options == {"provider": {"data_collection": "deny"}}
    assert config.profile("low").max_parallel == 2
    assert config.profile("low").request_options == {}


def test_default_privacy_is_used_when_none_given(tmp_path: Path) -> None:
    assert Config.load(write(tmp_path)).profile(None).name == "medium"


def test_unknown_privacy_level_fails(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="unknown privacy level 'max'"):
        Config.load(write(tmp_path)).profile("max")


def test_profile_without_tiers_fails(tmp_path: Path) -> None:
    broken = TOML.replace('tiers = ["openrouter/free/model:free", "openrouter/cheap/model"]\n', "")
    with pytest.raises(ConfigError, match="privacy.low: tiers must be a non-empty list"):
        Config.load(write(tmp_path, broken))


def test_model_for_difficulty_caps_at_strongest_tier(tmp_path: Path) -> None:
    profile = Config.load(write(tmp_path)).profile("low")
    assert profile.model_for_tier(0) == "openrouter/free/model:free"
    assert profile.model_for_tier(1) == "openrouter/cheap/model"
    assert profile.model_for_tier(7) is None
