from __future__ import annotations

import json
import os
from pathlib import Path


def credentials_path() -> Path:
    data_home = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(data_home) / "conductor" / "auth.json"


def stored_keys() -> dict[str, str]:
    try:
        data = json.loads(credentials_path().read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(name): str(value) for name, value in data.items()}


def write_keys(keys: dict[str, str]) -> None:
    path = credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    temporary = path.with_suffix(".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as file:
        file.write(json.dumps(keys, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(path)


def store_key(name: str, value: str) -> None:
    write_keys({**stored_keys(), name: value})


def remove_key(name: str) -> None:
    keys = stored_keys()
    if keys.pop(name, None) is not None:
        write_keys(keys)


def api_key(name: str) -> str | None:
    return os.environ.get(name) or stored_keys().get(name)
