from __future__ import annotations

import contextlib
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from conductor import credentials
from conductor.catalog import CatalogError, CatalogModel, fetch_models, select_models
from conductor.config import Config
from conductor.setup_state import KNOWN_PROVIDERS, KnownProvider, SetupError, SetupState

PROFILES = "profiles"
PROVIDER = "provider"
NAME = "name"
EDITOR = "editor"
CATALOG = "catalog"
KEY = "key"
MODEL = "model"

REVIEWERS = "brain"

HINTS = {
    PROFILES: "a add  d delete  p default  enter edit  s save  q quit",
    PROVIDER: "enter choose  esc back",
    NAME: "enter confirm  esc back",
    EDITOR: "a add tier  t type id  d remove  J/K move  r reviewer  m/M parallel  k key  esc back",
    CATALOG: "type to search  enter add tier  esc back",
    KEY: "enter save key  esc cancel",
    MODEL: "enter confirm  esc back",
}

TITLES = {
    PROFILES: "Conductor setup — privacy profiles",
    PROVIDER: "Conductor setup — choose a provider",
    NAME: "Conductor setup — name of the new profile",
    EDITOR: "Conductor setup — edit a profile",
    CATALOG: "Conductor setup — models of this provider",
    KEY: "Conductor setup — API key",
    MODEL: "Conductor setup — model id, typed by hand",
}

Store = Callable[[str, str], None]
Catalog = Callable[[str], list[CatalogModel]]


@dataclass
class Editor:
    state: SetupState
    catalog: Catalog = fetch_models
    store: Store = credentials.store_key
    screen: str = PROFILES
    provider_cursor: int = 0
    tier_cursor: int = 0
    tier_offset: int = 0
    model_cursor: int = 0
    text: str = ""
    message: str = ""
    models: list[CatalogModel] = field(default_factory=list)
    saved: bool = False

    def handle_key(self, key: str) -> bool:
        self.message = ""
        handler = getattr(self, f"{self.screen}_key")
        return bool(handler(key))

    def profiles_key(self, key: str) -> bool:
        if key in ("down", "j"):
            self.state.select(self.state.selected + 1)
        elif key in ("up", "k"):
            self.state.select(self.state.selected - 1)
        elif key == "enter" and self.state.selected_profile() is not None:
            self.screen = EDITOR
            self.tier_cursor = 0
            self.tier_offset = 0
        elif key == "a":
            self.screen = PROVIDER
            self.provider_cursor = 0
        elif key == "d" and self.state.selected_profile() is not None:
            self.state.remove_profile(self.state.draft().name)
        elif key == "p" and self.state.selected_profile() is not None:
            self.state.set_default_privacy(self.state.draft().name)
        elif key == "s":
            return self.save()
        elif key == "q":
            return True
        return False

    def provider_key(self, key: str) -> bool:
        if key in ("down", "j"):
            self.provider_cursor = min(self.provider_cursor + 1, len(KNOWN_PROVIDERS) - 1)
        elif key in ("up", "k"):
            self.provider_cursor = max(self.provider_cursor - 1, 0)
        elif key == "enter":
            self.screen = NAME
            self.text = ""
        elif key == "esc":
            self.screen = PROFILES
        return False

    def typed(self, key: str) -> None:
        if key == "backspace":
            self.text = self.text[:-1]
        elif len(key) == 1 and key.isprintable():
            self.text += key

    def name_key(self, key: str) -> bool:
        if key == "esc":
            self.screen = PROVIDER
        elif key == "enter":
            self.create_profile()
        else:
            self.typed(key)
        return False

    def create_profile(self) -> None:
        known: KnownProvider = KNOWN_PROVIDERS[self.provider_cursor]
        try:
            self.state.add_profile(self.text, known)
        except SetupError as error:
            self.message = str(error)
            return
        self.screen = EDITOR
        self.tier_cursor = 0
        self.tier_offset = 0

    def editor_key(self, key: str) -> bool:
        profile = self.state.draft()
        if key == "esc":
            self.screen = PROFILES
        elif key == "a":
            self.open_catalog()
        elif key == "d" and profile.tiers:
            self.state.remove_tier(self.tier_cursor)
            self.tier_cursor = min(self.tier_cursor, len(profile.tiers) - 1)
            self.tier_offset = min(self.tier_offset, max(len(profile.tiers) - 1, 0))
        elif key in ("J", "down") and profile.tiers:
            self.state.move_tier(self.tier_cursor, 1)
            self.tier_cursor = min(self.tier_cursor + 1, len(profile.tiers) - 1)
        elif key in ("K", "up") and profile.tiers:
            self.state.move_tier(self.tier_cursor, -1)
            self.tier_cursor = max(self.tier_cursor - 1, 0)
        elif key == "r":
            self.cycle_reviewer(profile)
        elif key == "m":
            profile.max_parallel += 1
        elif key == "M":
            profile.max_parallel = max(1, profile.max_parallel - 1)
        elif key == "k":
            self.screen = KEY
            self.text = ""
        elif key == "t":
            self.screen = MODEL
            self.text = ""
        return False

    def cycle_reviewer(self, profile: Any) -> None:
        choices = [*profile.tiers, REVIEWERS]
        try:
            index = choices.index(profile.reviewer)
        except ValueError:
            index = -1
        profile.reviewer = choices[(index + 1) % len(choices)]

    def open_catalog(self) -> None:
        profile = self.state.draft()
        self.screen = CATALOG
        self.query = ""
        self.model_cursor = 0
        self.models = []
        try:
            self.models = select_models(self.catalog(profile.base_url))
        except CatalogError as error:
            self.message = str(error)

    def catalog_key(self, key: str) -> bool:
        if key == "esc":
            self.screen = EDITOR
        elif key in ("down", "j"):
            self.model_cursor = min(self.model_cursor + 1, max(len(self.models) - 1, 0))
        elif key in ("up", "k"):
            self.model_cursor = max(self.model_cursor - 1, 0)
        elif key == "enter" and self.models:
            self.add_selected_model()
        elif key == "backspace":
            self.query = self.query[:-1]
            self.filter_models()
        elif len(key) == 1 and key.isprintable():
            self.query += key
            self.filter_models()
        return False

    def filter_models(self) -> None:
        profile = self.state.draft()
        try:
            self.models = select_models(self.catalog(profile.base_url), search=self.query)
        except CatalogError as error:
            self.models = []
            self.message = str(error)
        self.model_cursor = 0

    def add_model(self, model: str) -> None:
        provider = self.state.draft().provider
        if provider and not model.startswith(f"{provider}/"):
            model = f"{provider}/{model}"
        try:
            profile = self.state.add_tier(model)
        except SetupError as error:
            self.message = str(error)
            return
        self.screen = EDITOR
        self.tier_cursor = len(profile.tiers) - 1
        self.tier_offset = max(len(profile.tiers) - 1, 0)
        self.message = f"added {model}"

    def add_selected_model(self) -> None:
        self.add_model(self.models[self.model_cursor].id)

    def model_key(self, key: str) -> bool:
        if key == "esc":
            self.screen = EDITOR
        elif key == "enter":
            self.add_model(self.text.strip())
        else:
            self.typed(key)
        return False

    def key_key(self, key: str) -> bool:
        if key == "esc":
            self.screen = EDITOR
        elif key == "enter":
            name = self.state.draft().api_key_env
            self.store(name, self.text)
            self.screen = EDITOR
            self.message = f"key stored in {credentials.credentials_path()}"
        else:
            self.typed(key)
        return False

    def save(self) -> bool:
        problems = self.state.problems()
        if problems:
            self.message = "cannot save: " + "; ".join(problems)
            return False
        save_config(Path(self.path), self.state)
        self.saved = True
        self.message = "saved"
        return True

    path: str = ""

    def key_status(self, profile: Any) -> str:
        return "stored" if credentials.api_key(profile.api_key_env) else "missing"


def save_config(path: Path, state: SetupState) -> Path | None:
    backup = None
    if path.exists():
        backup = path.with_name(path.name + ".bak")
        shutil.copy2(path, backup)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(state.to_config().dump())
    return backup


def profile_rows(state: SetupState) -> list[str]:
    if not state.profiles:
        return ["(no profiles yet: press a to add one)"]
    rows = []
    for index, profile in enumerate(state.profiles):
        marker = ">" if index == state.selected else " "
        default = ", default" if profile.name == state.default_privacy else ""
        count = len(profile.tiers)
        rows.append(f"{marker} {profile.name}  ({count} tiers{default})")
    return rows


def render(view: Editor) -> list[str]:
    rows = [TITLES.get(view.screen, "Conductor setup")]
    if view.screen == PROFILES:
        rows.extend(profile_rows(view.state))
    elif view.screen == PROVIDER:
        for index, known in enumerate(KNOWN_PROVIDERS):
            marker = ">" if index == view.provider_cursor else " "
            rows.append(f"{marker} {known.label}  {known.base_url or 'manual'}")
    elif view.screen == NAME:
        rows.append(f"new profile name: {view.text}")
    elif view.screen == EDITOR and view.state.selected_profile() is not None:
        profile = view.state.draft()
        rows.extend(
            [
                f"profile   {profile.name}"
                + ("  (default)" if profile.name == view.state.default_privacy else ""),
                f"provider  {profile.provider or '(not set yet)'}  {profile.base_url}",
                f"key       {profile.api_key_env}: {view.key_status(profile)}",
                f"parallel  {profile.max_parallel}",
                f"reviewer  {profile.reviewer or '(not set)'}",
                "",
                "tiers, cheapest first:",
            ]
        )
        for index, tier in enumerate(profile.tiers):
            marker = ">" if index == view.tier_cursor else " "
            rows.append(f"{marker} {index + 1}. {tier}")
        if not profile.tiers:
            rows.append("  (no tiers yet: press a)")
    elif view.screen == CATALOG:
        rows.append(f"search: {view.query}")
        if not view.models:
            rows.append("  (no model matches, or the provider could not be read)")
        for index, model in enumerate(view.models):
            marker = ">" if index == view.model_cursor else " "
            rows.append(
                f"{marker} {model.id:52} {model.prompt_price:8.4f} {model.completion_price:8.4f}"
                f" {model.context:8}"
            )
    elif view.screen == MODEL:
        rows.append(f"model id: {view.text}")
    elif view.screen == KEY:
        rows.append(f"{view.state.draft().api_key_env}: {'*' * len(view.text)}")
    if view.message:
        rows.extend(["", view.message])
    rows.append(HINTS[view.screen])
    return rows


def translate(key: int) -> str | None:
    import curses

    special = {
        curses.KEY_UP: "up",
        curses.KEY_DOWN: "down",
        curses.KEY_BACKSPACE: "backspace",
        8: "backspace",
        127: "backspace",
        10: "enter",
        13: "enter",
        27: "esc",
    }
    if key in special:
        return special[key]
    if 32 <= key < 127:
        return chr(key)
    return None


def draw(screen: Any, view: Editor) -> None:
    import curses

    height, width = screen.getmaxyx()
    screen.erase()
    for row, line in enumerate(render(view)[: height - 1]):
        with contextlib.suppress(curses.error):
            screen.addstr(row, 0, line[: width - 1])
    screen.refresh()


def loop(screen: Any, view: Editor) -> None:
    import curses

    curses.curs_set(0)
    screen.keypad(True)
    while True:
        draw(screen, view)
        key = screen.getch()
        if key == curses.KEY_RESIZE:
            continue
        translated = translate(key)
        if translated is not None and view.handle_key(translated):
            return


def run(path: Path) -> int:
    import curses
    import sys

    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("error: `conductor setup` needs an interactive terminal")
        return 2
    if path.exists():
        view = Editor(SetupState.from_config(Config.load(path)), path=str(path))
    else:
        view = Editor(SetupState([], "medium"), path=str(path))
    curses.wrapper(loop, view)
    return 0 if view.saved else 1
