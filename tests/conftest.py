from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_data_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_home = tmp_path / "xdg-data"
    monkeypatch.setenv("XDG_DATA_HOME", str(data_home))
    return data_home
