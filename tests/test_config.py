import tomllib
from pathlib import Path

import pytest

from conductor.config import Config, ConfigError, Profile, Provider, merge_options

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
        ("openrouter/cheap/model",),
        ("openrouter/mid/model",),
        ("openrouter/strong/model",),
    )
    assert medium.max_parallel == 4
    assert medium.providers["openrouter"].request_options == {
        "provider": {"data_collection": "deny"}
    }
    assert config.profile("low").max_parallel == 2
    assert config.profile("low").providers["openrouter"].request_options == {}


def test_default_privacy_is_used_when_none_given(tmp_path: Path) -> None:
    assert Config.load(write(tmp_path)).profile(None).name == "medium"


def test_unknown_privacy_level_fails(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="unknown privacy level 'max'"):
        Config.load(write(tmp_path)).profile("max")


def test_profile_without_tiers_fails(tmp_path: Path) -> None:
    broken = TOML.replace('tiers = ["openrouter/free/model:free", "openrouter/cheap/model"]\n', "")
    with pytest.raises(ConfigError, match="privacy.low: tiers must be a non-empty list"):
        Config.load(write(tmp_path, broken))


def test_models_for_tier_are_empty_beyond_the_strongest_tier(tmp_path: Path) -> None:
    profile = Config.load(write(tmp_path)).profile("low")
    assert profile.models_for_tier(0) == ("openrouter/free/model:free",)
    assert profile.models_for_tier(1) == ("openrouter/cheap/model",)
    assert profile.models_for_tier(7) == ()


def test_dump_round_trips_the_example_configuration(tmp_path: Path) -> None:
    example = Config.load(Path(__file__).parent.parent / "conductor.toml.example")
    written = tmp_path / "conductor.toml"
    written.write_text(example.dump())
    assert Config.load(written) == example


def test_dump_writes_one_tier_per_line_and_omits_empty_request_options() -> None:
    provider = Provider("openrouter", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY")
    profile = Profile(
        "low", {"openrouter": provider}, (("openrouter/a:free",), ("openrouter/b",)), ("brain",), 2
    )
    assert (
        Config("low", {"low": profile}).dump()
        == """\
# Written by `conductor setup`. Comments added by hand are lost on the next save.
default_privacy = "low"

[privacy.low]
max_parallel = 2
tiers = [
  "openrouter/a:free",
  "openrouter/b",
]
reviewer = "brain"

[privacy.low.providers.openrouter]
base_url = "https://openrouter.ai/api/v1"
api_key_env = "OPENROUTER_API_KEY"
"""
    )


def test_dump_quotes_unusual_names_and_nested_options(tmp_path: Path) -> None:
    provider = Provider(
        "p",
        "https://example.invalid/v1",
        "K",
        {"provider": {"only": ["a", "b"], "zdr": True}, "max tokens": 512},
    )
    profile = Profile("eu only", {"p": provider}, (('p/odd "name"',),), ("p/r",))
    config = Config("eu only", {"eu only": profile})
    written = tmp_path / "conductor.toml"
    written.write_text(config.dump())
    assert Config.load(written) == config


def test_reads_the_new_multi_provider_format(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        """
default_privacy = "medium"
[privacy.medium]
tiers = ["openrouter/a", "scaleway/b"]
reviewer = "scaleway/b"

[privacy.medium.providers.openrouter]
base_url = "https://openrouter.ai/api/v1"
api_key_env = "OPENROUTER_API_KEY"

[privacy.medium.providers.scaleway]
base_url = "https://api.scaleway.ai/v1"
api_key_env = "SCALEWAY_API_KEY"
""",
    )
    profile = Config.load(path).profile("medium")
    assert list(profile.providers) == ["openrouter", "scaleway"]
    assert profile.provider_for("scaleway/b").api_key_env == "SCALEWAY_API_KEY"
    assert profile.provider_for("openrouter/a").request_options == {}


def test_rejects_a_model_whose_provider_is_not_declared(tmp_path: Path) -> None:
    path = write(
        tmp_path,
        """
[privacy.medium]
tiers = ["openrouter/a", "scaleway/b"]
reviewer = "openrouter/a"
provider = "openrouter"
base_url = "https://openrouter.ai/api/v1"
api_key_env = "OPENROUTER_API_KEY"
""",
    )
    with pytest.raises(ConfigError, match="does not name one of the providers"):
        Config.load(path)


def test_the_example_configuration_is_the_built_in_default() -> None:
    from conductor.defaults import default_config

    example = Path(__file__).parent.parent / "conductor.toml.example"
    assert Config.load(example) == default_config()


MULTI_PROVIDER = """
default_privacy = "medium"
[privacy.medium]
tiers = ["openrouter/a", "openrouter/b"]
reviewer = "openrouter/a"

[privacy.medium.providers.openrouter]
base_url = "https://openrouter.ai/api/v1"
api_key_env = "OPENROUTER_API_KEY"
request_options = { provider = { data_collection = "deny" } }

[privacy.medium.providers.openrouter.models."b"]
request_options = { provider = { order = ["relace"], allow_fallbacks = true } }
"""


def test_reads_per_model_request_options() -> None:
    provider = Profile.from_dict(
        "medium", tomllib.loads(MULTI_PROVIDER)["privacy"]["medium"]
    ).providers["openrouter"]
    assert provider.model_options == {
        "b": {"provider": {"order": ["relace"], "allow_fallbacks": True}}
    }


def test_dump_round_trips_per_model_options(tmp_path: Path) -> None:
    profile = Profile.from_dict("medium", tomllib.loads(MULTI_PROVIDER)["privacy"]["medium"])
    config = Config("medium", {"medium": profile})
    written = tmp_path / "conductor.toml"
    written.write_text(config.dump())
    assert Config.load(written) == config
    assert ".providers.openrouter.models.b]" in written.read_text()


def test_rejects_options_for_a_model_the_profile_does_not_use() -> None:
    data = tomllib.loads(MULTI_PROVIDER)["privacy"]["medium"]
    data["providers"]["openrouter"]["models"] = {"ghost": {"request_options": {"sort": "price"}}}
    with pytest.raises(ConfigError, match="unknown model"):
        Profile.from_dict("medium", data)


def test_merge_options_is_recursive_and_the_override_wins() -> None:
    assert merge_options(
        {"provider": {"data_collection": "deny", "allow_fallbacks": True}, "temperature": 0},
        {"provider": {"order": ["relace"]}},
    ) == {
        "provider": {"data_collection": "deny", "allow_fallbacks": True, "order": ["relace"]},
        "temperature": 0,
    }


RETRY = MULTI_PROVIDER.replace(
    'reviewer = "openrouter/a"\n', 'reviewer = "openrouter/a"\nretry = { transient_attempts = 1 }\n'
)


def test_transient_attempts_default_to_three() -> None:
    profile = Profile.from_dict("medium", tomllib.loads(MULTI_PROVIDER)["privacy"]["medium"])
    assert profile.transient_attempts == 3


def test_reads_the_retry_table() -> None:
    profile = Profile.from_dict("medium", tomllib.loads(RETRY)["privacy"]["medium"])
    assert profile.transient_attempts == 1


@pytest.mark.parametrize("value", ["-1", '"many"', "true"])
def test_rejects_transient_attempts_that_are_not_a_count(value: str) -> None:
    text = RETRY.replace("transient_attempts = 1", f"transient_attempts = {value}")
    with pytest.raises(ConfigError, match="transient_attempts"):
        Profile.from_dict("medium", tomllib.loads(text)["privacy"]["medium"])


def test_dump_round_trips_the_retry_table(tmp_path: Path) -> None:
    profile = Profile.from_dict("medium", tomllib.loads(RETRY)["privacy"]["medium"])
    config = Config("medium", {"medium": profile})
    written = tmp_path / "conductor.toml"
    written.write_text(config.dump())
    assert Config.load(written) == config
    assert "retry = { transient_attempts = 1 }" in written.read_text()


def test_rejects_a_reviewer_whose_provider_is_not_https() -> None:
    text = MULTI_PROVIDER.replace("https://openrouter.ai/api/v1", "http://openrouter.ai/api/v1")
    with pytest.raises(ConfigError, match="reviewer .* https"):
        Profile.from_dict("medium", tomllib.loads(text)["privacy"]["medium"])


def test_a_brain_reviewer_does_not_need_an_https_provider() -> None:
    text = MULTI_PROVIDER.replace(
        "https://openrouter.ai/api/v1", "http://localhost:11434/v1"
    ).replace('reviewer = "openrouter/a"', 'reviewer = "brain"')
    profile = Profile.from_dict("medium", tomllib.loads(text)["privacy"]["medium"])
    assert profile.is_brain_review


FALLBACKS = """
default_privacy = "medium"
[privacy.medium]
tiers = ["openrouter/a", ["openrouter/b", "deepseek/b2"]]
reviewer = ["openrouter/r", "deepseek/r2"]

[privacy.medium.providers.openrouter]
base_url = "https://openrouter.ai/api/v1"
api_key_env = "OPENROUTER_API_KEY"

[privacy.medium.providers.deepseek]
base_url = "https://api.deepseek.com/v1"
api_key_env = "DEEPSEEK_API_KEY"

[privacy.medium.providers.deepseek.models."b2"]
request_options = { temperature = 0 }
"""


def fallback_profile(text: str = FALLBACKS) -> Profile:
    return Profile.from_dict("medium", tomllib.loads(text)["privacy"]["medium"])


def test_a_level_may_list_fallback_models_in_order() -> None:
    profile = fallback_profile()
    assert profile.tiers == (("openrouter/a",), ("openrouter/b", "deepseek/b2"))
    assert profile.models_for_tier(1) == ("openrouter/b", "deepseek/b2")
    assert profile.models_for_tier(2) == ()


def test_the_reviewer_may_be_a_list() -> None:
    assert fallback_profile().reviewers == ("openrouter/r", "deepseek/r2")


def test_a_plain_reviewer_is_a_one_model_list() -> None:
    profile = Profile.from_dict("medium", tomllib.loads(MULTI_PROVIDER)["privacy"]["medium"])
    assert profile.reviewers == ("openrouter/a",)


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ('["openrouter/b", "deepseek/b2"]', "[]", "level 2 must name at least one model"),
        ('["openrouter/b", "deepseek/b2"]', '["openrouter/b", 3]', "level 2 must name"),
        (
            '["openrouter/b", "deepseek/b2"]',
            '["openrouter/b", "deepseek/b2", "nope/x"]',
            "nope/x",
        ),
        ('["openrouter/r", "deepseek/r2"]', "[]", "reviewer must name at least one model"),
        ('["openrouter/r", "deepseek/r2"]', '["brain", "deepseek/r2"]', "brain"),
    ],
)
def test_rejects_malformed_lists(old: str, new: str, message: str) -> None:
    with pytest.raises(ConfigError, match=message):
        fallback_profile(FALLBACKS.replace(old, new))


def test_every_reviewer_needs_an_https_provider() -> None:
    text = FALLBACKS.replace("https://api.deepseek.com/v1", "http://api.deepseek.com/v1")
    with pytest.raises(ConfigError, match="deepseek/r2.*https"):
        fallback_profile(text)


def test_dump_writes_lists_only_for_levels_with_fallbacks(tmp_path: Path) -> None:
    config = Config("medium", {"medium": fallback_profile()})
    text = config.dump()
    assert '  "openrouter/a",\n' in text
    assert '  ["openrouter/b", "deepseek/b2"],\n' in text
    assert 'reviewer = ["openrouter/r", "deepseek/r2"]\n' in text
    written = tmp_path / "conductor.toml"
    written.write_text(text)
    assert Config.load(written) == config


HARNESS_MANAGED = """
default_privacy = "medium"
[privacy.medium]
tiers = ["openrouter/a", ["subscription/opus", "openrouter/b"]]
reviewer = "openrouter/a"

[privacy.medium.providers.openrouter]
base_url = "https://openrouter.ai/api/v1"
api_key_env = "OPENROUTER_API_KEY"

[privacy.medium.providers.subscription]
harness = "opencode"
"""


def managed_profile(text: str = HARNESS_MANAGED) -> Profile:
    return Profile.from_dict("medium", tomllib.loads(text)["privacy"]["medium"])


def test_a_provider_managed_by_its_harness_has_no_url_or_key() -> None:
    provider = managed_profile().providers["subscription"]
    assert (provider.base_url, provider.api_key_env, provider.harness) == ("", "", "opencode")
    assert managed_profile().providers["openrouter"].harness == "opencode"


def test_base_url_and_api_key_env_come_together() -> None:
    text = HARNESS_MANAGED.replace('harness = "opencode"', 'api_key_env = "K"')
    with pytest.raises(ConfigError, match="subscription: set both base_url and api_key_env"):
        managed_profile(text)


def test_an_unknown_harness_is_rejected() -> None:
    text = HARNESS_MANAGED.replace('harness = "opencode"', 'harness = "emacs"')
    with pytest.raises(ConfigError, match="subscription: unknown harness 'emacs'"):
        managed_profile(text)


def test_a_provider_without_url_cannot_review() -> None:
    text = HARNESS_MANAGED.replace('reviewer = "openrouter/a"', 'reviewer = "subscription/opus"')
    with pytest.raises(ConfigError, match="reviewer 'subscription/opus'.*no base_url"):
        managed_profile(text)


def test_dump_omits_what_a_managed_provider_does_not_have(tmp_path: Path) -> None:
    config = Config("medium", {"medium": managed_profile()})
    text = config.dump()
    section = text[text.index("[privacy.medium.providers.subscription]") :]
    assert "base_url" not in section
    assert "harness" not in section
    written = tmp_path / "conductor.toml"
    written.write_text(text)
    assert Config.load(written) == config
