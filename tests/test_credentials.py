import stat
from pathlib import Path

import pytest

from conductor.credentials import api_key, credentials_path, remove_key, store_key, stored_keys


@pytest.fixture(autouse=True)
def no_key_in_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TEST_CREDENTIALS_KEY", raising=False)


def test_credentials_live_under_the_user_data_directory(isolated_data_home: Path) -> None:
    assert credentials_path() == isolated_data_home / "conductor" / "auth.json"


def test_a_stored_key_is_readable_only_by_its_owner() -> None:
    store_key("TEST_CREDENTIALS_KEY", "sk-one")
    store_key("OTHER_KEY", "sk-two")

    assert stored_keys() == {"TEST_CREDENTIALS_KEY": "sk-one", "OTHER_KEY": "sk-two"}
    assert stat.S_IMODE(credentials_path().stat().st_mode) == 0o600
    assert stat.S_IMODE(credentials_path().parent.stat().st_mode) == 0o700


def test_storing_again_replaces_the_key_and_tightens_loose_permissions() -> None:
    store_key("TEST_CREDENTIALS_KEY", "sk-old")
    credentials_path().chmod(0o644)
    store_key("TEST_CREDENTIALS_KEY", "sk-new")

    assert stored_keys() == {"TEST_CREDENTIALS_KEY": "sk-new"}
    assert stat.S_IMODE(credentials_path().stat().st_mode) == 0o600


def test_remove_key_forgets_one_key_and_tolerates_unknown_names() -> None:
    store_key("TEST_CREDENTIALS_KEY", "sk-one")
    store_key("OTHER_KEY", "sk-two")
    remove_key("TEST_CREDENTIALS_KEY")
    remove_key("NEVER_STORED")
    assert stored_keys() == {"OTHER_KEY": "sk-two"}


def test_stored_keys_is_empty_without_a_file_or_with_a_broken_one() -> None:
    assert stored_keys() == {}
    credentials_path().parent.mkdir(parents=True)
    credentials_path().write_text("not json")
    assert stored_keys() == {}
    credentials_path().write_text('["a list"]')
    assert stored_keys() == {}


def test_api_key_prefers_the_environment_over_the_stored_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert api_key("TEST_CREDENTIALS_KEY") is None
    store_key("TEST_CREDENTIALS_KEY", "sk-stored")
    assert api_key("TEST_CREDENTIALS_KEY") == "sk-stored"
    monkeypatch.setenv("TEST_CREDENTIALS_KEY", "sk-env")
    assert api_key("TEST_CREDENTIALS_KEY") == "sk-env"
    monkeypatch.setenv("TEST_CREDENTIALS_KEY", "")
    assert api_key("TEST_CREDENTIALS_KEY") == "sk-stored"
