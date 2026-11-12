from collections.abc import Callable
from pathlib import Path

from conductor.catalog import CatalogError, CatalogModel
from conductor.config import Config
from conductor.defaults import DIFFICULTY_LEVELS
from conductor.setup_state import KNOWN_PROVIDERS, ProviderDraft, SetupState
from conductor.setup_tui import (
    BASED,
    CATALOG,
    EDITOR,
    KEY,
    KEYPROVIDER,
    MODEL,
    NAME,
    PROFILES,
    PROVIDER,
    PROVIDERADD,
    PROVIDERS,
    Editor,
    render,
    save_config,
)

FLASH = CatalogModel("deepseek/flash", 0.3, 1.2, 128000, True)
SONNET = CatalogModel("anthropic/sonnet", 2.0, 10.0, 500000, True)

CONFIG = """
default_privacy = "medium"
[privacy.medium]
max_parallel = 4
tiers = [
  "openrouter/m1",
  "openrouter/m2",
  "openrouter/m3",
  "openrouter/m4",
  "openrouter/m5",
]
reviewer = "openrouter/m5"

[privacy.medium.providers.openrouter]
base_url = "https://openrouter.ai/api/v1"
api_key_env = "TEST_TUI_KEY"
"""


def editor(
    tmp_path: Path, fetcher: Callable[[str], list[CatalogModel]] | None = None, store: object = None
) -> Editor:
    path = tmp_path / "conductor.toml"
    path.write_text(CONFIG)
    return Editor(
        SetupState.from_config(Config.load(path)),
        path=str(path),
        catalog=fetcher or (lambda url: [SONNET, FLASH]),
        store=store or (lambda name, value: None),  # type: ignore[arg-type]
    )


def type_text(view: Editor, text: str) -> None:
    for character in text:
        view.handle_key(character)


def test_the_profiles_screen_counts_filled_levels_and_marks_the_default(tmp_path: Path) -> None:
    lines = render(editor(tmp_path))
    assert lines[0].startswith("Conductor setup")
    assert lines[1] == "> medium  (5/5, default)"
    assert any(line.startswith("a add") for line in lines)


def test_a_creates_a_profile_with_the_chosen_provider(tmp_path: Path) -> None:
    view = editor(tmp_path)
    view.handle_key("a")
    assert view.screen == PROVIDER
    view.handle_key("down")
    view.handle_key("down")
    view.handle_key("enter")
    assert view.screen == NAME
    type_text(view, "cheap-eu")
    view.handle_key("enter")
    assert view.screen == EDITOR
    draft = view.state.draft()
    assert draft.name == "cheap-eu"
    assert list(draft.providers) == ["vercel"]
    assert draft.tiers == [""] * DIFFICULTY_LEVELS
    assert "5. (no model yet)" in "\n".join(render(view))


def test_a_duplicate_profile_name_is_reported(tmp_path: Path) -> None:
    view = editor(tmp_path)
    view.handle_key("a")
    view.handle_key("enter")
    type_text(view, "medium")
    view.handle_key("enter")
    assert view.screen == NAME
    assert "already exists" in view.message
    assert len(view.state.profiles) == 1


def test_the_editor_lists_the_five_difficulty_levels(tmp_path: Path) -> None:
    view = editor(tmp_path)
    view.handle_key("enter")
    text = "\n".join(render(view))
    for level in range(1, 6):
        assert f"{level}. openrouter/m{level}" in text
    assert "reviewer  openrouter/m5" in text
    view.handle_key("down")
    assert view.level == 2


def test_the_catalog_merges_the_providers_of_the_profile_and_sets_a_level(tmp_path: Path) -> None:
    seen: list[str] = []

    def fetcher(url: str) -> list[CatalogModel]:
        seen.append(url)
        return [SONNET, FLASH]

    view = editor(tmp_path, fetcher)
    view.handle_key("enter")
    view.handle_key("d")
    view.handle_key("a")
    assert view.screen == CATALOG
    assert seen == ["https://openrouter.ai/api/v1"]
    assert [model.id for model in view.models] == [
        "openrouter/deepseek/flash",
        "openrouter/anthropic/sonnet",
    ]
    type_text(view, "sonnet")
    view.handle_key("enter")
    assert view.screen == EDITOR
    assert view.state.draft().tiers[0] == "openrouter/anthropic/sonnet"


def test_a_broken_provider_is_reported_and_the_others_still_list(tmp_path: Path) -> None:
    def fetcher(url: str) -> list[CatalogModel]:
        raise CatalogError(f"{url} could not be read")

    view = editor(tmp_path, fetcher)
    view.handle_key("enter")
    view.handle_key("a")
    assert view.models == []
    assert "could not be read" in view.message


def test_a_model_can_be_typed_by_hand_and_a_level_cleared(tmp_path: Path) -> None:
    view = editor(tmp_path)
    view.handle_key("enter")
    view.handle_key("t")
    assert view.screen == MODEL
    type_text(view, "openrouter/typed/model")
    view.handle_key("enter")
    assert view.screen == EDITOR
    assert view.state.draft().tiers[0] == "openrouter/typed/model"
    view.handle_key("d")
    assert view.state.draft().tiers[0] == ""


def test_providers_can_be_added_edited_and_removed(tmp_path: Path) -> None:
    view = editor(tmp_path)
    view.handle_key("enter")
    view.handle_key("P")
    assert view.screen == PROVIDERS
    view.handle_key("a")
    assert view.screen == PROVIDERADD
    view.handle_key("down")
    view.handle_key("down")
    view.handle_key("down")
    view.handle_key("enter")
    assert view.screen == PROVIDERS
    assert list(view.state.draft().providers) == ["openrouter", "scaleway"]
    view.handle_key("down")
    view.handle_key("b")
    assert view.screen == BASED
    type_text(view, "https://api.scaleway.ai/v2")
    view.handle_key("enter")
    assert view.state.draft().providers["scaleway"].base_url.endswith("/v2")
    view.handle_key("e")
    type_text(view, "SCW_KEY")
    view.handle_key("enter")
    assert view.state.draft().providers["scaleway"].api_key_env == "SCW_KEY"
    view.handle_key("esc")
    for _ in range(4):
        view.handle_key("down")
    view.handle_key("t")
    type_text(view, "scaleway/glm-5.3")
    view.handle_key("enter")
    assert view.state.draft().tiers[4] == "scaleway/glm-5.3"
    view.handle_key("P")
    view.handle_key("down")
    view.handle_key("d")
    assert list(view.state.draft().providers) == ["openrouter"]
    assert view.state.draft().tiers[4] == ""
    assert "difficulty 5 has no model" in " ".join(view.state.problems())


def test_a_key_is_stored_for_the_chosen_provider(tmp_path: Path) -> None:
    stored: list[tuple[str, str]] = []

    def store(name: str, value: str) -> None:
        stored.append((name, value))

    view = editor(tmp_path, store=store)
    view.handle_key("enter")
    view.handle_key("k")
    assert view.screen == KEY
    type_text(view, "sk-secret")
    assert "sk-secret" not in "\n".join(render(view))
    view.handle_key("enter")
    assert view.screen == EDITOR
    assert stored == [("TEST_TUI_KEY", "sk-secret")]
    assert "key of openrouter stored" in view.message


def test_with_several_providers_the_key_screen_asks_which_one(tmp_path: Path) -> None:
    view = editor(tmp_path)
    view.handle_key("enter")
    view.handle_key("P")
    view.handle_key("a")
    view.handle_key("down")
    view.handle_key("down")
    view.handle_key("down")
    view.handle_key("enter")
    view.handle_key("esc")
    view.handle_key("k")
    assert view.screen == KEYPROVIDER
    view.handle_key("enter")
    assert view.screen == KEY
    assert view.target == "openrouter"


def test_the_reviewer_cycles_between_the_levels_and_the_brain(tmp_path: Path) -> None:
    view = editor(tmp_path)
    view.handle_key("enter")
    view.handle_key("r")
    assert view.state.draft().reviewer == "brain"
    view.handle_key("r")
    assert view.state.draft().reviewer == "openrouter/m1"
    view.handle_key("m")
    assert view.state.draft().max_parallel == 5
    view.handle_key("M")
    view.handle_key("M")
    assert view.state.draft().max_parallel == 3


def test_saving_refuses_a_configuration_with_an_empty_level(tmp_path: Path) -> None:
    view = editor(tmp_path)
    view.handle_key("enter")
    view.handle_key("d")
    view.handle_key("esc")
    assert view.handle_key("s") is False
    assert view.screen == PROFILES
    assert "difficulty 1 has no model" in view.message
    assert (tmp_path / "conductor.toml").read_text() == CONFIG


def test_saving_writes_the_config_and_keeps_a_backup(tmp_path: Path) -> None:
    view = editor(tmp_path)
    view.handle_key("enter")
    view.handle_key("r")
    view.handle_key("esc")
    assert view.handle_key("s") is True
    path = tmp_path / "conductor.toml"
    assert 'reviewer = "brain"' in path.read_text()
    assert (tmp_path / "conductor.toml.bak").read_text() == CONFIG
    assert Config.load(path).profiles["medium"].is_brain_review


def test_save_config_without_an_existing_file_creates_it(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "conductor.toml"
    path.parent.mkdir()
    save_config(path, SetupState.defaults())
    assert "difficulty" not in path.read_text()
    assert "providers.openrouter" in path.read_text()
    assert not (tmp_path / "nested" / "conductor.toml.bak").exists()


def test_quit_without_saving_leaves_the_file_alone(tmp_path: Path) -> None:
    view = editor(tmp_path)
    view.handle_key("enter")
    view.handle_key("d")
    view.handle_key("esc")
    assert view.handle_key("q") is True
    assert (tmp_path / "conductor.toml").read_text() == CONFIG


def test_the_defaults_of_the_setup_are_the_defaults_of_conductor() -> None:
    assert [profile.name for profile in SetupState.defaults().profiles] == ["low", "medium", "high"]


def test_known_providers_are_offered_when_adding_one(tmp_path: Path) -> None:
    view = editor(tmp_path)
    view.handle_key("enter")
    view.handle_key("P")
    view.handle_key("a")
    text = "\n".join(render(view))
    for known in KNOWN_PROVIDERS:
        assert known.label in text
    assert isinstance(view.state.draft().providers["openrouter"], ProviderDraft)


def test_a_level_gets_fallbacks_from_the_catalog_or_typed_and_drops_the_last(
    tmp_path: Path,
) -> None:
    view = editor(tmp_path)
    view.handle_key("enter")
    view.handle_key("down")
    view.handle_key("f")
    assert view.screen == CATALOG
    type_text(view, "sonnet")
    view.handle_key("enter")
    assert view.screen == EDITOR
    view.handle_key("F")
    assert view.screen == MODEL
    type_text(view, "openrouter/typed/model")
    view.handle_key("enter")
    assert view.state.draft().tiers[1] == "openrouter/m2"
    assert view.state.draft().fallbacks[1] == [
        "openrouter/anthropic/sonnet",
        "openrouter/typed/model",
    ]
    text = "\n".join(render(view))
    assert "2. openrouter/m2 → openrouter/anthropic/sonnet, openrouter/typed/model" in text
    view.handle_key("x")
    assert view.state.draft().fallbacks[1] == ["openrouter/anthropic/sonnet"]
    view.handle_key("down")
    view.handle_key("x")
    assert "no fallback" in view.message


def test_the_reviewer_gets_fallbacks_and_loses_them_when_it_becomes_the_brain(
    tmp_path: Path,
) -> None:
    view = editor(tmp_path)
    view.handle_key("enter")
    view.handle_key("v")
    assert view.screen == CATALOG
    type_text(view, "flash")
    view.handle_key("enter")
    assert "reviewer  openrouter/m5 → openrouter/deepseek/flash" in "\n".join(render(view))
    view.handle_key("V")
    assert view.state.draft().reviewer_fallbacks == []
    view.handle_key("v")
    view.handle_key("enter")
    view.handle_key("r")
    assert view.state.draft().reviewer == "brain"
    assert view.state.draft().reviewer_fallbacks == []


def test_a_managed_provider_says_so_and_offers_no_endpoint_to_edit(tmp_path: Path) -> None:
    view = editor(tmp_path)
    view.state.add_provider(next(k for k in KNOWN_PROVIDERS if k.name == "claude-code"))
    view.handle_key("enter")
    view.handle_key("P")
    assert "claude-code  (managed by claude-code)" in "\n".join(render(view))
    view.handle_key("down")
    view.handle_key("b")
    assert "managed" in view.message
    assert view.screen == PROVIDERS
