from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from conductor.config import Config

SCHEMA = 1


class SettingsError(ValueError):
    pass


@dataclass(frozen=True)
class ImportResult:
    profiles: tuple[str, ...]
    path: Path
    backup: Path | None
    missing_keys: tuple[str, ...]


def export_settings(config: Config, target: Path, version: str) -> Path:
    raise NotImplementedError


def import_settings(source: Path, target: Path) -> ImportResult:
    raise NotImplementedError


def exported_at() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
