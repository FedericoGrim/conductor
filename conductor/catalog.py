from __future__ import annotations

import json
import urllib.error
import urllib.request
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


def http_get(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "conductor-catalog"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload: dict[str, Any] = json.loads(response.read())
            return payload
    except urllib.error.HTTPError as error:
        raise CatalogError(f"{url} answered HTTP {error.code}") from error
    except (OSError, ValueError) as error:
        raise CatalogError(f"{url} could not be read") from error


def price_per_million(price: object) -> float:
    return round(float(str(price or 0)) * 1_000_000, 6)


def parse_model(entry: dict[str, Any]) -> CatalogModel | None:
    pricing = entry.get("pricing") or {}
    prompt = price_per_million(pricing.get("prompt", pricing.get("input")))
    completion = price_per_million(pricing.get("completion", pricing.get("output")))
    is_language_model = entry.get("type", "language") == "language"
    if not is_language_model or prompt < 0 or completion < 0:
        return None
    return CatalogModel(
        id=str(entry["id"]),
        prompt_price=prompt,
        completion_price=completion,
        context=int(entry.get("context_length") or entry.get("context_window") or 0),
        supports_tools="tools" in (entry.get("supported_parameters") or []),
    )


def parse_models(payload: dict[str, Any]) -> list[CatalogModel]:
    entries = payload.get("data")
    if not isinstance(entries, list):
        raise CatalogError("unexpected response from the models endpoint")
    try:
        parsed = [parse_model(entry) for entry in entries]
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise CatalogError("unexpected response from the models endpoint") from error
    return [model for model in parsed if model is not None]


def fetch_models(base_url: str, get: Get | None = None) -> list[CatalogModel]:
    get = get or http_get
    return parse_models(get(f"{base_url.rstrip('/')}/models"))


def select_models(
    models: list[CatalogModel],
    search: str = "",
    free: bool | None = None,
    tools_only: bool = True,
) -> list[CatalogModel]:
    words = search.lower().split()
    selected = [
        model
        for model in models
        if (model.supports_tools or not tools_only)
        and (free is None or model.is_free == free)
        and all(word in model.id.lower() for word in words)
    ]
    return sorted(
        selected, key=lambda model: (model.completion_price, model.prompt_price, model.id)
    )
