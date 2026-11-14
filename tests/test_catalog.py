from typing import Any

import pytest

from conductor.catalog import (
    CatalogError,
    CatalogModel,
    fetch_models,
    forget_prices,
    model_costs,
    parse_models,
    select_models,
)

OPENROUTER_PAYLOAD = {
    "data": [
        {
            "id": "deepseek/flash",
            "pricing": {"prompt": "0.0000003", "completion": "0.0000012"},
            "context_length": 128000,
            "supported_parameters": ["tools", "max_tokens"],
        },
        {
            "id": "google/gemma:free",
            "pricing": {"prompt": "0", "completion": "0"},
            "context_length": 32000,
            "supported_parameters": ["max_tokens"],
        },
        {"id": "openrouter/auto", "pricing": {"prompt": "-1", "completion": "-1"}},
    ]
}

OPENROUTER_WITH_CACHE_PAYLOAD = {
    "data": [
        {
            "id": "deepseek/flash",
            "pricing": {
                "prompt": "0.0000003",
                "completion": "0.0000012",
                "input_cache_read": "0.0000001",
                "input_cache_write": "0.00000015",
            },
            "context_length": 128000,
            "supported_parameters": ["tools", "max_tokens"],
        },
        {
            "id": "google/gemma:free",
            "pricing": {"prompt": "0", "completion": "0"},
            "context_length": 32000,
            "supported_parameters": ["max_tokens"],
        },
    ]
}

VERCEL_PAYLOAD = {
    "data": [
        {
            "id": "alibaba/qwen-3-14b",
            "type": "language",
            "context_window": 40960,
            "supported_parameters": ["tools"],
            "pricing": {"input": "0.00000012", "output": "0.00000024"},
        },
        {"id": "meta/muse-image-1.0", "type": "image", "pricing": {}},
    ]
}

VERCEL_WITH_CACHE_PAYLOAD = {
    "data": [
        {
            "id": "alibaba/qwen-3-14b",
            "type": "language",
            "context_window": 40960,
            "supported_parameters": ["tools"],
            "pricing": {
                "input": "0.00000012",
                "output": "0.00000024",
                "cache_read": "0.00000006",
                "cache_write": "0.00000008",
            },
        },
    ]
}

FLASH = CatalogModel("deepseek/flash", 0.3, 1.2, 0.0, 0.0, 128000, True)
GEMMA = CatalogModel("google/gemma:free", 0.0, 0.0, 0.0, 0.0, 32000, False)
SONNET = CatalogModel("anthropic/sonnet", 2.0, 10.0, 0.0, 0.0, 500000, True)
NEMOTRON = CatalogModel("nvidia/nemotron:free", 0.0, 0.0, 0.0, 0.0, 64000, True)

FLASH_WITH_CACHE = CatalogModel("deepseek/flash", 0.3, 1.2, 0.1, 0.15, 128000, True)
QWEN_WITH_CACHE = CatalogModel("alibaba/qwen-3-14b", 0.12, 0.24, 0.06, 0.08, 40960, True)


def test_parse_models_reads_openrouter_prices_per_million_tokens() -> None:
    assert parse_models(OPENROUTER_PAYLOAD) == [FLASH, GEMMA]


def test_parse_models_reads_the_vercel_gateway_shape_and_skips_non_language_models() -> None:
    assert parse_models(VERCEL_PAYLOAD) == [
        CatalogModel("alibaba/qwen-3-14b", 0.12, 0.24, 0.0, 0.0, 40960, True)
    ]


def test_parse_models_reads_openrouter_cache_prices_per_million() -> None:
    models = parse_models(OPENROUTER_WITH_CACHE_PAYLOAD)
    assert models == [FLASH_WITH_CACHE, GEMMA]


def test_parse_models_reads_vercel_cache_prices_per_million() -> None:
    models = parse_models(VERCEL_WITH_CACHE_PAYLOAD)
    assert models == [QWEN_WITH_CACHE]


def test_parse_models_skips_batch_only_variants() -> None:
    payload = {
        "data": [
            {
                "id": "deepseek/flash:batch",
                "pricing": {"prompt": "0.0001", "completion": "0.0002"},
                "supported_parameters": ["tools"],
            },
            {
                "id": "deepseek/flash",
                "pricing": {"prompt": "0.0003", "completion": "0.0012"},
                "supported_parameters": ["tools"],
            },
        ]
    }
    assert [model.id for model in parse_models(payload)] == ["deepseek/flash"]


def test_parse_models_rejects_a_payload_without_a_model_list() -> None:
    with pytest.raises(CatalogError, match="unexpected response"):
        parse_models({"error": "maintenance"})


def test_fetch_models_asks_the_models_endpoint_of_the_base_url() -> None:
    seen: list[str] = []

    def fake_get(url: str) -> dict[str, Any]:
        seen.append(url)
        return OPENROUTER_PAYLOAD

    assert len(fetch_models("https://openrouter.ai/api/v1/", fake_get)) == 2
    assert seen == ["https://openrouter.ai/api/v1/models"]


def test_select_models_keeps_tool_capable_models_cheapest_first() -> None:
    assert select_models([SONNET, GEMMA, FLASH, NEMOTRON]) == [NEMOTRON, FLASH, SONNET]


def test_select_models_filters_by_price_class_and_search_text() -> None:
    models = [SONNET, GEMMA, FLASH, NEMOTRON]
    assert select_models(models, free=True) == [NEMOTRON]
    assert select_models(models, free=False) == [FLASH, SONNET]
    assert select_models(models, tools_only=False, free=True) == [GEMMA, NEMOTRON]
    assert select_models(models, search="SONN") == [SONNET]
    assert select_models(models, search="deep flash") == [FLASH]


def test_model_costs_returns_four_prices_per_model_id() -> None:
    def fake_get(url: str) -> dict[str, Any]:
        return OPENROUTER_WITH_CACHE_PAYLOAD

    costs = model_costs("https://openrouter.ai/api/v1/", fake_get)
    assert costs == {
        "deepseek/flash": {
            "input": 0.3,
            "output": 1.2,
            "cacheRead": 0.1,
            "cacheWrite": 0.15,
        },
        "google/gemma:free": {
            "input": 0.0,
            "output": 0.0,
            "cacheRead": 0.0,
            "cacheWrite": 0.0,
        },
    }


def test_model_costs_caches_results_same_base_url() -> None:
    call_count = 0

    def fake_get(url: str) -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        return OPENROUTER_WITH_CACHE_PAYLOAD

    forget_prices()
    model_costs("https://openrouter.ai/api/v1/", fake_get)
    model_costs("https://openrouter.ai/api/v1/", fake_get)
    assert call_count == 1


def test_model_costs_caches_results_different_base_urls() -> None:
    call_count = 0

    def fake_get(url: str) -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        return OPENROUTER_WITH_CACHE_PAYLOAD

    forget_prices()
    model_costs("https://openrouter.ai/api/v1/", fake_get)
    model_costs("https://api.deepseek.com/v1/", fake_get)
    assert call_count == 2


def test_model_costs_returns_empty_on_catalog_error() -> None:
    def fake_get(url: str) -> dict[str, Any]:
        raise CatalogError("network error")

    forget_prices()
    costs = model_costs("https://openrouter.ai/api/v1/", fake_get)
    assert costs == {}


def test_forget_prices_empties_the_cache() -> None:
    call_count = 0

    def fake_get(url: str) -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        return OPENROUTER_WITH_CACHE_PAYLOAD

    forget_prices()
    model_costs("https://openrouter.ai/api/v1/", fake_get)
    assert call_count == 1
    forget_prices()
    model_costs("https://openrouter.ai/api/v1/", fake_get)
    assert call_count == 2
