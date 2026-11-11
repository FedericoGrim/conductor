from collections.abc import Callable
from pathlib import Path

from conductor.catalog import CatalogError, CatalogModel
from conductor.config import Config
from conductor.setup_state import SetupState
from conductor.setup_tui import (
    CATALOG,
    EDITOR,
    KEY,
    NAME,
    PROFILES,
    PROVIDER,
    Editor,
    render,
    save_config,
)

FLASH = CatalogModel("openrouter/deepseek/flash", 0.3, 1.2, 128000, True)
SONNET = CatalogModel("openrouter/anthropic/sonnet", 2.0, 10.0, 500000, True)

CONFIG = """
default_privacy = "medium"
[privacy.medium]
provider = "openrouter"
base_url = "https://openrouter.ai/api/v1"
api_key_env = "TEST_TUI_KEY"
max_parallel = 4
tiers = ["openrouter/deepseek/flash"]
reviewer = "openrouter/deepseek/flash"
request_options = { provider = { data_collection = "deny" } }
"""


def state(tmp_path: Path) -> SetupState:
    path = tmp_path / "conductor.toml"
    path.write_text(CONFIG)
    return SetupState.from_config(Config.load(path))


def editor(tmp_path: Path, fetcher: Callable[[str], list[CatalogModel]] | None = None) -> Editor:
    return Editor(
        state(tmp_path),
        catalog=fetcher or (lambda url: [SONNET, FLASH]),
        store=lambda name, value: None,
        path=str(tmp_path / "conductor.toml"),
    )


def type_text(view: Editor, text: str) -> None:
    for character in text:
        view.handle_key(character)


def test_the_profiles_screen_lists_profiles_and_marks_the_default(tmp_path: Path) -> None:
    lines = render(editor(tmp_path))
    assert lines[0].startswith("Conductor setup")
    assert lines[1] == "> medium  (1 tiers, default)"
    assert any(line.startswith("a add") for line in lines)


def test_a_creates_a_profile_after_choosing_a_provider_and_typing_a_name(tmp_path: Path) -> None:
    view = editor(tmp_path)
    view.handle_key("a")
    assert view.screen == PROVIDER
    assert "OpenRouter" in "\n".join(render(view))
    view.handle_key("down")
    view.handle_key("down")
    view.handle_key("enter")
    assert view.screen == NAME
    type_text(view, "cheap-eu")
    assert "cheap-eu" in render(view)[-2]
    assert view.handle_key("enter") is False
    assert view.screen == EDITOR
    assert [profile.name for profile in view.state.profiles] == ["medium", "cheap-eu"]
    assert view.state.draft().base_url == "https://ai-gateway.vercel.sh/v1"


def test_a_duplicate_profile_name_is_reported_and_nothing_is_added(tmp_path: Path) -> None:
    view = editor(tmp_path)
    view.handle_key("a")
    view.handle_key("enter")
    type_text(view, "medium")
    view.handle_key("enter")
    assert view.screen == NAME
    assert "already exists" in view.message
    assert len(view.state.profiles) == 1


def test_d_deletes_the_selected_profile_and_p_sets_the_default(tmp_path: Path) -> None:
    view = editor(tmp_path)
    view.handle_key("a")
    view.handle_key("enter")
    type_text(view, "second")
    view.handle_key("enter")
    view.handle_key("esc")
    assert view.screen == PROFILES
    view.handle_key("down")
    view.handle_key("p")
    assert view.state.default_privacy == "second"
    view.handle_key("d")
    assert [profile.name for profile in view.state.profiles] == ["medium"]


def test_escape_leaves_the_editor_without_saving_anything(tmp_path: Path) -> None:
    view = editor(tmp_path)
    view.handle_key("enter")
    view.handle_key("a")
    assert view.screen == CATALOG
    view.handle_key("esc")
    assert view.screen == EDITOR
    view.handle_key("esc")
    assert view.screen == PROFILES


def test_the_catalog_screen_filters_models_and_adds_the_chosen_one(tmp_path: Path) -> None:
    view = editor(tmp_path)
    view.handle_key("enter")
    view.handle_key("a")
    assert view.screen == CATALOG
    assert [model.id for model in view.models] == [FLASH.id, SONNET.id]
    type_text(view, "sonnet")
    assert [model.id for model in view.models] == [SONNET.id]
    view.handle_key("enter")
    assert view.screen == EDITOR
    assert view.state.draft().tiers == [FLASH.id, SONNET.id]


def test_the_catalog_reports_a_provider_it_cannot_reach(tmp_path: Path) -> None:
    def broken(url: str) -> list[CatalogModel]:
        raise CatalogError("https://example.invalid/v1/models could not be read")

    view = editor(tmp_path, broken)
    view.handle_key("enter")
    view.handle_key("a")
    assert view.screen == CATALOG
    assert "could not be read" in view.message
    assert view.models == []


def test_tiers_can_be_removed_and_moved_and_the_reviewer_cycles(tmp_path: Path) -> None:
    view = editor(tmp_path)
    view.handle_key("enter")
    view.handle_key("a")
    view.handle_key("down")
    view.handle_key("enter")
    assert view.state.draft().tiers == [FLASH.id, SONNET.id]
    view.handle_key("K")
    assert view.state.draft().tiers == [SONNET.id, FLASH.id]
    view.handle_key("r")
    assert view.state.draft().reviewer == "brain"
    view.handle_key("r")
    assert view.state.draft().reviewer == SONNET.id
    view.handle_key("d")
    assert view.state.draft().tiers == [FLASH.id]
    view.handle_key("m")
    assert view.state.draft().max_parallel == 5
    view.handle_key("M")
    view.handle_key("M")
    assert view.state.draft().max_parallel == 3


def test_a_key_is_typed_masked_and_stored(tmp_path: Path) -> None:
    stored: list[tuple[str, str]] = []

    def store(name: str, value: str) -> None:
        stored.append((name, value))

    view = Editor(
        state(tmp_path),
        catalog=lambda url: [],
        store=store,
        path=str(tmp_path / "conductor.toml"),
    )
    view.handle_key("enter")
    view.handle_key("k")
    assert view.screen == KEY
    type_text(view, "sk-secret")
    assert "sk-secret" not in "\n".join(render(view))
    view.handle_key("enter")
    assert view.screen == EDITOR
    assert stored == [("TEST_TUI_KEY", "sk-secret")]
    assert "key stored" in view.message


def test_saving_refuses_an_invalid_configuration(tmp_path: Path) -> None:
    view = editor(tmp_path)
    view.handle_key("a")
    view.handle_key("enter")
    type_text(view, "empty")
    view.handle_key("enter")
    view.handle_key("esc")
    assert view.handle_key("s") is False
    assert view.screen == PROFILES
    assert "profiles.empty: tiers must not be empty" in view.message


def test_saving_writes_the_config_and_keeps_a_backup(tmp_path: Path) -> None:
    view = editor(tmp_path)
    view.handle_key("enter")
    view.handle_key("r")
    view.handle_key("esc")
    assert view.handle_key("s") is True
    path = tmp_path / "conductor.toml"
    assert 'reviewer = "brain"' in path.read_text()
    assert (tmp_path / "conductor.toml.bak").read_text() == CONFIG
    assert Config.load(path).profiles["medium"].reviewer == "brain"


def test_save_config_without_an_existing_file_creates_it(tmp_path: Path) -> None:
    state(tmp_path)
    path = tmp_path / "nested" / "conductor.toml"
    path.parent.mkdir()
    save_config(path, SetupState.from_config(Config.load(tmp_path / "conductor.toml")))
    assert "default_privacy" in path.read_text()
    assert not path.with_suffix(".toml.bak").exists()


def test_quit_without_saving_leaves_the_file_alone(tmp_path: Path) -> None:
    view = editor(tmp_path)
    view.handle_key("enter")
    view.handle_key("r")
    view.handle_key("esc")
    assert view.handle_key("q") is True
    assert (tmp_path / "conductor.toml").read_text() == CONFIG


def test_a_model_without_the_provider_prefix_gets_it_when_added(tmp_path: Path) -> None:
    bare = [CatalogModel("deepseek/flash", 0.3, 1.2, 128000, True)]
    view = editor(tmp_path, lambda url: bare)
    view.handle_key("enter")
    view.handle_key("a")
    view.handle_key("enter")
    assert view.state.draft().tiers == ["openrouter/deepseek/flash"]
    view.handle_key("a")
    view.handle_key("enter")
    assert view.state.draft().tiers == ["openrouter/deepseek/flash"]
    assert "already a tier" in view.message


def test_t_types_a_tier_id_by_hand_for_providers_without_a_catalog(tmp_path: Path) -> None:
    view = editor(tmp_path, lambda url: [])
    view.handle_key("enter")
    view.handle_key("t")
    type_text(view, "scaleway/glm-5.3")
    view.handle_key("enter")
    assert view.screen == EDITOR
    assert view.state.draft().tiers == [FLASH.id, "openrouter/scaleway/glm-5.3"]
    view.handle_key("t")
    type_text(view, "scaleway/glm-5.3")
    view.handle_key("enter")
    assert "already a tier" in view.message
