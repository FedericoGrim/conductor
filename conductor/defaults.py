from __future__ import annotations

from typing import Any

from conductor.config import Config, Profile, Provider

DIFFICULTY_LEVELS = 5

OPENROUTER = "https://openrouter.ai/api/v1"
OPENROUTER_EU = "https://eu.openrouter.ai/api/v1"
NO_TRAINING = {"provider": {"data_collection": "deny"}}


def profile(
    name: str,
    base_url: str,
    tiers: tuple[str, ...],
    reviewer: str,
    max_parallel: int,
    request_options: dict[str, Any],
) -> Profile:
    provider = Provider("openrouter", base_url, "OPENROUTER_API_KEY", dict(request_options))
    return Profile(name, {"openrouter": provider}, tiers, reviewer, max_parallel)


DEFAULT_PROFILES: tuple[Profile, ...] = (
    profile(
        "low",
        OPENROUTER,
        (
            "openrouter/thinkingmachines/inkling-2-small:free",
            "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free",
            "openrouter/z-ai/glm-5.3-flash",
            "openrouter/deepseek/deepseek-v4-flash-0731",
            "openrouter/openai/gpt-5.6-luna",
        ),
        "openrouter/z-ai/glm-5.3-flash",
        2,
        {},
    ),
    profile(
        "medium",
        OPENROUTER,
        (
            "openrouter/deepseek/deepseek-v4-flash-0731",
            "openrouter/z-ai/glm-5.3-flash",
            "openrouter/openai/gpt-5.6-luna",
            "openrouter/z-ai/glm-5.3",
            "openrouter/deepseek/deepseek-v4-pro-0813",
        ),
        "openrouter/openai/gpt-5.6-luna",
        4,
        NO_TRAINING,
    ),
    profile(
        "high",
        OPENROUTER_EU,
        (
            "openrouter/z-ai/glm-5.3-flash",
            "openrouter/deepseek/deepseek-v4-flash-0731",
            "openrouter/openai/gpt-5.6-luna",
            "openrouter/z-ai/glm-5.3",
            "openrouter/anthropic/claude-opus-5.5",
        ),
        "openrouter/openai/gpt-5.6-luna",
        4,
        {},
    ),
)


def default_config() -> Config:
    return Config("medium", {profile.name: profile for profile in DEFAULT_PROFILES})
