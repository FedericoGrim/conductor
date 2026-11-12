from pathlib import Path

import pytest

from conductor.config import Config
from conductor.credentials import store_key
from conductor.settings import SCHEMA, SettingsError, export_settings, import_settings

CONFIG = """
default_privacy = "medium"
[privacy.medium]
max_parallel = 4
tiers = ["openrouter/a", "openrouter/b", "openrouter/c", "openrouter/d", "openrouter/e"]
reviewer = "openrouter/b"

[privacy.medium.providers.openrouter]
base_url = "https://openrouter.ai/api/v1"
api_key_env = "TEST_SETTINGS_KEY"
request_options = { provider = { data_collection = "deny" } }

[privacy.medium.providers.openrouter.models."a"]
request_options = { provider = { order = ["relace"], allow_fallbacks = true } }
"""


def config(tmp_path: Path) -> Config:
    path = tmp_path / "conductor.toml"
    path.write_text(CONFIG)
    return Config.load(path)


def test_export_writes_a_readable_file_with_metadata_last(tmp_path: Path) -> None:
    target = tmp_path / "settings.toml"
    export_settings(config(tmp_path), target, version="0.4.0")
    text = target.read_text()
    assert 'version = "0.4.0"' in text
    assert f"schema = {SCHEMA}" in text
    assert "exported_at" in text
    assert text.index("default_privacy") < text.index("[conductor]")
    assert "TEST_SETTINGS_KEY" in text


def test_export_never_contains_a_stored_key(tmp_path: Path) -> None:
    store_key("TEST_SETTINGS_KEY", "sk-very-secret")
    target = tmp_path / "settings.toml"
    export_settings(config(tmp_path), target, version="0.4.0")
    assert "sk-very-secret" not in target.read_text()


def test_import_round_trips_every_setting_including_routing(tmp_path: Path) -> None:
    exported = tmp_path / "settings.toml"
    original = config(tmp_path)
    export_settings(original, exported, version="0.4.0")
    destination = tmp_path / "imported.toml"

    result = import_settings(exported, destination)

    assert result.profiles == ("medium",)
    assert result.backup is None
    assert Config.load(destination) == original
    provider = Config.load(destination).profile("medium").providers["openrouter"]
    assert provider.model_options == {
        "a": {"provider": {"order": ["relace"], "allow_fallbacks": True}}
    }


def test_import_keeps_a_backup_and_reports_missing_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TEST_SETTINGS_KEY", raising=False)
    exported = tmp_path / "settings.toml"
    export_settings(config(tmp_path), exported, version="0.4.0")
    destination = tmp_path / "existing.toml"
    destination.write_text("# old\n")

    result = import_settings(exported, destination)

    assert result.backup == tmp_path / "existing.toml.bak"
    assert result.backup.read_text() == "# old\n"
    assert result.missing_keys == ("TEST_SETTINGS_KEY",)


def test_a_stored_key_counts_as_present(tmp_path: Path) -> None:
    store_key("TEST_SETTINGS_KEY", "sk")
    exported = tmp_path / "settings.toml"
    export_settings(config(tmp_path), exported, version="0.4.0")
    assert import_settings(exported, tmp_path / "out.toml").missing_keys == ()


def test_import_accepts_a_plain_configuration_without_metadata(tmp_path: Path) -> None:
    source = tmp_path / "conductor.toml"
    source.write_text(CONFIG)
    result = import_settings(source, tmp_path / "out.toml")
    assert result.profiles == ("medium",)
    assert Config.load(tmp_path / "out.toml").profile("medium").tiers[0] == ("openrouter/a",)


def test_import_refuses_a_newer_schema(tmp_path: Path) -> None:
    source = tmp_path / "settings.toml"
    source.write_text(f'default_privacy = "medium"\n[conductor]\nschema = {SCHEMA + 1}\n')
    with pytest.raises(SettingsError, match="schema"):
        import_settings(source, tmp_path / "out.toml")


def test_import_refuses_invalid_content_and_leaves_the_target_alone(tmp_path: Path) -> None:
    source = tmp_path / "settings.toml"
    source.write_text("not = [valid")
    destination = tmp_path / "existing.toml"
    destination.write_text("# keep me\n")
    with pytest.raises(SettingsError, match="read"):
        import_settings(source, destination)
    assert destination.read_text() == "# keep me\n"
    assert not (tmp_path / "existing.toml.bak").exists()


def test_import_refuses_a_configuration_that_does_not_load(tmp_path: Path) -> None:
    source = tmp_path / "settings.toml"
    source.write_text('default_privacy = "medium"\n[privacy.medium]\ntiers = []\nreviewer = "x"\n')
    with pytest.raises(SettingsError, match="invalid configuration"):
        import_settings(source, tmp_path / "out.toml")


def test_import_creates_missing_directories(tmp_path: Path) -> None:
    source = tmp_path / "conductor.toml"
    source.write_text(CONFIG)
    destination = tmp_path / "nested" / "dir" / "conductor.toml"
    import_settings(source, destination)
    assert destination.exists()
