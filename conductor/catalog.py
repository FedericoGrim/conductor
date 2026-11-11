from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

Get = Callable[[str], dict[str, Any]]


class CatalogError(RuntimeError):
    pass


@dataclass(frozen=True)
class CatalogModel:
    id: str
    prompt_price: float
    completion_price: float
    context: int
    supports_tools: bool

    @property
    def is_free(self) -> bool:
        return self.prompt_price == 0 and self.completion_price == 0


def parse_models(payload: dict[str, Any]) -> list[CatalogModel]:
    raise NotImplementedError


def fetch_models(base_url: str, get: Get | None = None) -> list[CatalogModel]:
    raise NotImplementedError


def select_models(
    models: list[CatalogModel],
    search: str = "",
    free: bool | None = None,
    tools_only: bool = True,
) -> list[CatalogModel]:
    raise NotImplementedError
