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
    cache_read_price: float
    cache_write_price: float
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
    cache_read = price_per_million(pricing.get("input_cache_read", pricing.get("cache_read")))
    cache_write = price_per_million(pricing.get("input_cache_write", pricing.get("cache_write")))
    is_language_model = entry.get("type", "language") == "language"
    is_batch_only = str(entry.get("id", "")).endswith(":batch")
    if not is_language_model or is_batch_only or prompt < 0 or completion < 0:
        return None
    return CatalogModel(
        id=str(entry["id"]),
        prompt_price=prompt,
        completion_price=completion,
        cache_read_price=cache_read,
        cache_write_price=cache_write,
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


_MODEL_COSTS_CACHE: dict[str, dict[str, dict[str, float]]] = {}


def model_costs(base_url: str, get: Get | None = None) -> dict[str, dict[str, float]]:
    """Return the prices of every model the endpoint lists, keyed by model id.

    Each value is a dict with keys "input", "output", "cacheRead", "cacheWrite".
    On any CatalogError return {} and never raise.
    Results are cached per base_url.
    """
    if base_url in _MODEL_COSTS_CACHE:
        return _MODEL_COSTS_CACHE[base_url]

    get = get or http_get
    try:
        payload = get(f"{base_url.rstrip('/')}/models")
        models = parse_models(payload)
    except CatalogError:
        _MODEL_COSTS_CACHE[base_url] = {}
        return {}

    result: dict[str, dict[str, float]] = {}
    for model in models:
        result[model.id] = {
            "input": model.prompt_price,
            "output": model.completion_price,
            "cacheRead": model.cache_read_price,
            "cacheWrite": model.cache_write_price,
        }
    _MODEL_COSTS_CACHE[base_url] = result
    return result


def forget_prices() -> None:
    """Clear the model costs cache. For tests and long-lived processes."""
    _MODEL_COSTS_CACHE.clear()
