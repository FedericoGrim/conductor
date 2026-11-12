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
from conductor.defaults import DIFFICULTY_LEVELS
from conductor.setup_state import (
    KNOWN_PROVIDERS,
    KnownProvider,
    SetupError,
    SetupState,
)

PROFILES = "profiles"
PROVIDER = "provider"
NAME = "name"
EDITOR = "editor"
PROVIDERS = "providers"
PROVIDERADD = "provideradd"
BASED = "based"
KEYENV = "keyenv"
CATALOG = "catalog"
MODEL = "model"
KEYPROVIDER = "keyprovider"
KEY = "key"

BRAIN = "brain"
LEVEL_MODEL = "level"
FALLBACK = "fallback"
REVIEWER_FALLBACK = "reviewer_fallback"

HINTS = {
    PROFILES: "a add  d delete  p default  enter edit  s save  q quit",
    PROVIDER: "enter choose  esc back",
    NAME: "enter confirm  esc back",
    EDITOR: (
        "a model  t type  d clear  f/F fallback  x drop fallback  esc back\n"
        "P providers  k key  r reviewer  v/V reviewer fallback  m/M parallel"
    ),
    PROVIDERS: "a add  d delete  b base_url  e key variable  esc back",
    PROVIDERADD: "enter add  esc back",
    BASED: "enter confirm  esc back",
    KEYENV: "enter confirm  esc back",
    CATALOG: "type to search  enter set  esc back",
    MODEL: "enter confirm  esc back",
    KEYPROVIDER: "enter choose  esc back",
    KEY: "enter store key  esc cancel",
}

TITLES = {
    PROFILES: "Conductor setup — privacy profiles",
    PROVIDER: "Conductor setup — provider of the new profile",
    NAME: "Conductor setup — name of the new profile",
    EDITOR: "Conductor setup — difficulty levels",
    PROVIDERS: "Conductor setup — providers of this profile",
    PROVIDERADD: "Conductor setup — add a provider",
    BASED: "Conductor setup — base_url",
    KEYENV: "Conductor setup — variable holding the key",
    CATALOG: "Conductor setup — models of this profile",
    MODEL: "Conductor setup — model id, typed by hand",
    KEYPROVIDER: "Conductor setup — provider of the key",
    KEY: "Conductor setup — API key",
}

Store = Callable[[str, str], None]
Catalog = Callable[[str], list[CatalogModel]]


@dataclass
class Editor:
    state: SetupState
    path: str
    catalog: Catalog = fetch_models
    store: Store = credentials.store_key
    screen: str = PROFILES
    slot_cursor: int = 0
    profile_cursor: int = 0
    provider_cursor: int = 0
    model_cursor: int = 0
    text: str = ""
    message: str = ""
    models: list[CatalogModel] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    target: str = ""
    choosing: str = LEVEL_MODEL
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
            self.slot_cursor = 0
        elif key == "a":
            self.screen = PROVIDER
            self.profile_cursor = 0
        elif key == "d" and self.state.selected_profile() is not None:
            self.apply(lambda: self.state.remove_profile(self.state.draft().name))
        elif key == "p" and self.state.selected_profile() is not None:
            self.apply(lambda: self.state.set_default_privacy(self.state.draft().name))
        elif key == "s":
            return self.save()
        elif key == "q":
            return True
        return False

    def apply(self, action: Callable[[], Any]) -> None:
        try:
            action()
        except SetupError as error:
            self.message = str(error)

    def provider_key(self, key: str) -> bool:
        if key in ("down", "j"):
            self.profile_cursor = min(self.profile_cursor + 1, len(KNOWN_PROVIDERS) - 1)
        elif key in ("up", "k"):
            self.profile_cursor = max(self.profile_cursor - 1, 0)
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

    def create_profile(self) -> None:
        known: KnownProvider = KNOWN_PROVIDERS[self.profile_cursor]
        try:
            self.state.add_profile(self.text, known)
        except SetupError as error:
            self.message = str(error)
            return
        self.screen = EDITOR
        self.slot_cursor = 0

    def name_key(self, key: str) -> bool:
        if key == "esc":
            self.screen = PROVIDER
        elif key == "enter":
            self.create_profile()
        else:
            self.typed(key)
        return False

    def editor_key(self, key: str) -> bool:
        profile = self.state.draft()
        if key == "esc":
            self.screen = PROFILES
        elif key in ("down", "J"):
            self.slot_cursor = min(self.slot_cursor + 1, DIFFICULTY_LEVELS - 1)
        elif key in ("up", "K"):
            self.slot_cursor = max(self.slot_cursor - 1, 0)
        elif key in ("a", "f", "v"):
            self.choosing = {"a": LEVEL_MODEL, "f": FALLBACK, "v": REVIEWER_FALLBACK}[key]
            self.open_catalog()
        elif key in ("t", "F"):
            self.choosing = LEVEL_MODEL if key == "t" else FALLBACK
            self.screen = MODEL
            self.text = ""
        elif key == "d":
            self.apply(lambda: self.state.clear_tier(self.level))
        elif key == "x":
            self.apply(lambda: self.state.remove_fallback(self.level))
        elif key == "V":
            self.state.clear_reviewer_fallbacks()
        elif key == "P":
            self.screen = PROVIDERS
            self.provider_cursor = 0
        elif key == "k":
            self.ask_for_key()
        elif key == "r":
            self.cycle_reviewer(profile)
        elif key == "m":
            profile.max_parallel += 1
        elif key == "M":
            profile.max_parallel = max(1, profile.max_parallel - 1)
        return False

    @property
    def level(self) -> int:
        return self.slot_cursor + 1

    def cycle_reviewer(self, profile: Any) -> None:
        choices = [*profile.filled(), BRAIN]
        try:
            index = choices.index(profile.reviewer)
        except ValueError:
            index = -1
        self.apply(lambda: self.state.set_reviewer(choices[(index + 1) % len(choices)]))

    def choose(self, model: str) -> None:
        actions = {
            LEVEL_MODEL: lambda: self.state.set_tier(self.level, model),
            FALLBACK: lambda: self.state.add_fallback(self.level, model),
            REVIEWER_FALLBACK: lambda: self.state.add_reviewer_fallback(model),
        }
        self.apply(actions[self.choosing])
        if not self.message:
            self.screen = EDITOR

    def open_catalog(self) -> None:
        self.screen = CATALOG
        self.query = ""
        self.model_cursor = 0
        self.load_catalog()

    def load_catalog(self) -> None:
        profile = self.state.draft()
        self.models = []
        self.notes = []
        broken: list[str] = []
        for name, provider in profile.providers.items():
            if not provider.base_url:
                continue
            try:
                fetched = self.catalog(provider.base_url)
            except CatalogError as error:
                broken.append(f"{name}: {error}")
                continue
            self.models.extend(
                CatalogModel(
                    f"{name}/{model.id}",
                    model.prompt_price,
                    model.completion_price,
                    model.context,
                    model.supports_tools,
                )
                for model in fetched
            )
        if broken:
            self.message = "; ".join(broken)
        self.filter_models()

    def filter_models(self) -> None:
        self.models = select_models(self.models, search=self.query)
        self.model_cursor = 0
        self.notes = [model.id for model in self.models[3:4]]

    def catalog_key(self, key: str) -> bool:
        if key == "esc":
            self.screen = EDITOR
        elif key in ("down", "j"):
            self.model_cursor = min(self.model_cursor + 1, max(len(self.models) - 1, 0))
        elif key in ("up", "k"):
            self.model_cursor = max(self.model_cursor - 1, 0)
        elif key == "enter" and self.models:
            self.choose(self.models[self.model_cursor].id)
        elif key == "backspace":
            self.query = self.query[:-1]
            self.filter_models()
        elif len(key) == 1 and key.isprintable():
            self.query += key
            self.filter_models()
        return False

    def model_key(self, key: str) -> bool:
        if key == "esc":
            self.screen = EDITOR
        elif key == "enter":
            self.choose(self.text.strip())
        else:
            self.typed(key)
        return False

    def providers_key(self, key: str) -> bool:
        profile = self.state.draft()
        names = list(profile.providers)
        if key == "esc":
            self.screen = EDITOR
        elif key in ("down", "j"):
            self.provider_cursor = min(self.provider_cursor + 1, max(len(names) - 1, 0))
        elif key in ("up", "k"):
            self.provider_cursor = max(self.provider_cursor - 1, 0)
        elif key == "a":
            self.screen = PROVIDERADD
            self.profile_cursor = 0
        elif key in ("d", "b", "e") and names:
            name = names[self.provider_cursor]
            if key == "d":
                self.apply(lambda: self.state.remove_provider(name))
            else:
                provider = profile.providers[name]
                if not provider.base_url:
                    self.message = f"{name} is managed by {provider.harness}: no base_url or key"
                else:
                    self.target = name
                    self.text = ""
                    self.screen = BASED if key == "b" else KEYENV
        return False

    def provideradd_key(self, key: str) -> bool:
        if key == "esc":
            self.screen = PROVIDERS
        elif key in ("down", "j"):
            self.profile_cursor = min(self.profile_cursor + 1, len(KNOWN_PROVIDERS) - 1)
        elif key in ("up", "k"):
            self.profile_cursor = max(self.profile_cursor - 1, 0)
        elif key == "enter":
            known = KNOWN_PROVIDERS[self.profile_cursor]
            self.apply(lambda: self.state.add_provider(known))
            if not self.message:
                self.screen = PROVIDERS
                self.provider_cursor = len(self.state.draft().providers) - 1
        return False

    def based_key(self, key: str) -> bool:
        if key == "esc":
            self.screen = PROVIDERS
        elif key == "enter":
            self.apply(lambda: self.state.set_base_url(self.target, self.text.strip()))
            if not self.message:
                self.screen = PROVIDERS
        else:
            self.typed(key)
        return False

    def keyenv_key(self, key: str) -> bool:
        if key == "esc":
            self.screen = PROVIDERS
        elif key == "enter":
            self.apply(lambda: self.state.set_api_key_env(self.target, self.text.strip()))
            if not self.message:
                self.screen = PROVIDERS
        else:
            self.typed(key)
        return False

    def ask_for_key(self) -> None:
        names = list(self.state.draft().providers)
        if not names:
            self.message = "add a provider first"
        elif len(names) == 1:
            self.open_key(names[0])
        else:
            self.screen = KEYPROVIDER
            self.provider_cursor = 0

    def open_key(self, provider: str) -> None:
        self.target = provider
        self.text = ""
        self.screen = KEY

    def keyprovider_key(self, key: str) -> bool:
        names = list(self.state.draft().providers)
        if key == "esc":
            self.screen = EDITOR
        elif key in ("down", "j"):
            self.provider_cursor = min(self.provider_cursor + 1, max(len(names) - 1, 0))
        elif key in ("up", "k"):
            self.provider_cursor = max(self.provider_cursor - 1, 0)
        elif key == "enter" and names:
            self.open_key(names[self.provider_cursor])
        return False

    def key_key(self, key: str) -> bool:
        if key == "esc":
            self.screen = EDITOR
        elif key == "enter":
            provider = self.state.provider(self.target)
            self.store(provider.api_key_env, self.text)
            self.screen = EDITOR
            self.message = f"key of {provider.name} stored in {credentials.credentials_path()}"
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
        rows.append(
            f"{marker} {profile.name}  ({len(profile.filled())}/{DIFFICULTY_LEVELS}{default})"
        )
    return rows


def with_fallbacks(model: str, fallbacks: list[str]) -> str:
    return f"{model} → {', '.join(fallbacks)}" if fallbacks else model


def difficulty_rows(view: Editor) -> list[str]:
    profile = view.state.draft()
    rows = []
    levels = zip(profile.tiers, profile.fallbacks, strict=True)
    for level, (model, fallbacks) in enumerate(levels, start=1):
        marker = ">" if level == view.level else " "
        rows.append(f"{marker} {level}. {with_fallbacks(model or '(no model yet)', fallbacks)}")
    return rows


def render(view: Editor) -> list[str]:
    rows = [TITLES[view.screen]]
    if view.screen == PROFILES:
        rows.extend(profile_rows(view.state))
    elif view.screen in (PROVIDER, PROVIDERADD):
        for index, known in enumerate(KNOWN_PROVIDERS):
            marker = ">" if index == view.profile_cursor else " "
            rows.append(f"{marker} {known.label}  {known.base_url}")
    elif view.screen == NAME:
        rows.append(f"new profile name: {view.text}")
    elif view.screen == EDITOR and view.state.selected_profile() is not None:
        profile = view.state.draft()
        reviewer = profile.reviewer or "(not set)"
        rows.extend(
            [
                f"profile   {profile.name}"
                + ("  (default)" if profile.name == view.state.default_privacy else ""),
                f"providers {', '.join(profile.providers) or '(none)'}",
                f"parallel  {profile.max_parallel}",
                "reviewer  " + with_fallbacks(reviewer, profile.reviewer_fallbacks),
                "",
                "difficulty, easiest first:",
                *difficulty_rows(view),
            ]
        )
    elif view.screen == PROVIDERS and view.state.selected_profile() is not None:
        names = list(view.state.draft().providers)
        for index, name in enumerate(names):
            marker = ">" if index == view.provider_cursor else " "
            provider = view.state.draft().providers[name]
            if provider.base_url:
                rows.append(f"{marker} {name:12} {provider.base_url}")
                rows.append(f"  {'':12} {provider.api_key_env}")
            else:
                rows.append(f"{marker} {name:12} (managed by {provider.harness})")
        if not names:
            rows.append("(no providers yet: press a)")
    elif view.screen in (BASED, KEYENV):
        current = view.state.draft().providers.get(view.target)
        label = "base_url" if view.screen == BASED else "api_key_env"
        current_value = "" if current is None else getattr(current, label)
        rows.append(f"{view.target}: {label} = {view.text or current_value}")
    elif view.screen == CATALOG:
        rows.append(f"search: {view.query}")
        if not view.models:
            rows.append("  (no model matches, or the providers could not be read)")
        for index, model in enumerate(view.models):
            marker = ">" if index == view.model_cursor else " "
            rows.append(
                f"{marker} {model.id:52} {model.prompt_price:8.4f} "
                f"{model.completion_price:8.4f} {model.context:8}"
            )
    elif view.screen == MODEL:
        rows.append(f"model id for difficulty {view.level}: {view.text}")
    elif view.screen == KEYPROVIDER and view.state.selected_profile() is not None:
        for index, name in enumerate(view.state.draft().providers):
            marker = ">" if index == view.provider_cursor else " "
            rows.append(f"{marker} {name}")
    elif view.screen == KEY:
        rows.append(f"{view.target}: {'*' * len(view.text)}")
    if view.message:
        rows.extend(["", view.message])
    rows.extend(HINTS[view.screen].splitlines())
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
    state = SetupState.from_config(Config.load(path)) if path.exists() else SetupState.defaults()
    view = Editor(state, path=str(path))
    curses.wrapper(loop, view)
    return 0 if view.saved else 1
