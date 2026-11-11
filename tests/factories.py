from __future__ import annotations

from typing import Any

from conductor.config import Profile, Provider


def make_profile(
    name: str = "medium",
    provider: str = "openrouter",
    base_url: str = "https://openrouter.ai/api/v1",
    api_key_env: str = "TEST_PROFILE_KEY",
    tiers: tuple[str, ...] = ("openrouter/t0", "openrouter/t1", "openrouter/t2"),
    reviewer: str = "openrouter/r",
    max_parallel: int = 4,
    request_options: dict[str, Any] | None = None,
) -> Profile:
    return Profile(
        name,
        {provider: Provider(provider, base_url, api_key_env, dict(request_options or {}))},
        tiers,
        reviewer,
        max_parallel,
    )
