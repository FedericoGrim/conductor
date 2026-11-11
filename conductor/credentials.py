from __future__ import annotations

from pathlib import Path


def credentials_path() -> Path:
    raise NotImplementedError


def stored_keys() -> dict[str, str]:
    raise NotImplementedError


def store_key(name: str, value: str) -> None:
    raise NotImplementedError


def remove_key(name: str) -> None:
    raise NotImplementedError


def api_key(name: str) -> str | None:
    raise NotImplementedError
