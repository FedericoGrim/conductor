from __future__ import annotations

import json
import os
import shutil
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from conductor import credentials
from conductor.config import Config, ConfigError

SCHEMA = 1
METADATA_TABLE = "conductor"


class SettingsError(ValueError):
    pass


@dataclass(frozen=True)
class ImportResult:
    profiles: tuple[str, ...]
    path: Path
    backup: Path | None
    missing_keys: tuple[str, ...]


def exported_at() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def metadata(version: str) -> dict[str, Any]:
    return {"schema": SCHEMA, "version": version, "exported_at": exported_at()}


def toml_scalar(value: Any) -> str:
    return json.dumps(value) if isinstance(value, str) else str(value).lower()


def export_settings(config: Config, target: Path, version: str) -> Path:
    header = [f"[{METADATA_TABLE}]"]
    header.extend(f"{key} = {toml_scalar(value)}" for key, value in metadata(version).items())
    body = config.dump().splitlines()
    while body and body[0].startswith("#"):
        body.pop(0)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join([*body, "", *header]) + "\n")
    return target


def read_settings(source: Path) -> tuple[Config, dict[str, Any]]:
    try:
        data = tomllib.loads(source.read_text())
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise SettingsError(f"cannot read {source}: {error}") from error
    meta = data.pop(METADATA_TABLE, {})
    schema = meta.get("schema", SCHEMA)
    if not isinstance(schema, int) or schema > SCHEMA:
        raise SettingsError(f"settings schema {schema} is newer than this conductor ({SCHEMA})")
    try:
        config = Config.from_data(data)
    except ConfigError as error:
        raise SettingsError(f"invalid configuration: {error}") from error
    return config, meta


def missing_keys(config: Config) -> tuple[str, ...]:
    names = {
        provider.api_key_env
        for profile in config.profiles.values()
        for provider in profile.providers.values()
    }
    return tuple(sorted(name for name in names if not credentials.api_key(name)))


def import_settings(source: Path, target: Path) -> ImportResult:
    config, _ = read_settings(source)
    backup = None
    if target.exists():
        backup = target.with_name(target.name + ".bak")
        shutil.copy2(target, backup)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text(config.dump())
    os.replace(temporary, target)
    return ImportResult(
        profiles=tuple(config.profiles),
        path=target,
        backup=backup,
        missing_keys=missing_keys(config),
    )
