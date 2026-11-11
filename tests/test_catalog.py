from typing import Any

import pytest

from conductor.catalog import CatalogError, CatalogModel, fetch_models, parse_models, select_models

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

FLASH = CatalogModel("deepseek/flash", 0.3, 1.2, 128000, True)
GEMMA = CatalogModel("google/gemma:free", 0.0, 0.0, 32000, False)
SONNET = CatalogModel("anthropic/sonnet", 2.0, 10.0, 500000, True)
NEMOTRON = CatalogModel("nvidia/nemotron:free", 0.0, 0.0, 64000, True)


def test_parse_models_reads_openrouter_prices_per_million_tokens() -> None:
    assert parse_models(OPENROUTER_PAYLOAD) == [FLASH, GEMMA]


def test_parse_models_reads_the_vercel_gateway_shape_and_skips_non_language_models() -> None:
    assert parse_models(VERCEL_PAYLOAD) == [
        CatalogModel("alibaba/qwen-3-14b", 0.12, 0.24, 40960, True)
    ]


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
