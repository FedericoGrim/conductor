from __future__ import annotations

import json
import re
import tomllib
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")
DEFAULT_TRANSIENT_ATTEMPTS = 3
DUMP_HEADER = "# Written by `conductor setup`. Comments added by hand are lost on the next save."


class ConfigError(ValueError):
    pass


def toml_key(key: str) -> str:
    return key if BARE_KEY.fullmatch(key) else json.dumps(key)


def toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return repr(value)
    if isinstance(value, dict):
        items = ", ".join(f"{toml_key(str(k))} = {toml_value(v)}" for k, v in value.items())
        return f"{{ {items} }}" if items else "{}"
    if isinstance(value, list | tuple):
        return "[" + ", ".join(toml_value(item) for item in value) + "]"
    return json.dumps(str(value))


def merge_options(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = merge_options(current, value)
        else:
            merged[key] = value
    return merged


def provider_of(model: str) -> str:
    return model.split("/", 1)[0] if "/" in model else ""


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    api_key_env: str
    request_options: dict[str, Any] = field(default_factory=dict)
    model_options: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def is_https(self) -> bool:
        return urllib.parse.urlsplit(self.base_url).scheme == "https"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> Provider:
        try:
            return cls(
                name=name,
                base_url=str(data["base_url"]),
                api_key_env=str(data["api_key_env"]),
                request_options=dict(data.get("request_options", {})),
                model_options={
                    str(model): dict(body.get("request_options", {}))
                    for model, body in data.get("models", {}).items()
                },
            )
        except KeyError as error:
            raise ConfigError(f"privacy.*.providers.{name}: missing key {error}") from error

    def dump(self, prefix: str) -> list[str]:
        lines = [
            f"base_url = {toml_value(self.base_url)}",
            f"api_key_env = {toml_value(self.api_key_env)}",
        ]
        if self.request_options:
            lines.append(f"request_options = {toml_value(self.request_options)}")
        for model, options in self.model_options.items():
            lines.extend(
                [
                    "",
                    f"[{prefix}.models.{toml_key(model)}]",
                    f"request_options = {toml_value(options)}",
                ]
            )
        return lines


@dataclass(frozen=True)
class Profile:
    name: str
    providers: dict[str, Provider]
    tiers: tuple[str, ...]
    reviewer: str
    max_parallel: int = 4
    transient_attempts: int = DEFAULT_TRANSIENT_ATTEMPTS

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> Profile:
        try:
            providers = cls.parse_providers(name, data)
        except KeyError as error:
            raise ConfigError(f"privacy.{name}: missing key {error}") from error
        tiers = data.get("tiers")
        if not isinstance(tiers, list) or not tiers:
            raise ConfigError(f"privacy.{name}: tiers must be a non-empty list")
        try:
            profile = cls(
                name=name,
                providers=providers,
                tiers=tuple(str(t) for t in tiers),
                reviewer=str(data["reviewer"]),
                max_parallel=int(data.get("max_parallel", 4)),
                transient_attempts=cls.parse_transient_attempts(name, data),
            )
        except KeyError as error:
            raise ConfigError(f"privacy.{name}: missing key {error}") from error
        profile.validate()
        return profile

    @staticmethod
    def parse_transient_attempts(name: str, data: dict[str, Any]) -> int:
        retry = data.get("retry", {})
        if not isinstance(retry, dict):
            raise ConfigError(f"privacy.{name}: retry must be a table")
        attempts = retry.get("transient_attempts", DEFAULT_TRANSIENT_ATTEMPTS)
        if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts < 0:
            raise ConfigError(f"privacy.{name}: retry.transient_attempts must be a count >= 0")
        return attempts

    @staticmethod
    def parse_providers(name: str, data: dict[str, Any]) -> dict[str, Provider]:
        declared = data.get("providers")
        if declared is None:
            return {
                str(data["provider"]): Provider(
                    name=str(data["provider"]),
                    base_url=str(data["base_url"]),
                    api_key_env=str(data["api_key_env"]),
                    request_options=dict(data.get("request_options", {})),
                )
            }
        if not isinstance(declared, dict) or not declared:
            raise ConfigError(f"privacy.{name}: providers must not be empty")
        return {
            str(provider_name): Provider.from_dict(str(provider_name), body)
            for provider_name, body in declared.items()
        }

    def options_for(self, model: str) -> dict[str, Any]:
        provider = self.provider_for(model)
        return merge_options(
            provider.request_options,
            provider.model_options.get(model[len(provider.name) + 1 :], {}),
        )

    def validate(self) -> None:
        for name, provider in self.providers.items():
            used = {model[len(name) + 1 :] for model in (*self.tiers, self.reviewer)}
            for model in provider.model_options:
                if model not in used:
                    raise ConfigError(
                        f"privacy.{self.name}: unknown model '{model}' in providers.{name}.models"
                    )
        for model in (*self.tiers, self.reviewer):
            if self.reviewer == "brain" and model == "brain":
                continue
            if provider_of(model) not in self.providers:
                raise ConfigError(
                    f"privacy.{self.name}: '{model}' does not name one of the providers "
                    f"({', '.join(self.providers)})"
                )
        if self.reviewer != "brain" and not self.provider_for(self.reviewer).is_https:
            raise ConfigError(
                f"privacy.{self.name}: the reviewer '{self.reviewer}' needs an https base_url, "
                "because Conductor sends it the API key"
            )

    def provider_for(self, model: str) -> Provider:
        provider = self.providers.get(provider_of(model))
        if provider is None:
            raise ConfigError(f"privacy.{self.name}: no provider for '{model}'")
        return provider

    def model_for_tier(self, tier: int) -> str | None:
        return self.tiers[tier] if 0 <= tier < len(self.tiers) else None

    def dump(self) -> str:
        lines = [
            f"[privacy.{toml_key(self.name)}]",
            f"max_parallel = {toml_value(self.max_parallel)}",
            "tiers = [",
            *(f"  {toml_value(tier)}," for tier in self.tiers),
            "]",
            f"reviewer = {toml_value(self.reviewer)}",
        ]
        if self.transient_attempts != DEFAULT_TRANSIENT_ATTEMPTS:
            lines.append(f"retry = {toml_value({'transient_attempts': self.transient_attempts})}")
        for name, provider in self.providers.items():
            prefix = f"privacy.{toml_key(self.name)}.providers.{toml_key(name)}"
            lines.extend(["", f"[{prefix}]"])
            lines.extend(provider.dump(prefix))
        return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class Config:
    default_privacy: str
    profiles: dict[str, Profile]

    @classmethod
    def from_data(cls, data: dict[str, Any]) -> Config:
        profiles = {
            name: Profile.from_dict(name, body) for name, body in data.get("privacy", {}).items()
        }
        if not profiles:
            raise ConfigError("no [privacy.<level>] profiles defined")
        return cls(default_privacy=str(data.get("default_privacy", "medium")), profiles=profiles)

    @classmethod
    def load(cls, path: Path) -> Config:
        return cls.from_data(tomllib.loads(path.read_text()))

    def dump(self) -> str:
        head = f"{DUMP_HEADER}\ndefault_privacy = {toml_value(self.default_privacy)}\n"
        return "\n".join([head, *(profile.dump() for profile in self.profiles.values())])

    def profile(self, name: str | None) -> Profile:
        chosen = name or self.default_privacy
        if chosen not in self.profiles:
            raise ConfigError(f"unknown privacy level '{chosen}'")
        return self.profiles[chosen]
