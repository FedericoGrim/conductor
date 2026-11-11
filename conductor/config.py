from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Profile:
    name: str
    provider: str
    base_url: str
    api_key_env: str
    tiers: tuple[str, ...]
    reviewer: str
    max_parallel: int = 4
    request_options: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> Profile:
        tiers = data.get("tiers")
        if not isinstance(tiers, list) or not tiers:
            raise ConfigError(f"privacy.{name}: tiers must be a non-empty list")
        try:
            return cls(
                name=name,
                provider=str(data["provider"]),
                base_url=str(data["base_url"]),
                api_key_env=str(data["api_key_env"]),
                tiers=tuple(str(t) for t in tiers),
                reviewer=str(data["reviewer"]),
                max_parallel=int(data.get("max_parallel", 4)),
                request_options=dict(data.get("request_options", {})),
            )
        except KeyError as error:
            raise ConfigError(f"privacy.{name}: missing key {error}") from error

    def model_for_tier(self, tier: int) -> str | None:
        return self.tiers[tier] if 0 <= tier < len(self.tiers) else None


@dataclass(frozen=True)
class Config:
    default_privacy: str
    profiles: dict[str, Profile]

    @classmethod
    def load(cls, path: Path) -> Config:
        data = tomllib.loads(path.read_text())
        profiles = {
            name: Profile.from_dict(name, body) for name, body in data.get("privacy", {}).items()
        }
        if not profiles:
            raise ConfigError("no [privacy.<level>] profiles defined")
        return cls(default_privacy=str(data.get("default_privacy", "medium")), profiles=profiles)

    def dump(self) -> str:
        raise NotImplementedError

    def profile(self, name: str | None) -> Profile:
        chosen = name or self.default_privacy
        if chosen not in self.profiles:
            raise ConfigError(f"unknown privacy level '{chosen}'")
        return self.profiles[chosen]
