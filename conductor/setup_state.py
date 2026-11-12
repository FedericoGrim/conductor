from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from conductor.config import DEFAULT_TRANSIENT_ATTEMPTS, Config, Profile, Provider, provider_of
from conductor.defaults import DIFFICULTY_LEVELS, default_config

PROFILE_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")

EMPTY_SLOT = ""


class SetupError(ValueError):
    pass


@dataclass(frozen=True)
class KnownProvider:
    label: str
    name: str
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
)


@dataclass
class ProviderDraft:
    name: str
    base_url: str
    api_key_env: str
    request_options: dict[str, Any] = field(default_factory=dict)
    model_options: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_provider(cls, provider: Provider) -> ProviderDraft:
        return cls(
            provider.name,
            provider.base_url,
            provider.api_key_env,
            dict(provider.request_options),
            {model: dict(options) for model, options in provider.model_options.items()},
        )

    def to_provider(self) -> Provider:
        return Provider(
            self.name,
            self.base_url,
            self.api_key_env,
            dict(self.request_options),
            {model: dict(options) for model, options in self.model_options.items()},
        )


@dataclass
class ProfileDraft:
    name: str
    providers: dict[str, ProviderDraft] = field(default_factory=dict)
    tiers: list[str] = field(default_factory=lambda: [EMPTY_SLOT] * DIFFICULTY_LEVELS)
    reviewer: str = ""
    max_parallel: int = 4
    transient_attempts: int = DEFAULT_TRANSIENT_ATTEMPTS

    @classmethod
    def from_profile(cls, profile: Profile) -> ProfileDraft:
        tiers = list(profile.tiers)[:DIFFICULTY_LEVELS]
        tiers += [EMPTY_SLOT] * (DIFFICULTY_LEVELS - len(tiers))
        return cls(
            name=profile.name,
            providers={
                name: ProviderDraft.from_provider(provider)
                for name, provider in profile.providers.items()
            },
            tiers=tiers,
            reviewer=profile.reviewer,
            max_parallel=profile.max_parallel,
            transient_attempts=profile.transient_attempts,
        )

    def to_profile(self) -> Profile:
        return Profile(
            name=self.name,
            providers={name: provider.to_provider() for name, provider in self.providers.items()},
            tiers=tuple(tier for tier in self.tiers if tier != EMPTY_SLOT),
            reviewer=self.reviewer,
            max_parallel=self.max_parallel,
            transient_attempts=self.transient_attempts,
        )

    def filled(self) -> list[str]:
        return [tier for tier in self.tiers if tier != EMPTY_SLOT]


@dataclass
class SetupState:
    profiles: list[ProfileDraft]
    default_privacy: str
    selected: int = 0

    @classmethod
    def from_config(cls, config: Config) -> SetupState:
        return cls(
            [ProfileDraft.from_profile(profile) for profile in config.profiles.values()],
            config.default_privacy,
        )

    @classmethod
    def defaults(cls) -> SetupState:
        return cls.from_config(default_config())

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

    def add_profile(
        self, name: str, known: KnownProvider, provider_name: str | None = None
    ) -> ProfileDraft:
        if not PROFILE_NAME.fullmatch(name):
            raise SetupError("profile names must be lower-case letters, digits or '-'")
        if any(profile.name == name for profile in self.profiles):
            raise SetupError(f"profile '{name}' already exists")
        profile = ProfileDraft(name)
        profile.providers[provider_name or known.name] = ProviderDraft(
            provider_name or known.name, known.base_url, known.api_key_env
        )
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

    def add_provider(self, known: KnownProvider, name: str | None = None) -> ProviderDraft:
        profile = self.draft()
        provider_name = name or known.name
        if not PROFILE_NAME.fullmatch(provider_name):
            raise SetupError("provider names must be lower-case letters, digits or '-'")
        if provider_name in profile.providers:
            raise SetupError(f"provider '{provider_name}' already exists in {profile.name}")
        provider = ProviderDraft(provider_name, known.base_url, known.api_key_env)
        profile.providers[provider_name] = provider
        return provider

    def remove_provider(self, name: str) -> ProfileDraft:
        profile = self.draft()
        if name not in profile.providers:
            raise SetupError(f"unknown provider '{name}'")
        del profile.providers[name]
        profile.tiers = [
            EMPTY_SLOT if provider_of(tier) == name else tier for tier in profile.tiers
        ]
        if profile.reviewer != "brain" and provider_of(profile.reviewer) == name:
            profile.reviewer = ""
        return profile

    def provider(self, name: str) -> ProviderDraft:
        profile = self.draft()
        if name not in profile.providers:
            raise SetupError(f"unknown provider '{name}'")
        return profile.providers[name]

    def set_base_url(self, name: str, base_url: str) -> ProviderDraft:
        provider = self.provider(name)
        if not base_url.startswith("https://"):
            raise SetupError("base_url must start with https://")
        provider.base_url = base_url
        return provider

    def set_api_key_env(self, name: str, api_key_env: str) -> ProviderDraft:
        provider = self.provider(name)
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", api_key_env):
            raise SetupError("api_key_env must be an upper-case variable name")
        provider.api_key_env = api_key_env
        return provider

    def set_tier(self, level: int, model: str) -> ProfileDraft:
        profile = self.draft()
        if not 1 <= level <= DIFFICULTY_LEVELS:
            raise SetupError(f"difficulty must be between 1 and {DIFFICULTY_LEVELS}")
        if not model.strip():
            raise SetupError("model must not be empty")
        if provider_of(model) not in profile.providers:
            raise SetupError(f"add provider '{provider_of(model) or '?'}' first")
        if model in profile.tiers:
            raise SetupError(f"'{model}' is already a tier")
        profile.tiers[level - 1] = model
        return profile

    def clear_tier(self, level: int) -> ProfileDraft:
        profile = self.draft()
        if not 1 <= level <= DIFFICULTY_LEVELS:
            raise SetupError(f"difficulty must be between 1 and {DIFFICULTY_LEVELS}")
        profile.tiers[level - 1] = EMPTY_SLOT
        return profile

    def set_reviewer(self, model: str) -> ProfileDraft:
        profile = self.draft()
        if not model.strip():
            raise SetupError("reviewer must not be empty")
        if model != "brain" and provider_of(model) not in profile.providers:
            raise SetupError(f"reviewer '{model}' has no provider in {profile.name}")
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
            if not profile.providers:
                problems.append(f"profiles.{profile.name}: add at least one provider")
            for level, tier in enumerate(profile.tiers, start=1):
                if tier == EMPTY_SLOT:
                    problems.append(f"profiles.{profile.name}: difficulty {level} has no model")
            if not profile.reviewer.strip():
                problems.append(f"profiles.{profile.name}: reviewer must be set")
            elif profile.reviewer != "brain" and provider_of(profile.reviewer) not in (
                profile.providers
            ):
                problems.append(
                    f"profiles.{profile.name}: reviewer '{profile.reviewer}' has no provider"
                )
        if not any(profile.name == self.default_privacy for profile in self.profiles):
            problems.append(f"default_privacy references unknown profile '{self.default_privacy}'")
        return problems
