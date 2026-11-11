from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from conductor.config import Config, Profile

PROFILE_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


class SetupError(ValueError):
    pass


@dataclass(frozen=True)
class KnownProvider:
    label: str
    provider: str
    base_url: str
    api_key_env: str


KNOWN_PROVIDERS: tuple[KnownProvider, ...] = (
    KnownProvider("OpenRouter", "openrouter", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    KnownProvider(
        "OpenRouter (EU)", "openrouter", "https://eu.openrouter.ai/api/v1", "OPENROUTER_API_KEY"
    ),
    KnownProvider(
        "Vercel AI Gateway", "vercel", "https://ai-gateway.vercel.sh/v1", "AI_GATEWAY_API_KEY"
    ),
    KnownProvider("Scaleway (EU)", "scaleway", "https://api.scaleway.ai/v1", "SCALEWAY_API_KEY"),
    KnownProvider("OpenCode Zen", "opencode", "https://opencode.ai/zen/v1", "OPENCODE_API_KEY"),
    KnownProvider("DeepSeek", "deepseek", "https://api.deepseek.com/v1", "DEEPSEEK_API_KEY"),
    KnownProvider("Other (fill in by hand)", "", "", "API_KEY"),
)


@dataclass
class ProfileDraft:
    name: str
    provider: str
    base_url: str
    api_key_env: str
    max_parallel: int = 4
    tiers: list[str] = field(default_factory=list)
    reviewer: str = ""
    request_options: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_profile(cls, profile: Profile) -> ProfileDraft:
        return cls(
            name=profile.name,
            provider=profile.provider,
            base_url=profile.base_url,
            api_key_env=profile.api_key_env,
            max_parallel=profile.max_parallel,
            tiers=list(profile.tiers),
            reviewer=profile.reviewer,
            request_options=dict(profile.request_options),
        )

    def to_profile(self) -> Profile:
        return Profile(
            name=self.name,
            provider=self.provider,
            base_url=self.base_url,
            api_key_env=self.api_key_env,
            tiers=tuple(self.tiers),
            reviewer=self.reviewer,
            max_parallel=self.max_parallel,
            request_options=dict(self.request_options),
        )


@dataclass
class SetupState:
    profiles: list[ProfileDraft]
    default_privacy: str
    selected: int = 0

    @classmethod
    def from_config(cls, config: Config) -> SetupState:
        profiles = [ProfileDraft.from_profile(profile) for profile in config.profiles.values()]
        return cls(profiles, config.default_privacy)

    def to_config(self) -> Config:
        return Config(
            self.default_privacy,
            {draft.name: draft.to_profile() for draft in self.profiles},
        )

    def selected_profile(self) -> ProfileDraft | None:
        return self.profiles[self.selected] if self.profiles else None

    def select(self, index: int) -> None:
        self.selected = max(0, min(index, len(self.profiles) - 1))

    def draft(self) -> ProfileDraft:
        profile = self.selected_profile()
        if profile is None:
            raise SetupError("no profile selected")
        return profile

    def add_profile(self, name: str, known: KnownProvider) -> ProfileDraft:
        if not PROFILE_NAME.fullmatch(name):
            raise SetupError("profile names must be lower-case letters, digits or '-'")
        if any(profile.name == name for profile in self.profiles):
            raise SetupError(f"profile '{name}' already exists")
        profile = ProfileDraft(name, known.provider, known.base_url, known.api_key_env)
        self.profiles.append(profile)
        self.selected = len(self.profiles) - 1
        return profile

    def remove_profile(self, name: str) -> None:
        for index, profile in enumerate(self.profiles):
            if profile.name == name:
                del self.profiles[index]
                self.select(self.selected)
                return
        raise SetupError(f"unknown profile '{name}'")

    def add_tier(self, model: str) -> ProfileDraft:
        profile = self.draft()
        if model in profile.tiers:
            raise SetupError(f"'{model}' is already a tier")
        profile.tiers.append(model)
        return profile

    def remove_tier(self, index: int) -> ProfileDraft:
        profile = self.draft()
        if not 0 <= index < len(profile.tiers):
            raise SetupError(f"no tier at index {index}")
        del profile.tiers[index]
        return profile

    def move_tier(self, index: int, offset: int) -> ProfileDraft:
        profile = self.draft()
        if not 0 <= index < len(profile.tiers):
            raise SetupError(f"no tier at index {index}")
        target = max(0, min(index + offset, len(profile.tiers) - 1))
        profile.tiers.insert(target, profile.tiers.pop(index))
        return profile

    def set_reviewer(self, model: str) -> ProfileDraft:
        profile = self.draft()
        if not model.strip():
            raise SetupError("reviewer must not be empty")
        profile.reviewer = model.strip()
        return profile

    def set_default_privacy(self, name: str) -> None:
        if not any(profile.name == name for profile in self.profiles):
            raise SetupError(f"unknown profile '{name}'")
        self.default_privacy = name

    def problems(self) -> list[str]:
        if not self.profiles:
            return ["at least one profile is required"]
        problems = []
        for profile in self.profiles:
            if not profile.tiers:
                problems.append(f"profiles.{profile.name}: tiers must not be empty")
            if not profile.reviewer.strip():
                problems.append(f"profiles.{profile.name}: reviewer must be set")
        if not any(profile.name == self.default_privacy for profile in self.profiles):
            problems.append(f"default_privacy references unknown profile '{self.default_privacy}'")
        return problems
