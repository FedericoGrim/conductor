from __future__ import annotations

from conductor.config import Config, Profile, Provider

DIFFICULTY_LEVELS = 5

OPENROUTER = Provider("openrouter", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY")
OPENROUTER_NO_TRAINING = Provider(
    "openrouter",
    "https://openrouter.ai/api/v1",
    "OPENROUTER_API_KEY",
    {"provider": {"data_collection": "deny"}},
)
OPENROUTER_EU = Provider("openrouter", "https://eu.openrouter.ai/api/v1", "OPENROUTER_API_KEY")
DEEPSEEK = Provider("deepseek", "https://api.deepseek.com/v1", "DEEPSEEK_API_KEY")
VERCEL_NO_TRAINING = Provider(
    "vercel",
    "https://ai-gateway.vercel.sh/v1",
    "AI_GATEWAY_API_KEY",
    {"providerOptions": {"gateway": {"disallowPromptTraining": True}}},
)
SCALEWAY = Provider("scaleway", "https://api.scaleway.ai/v1", "SCALEWAY_API_KEY")


def profile(
    name: str,
    providers: tuple[Provider, ...],
    tiers: tuple[tuple[str, ...], ...],
    reviewers: tuple[str, ...],
    max_parallel: int,
) -> Profile:
    return Profile(
        name, {provider.name: provider for provider in providers}, tiers, reviewers, max_parallel
    )


DEFAULT_PROFILES: tuple[Profile, ...] = (
    profile(
        "low",
        (OPENROUTER, DEEPSEEK),
        (
            (
                "openrouter/thinkingmachines/inkling-2-small:free",
                "openrouter/dots-studio/dots-3-note-preview:free",
            ),
            (
                "openrouter/nvidia/nemotron-3-ultra-550b-a55b:free",
                "openrouter/recursive/flint-v1.0:free",
            ),
            ("openrouter/anthropic/claude-haiku-5.5", "deepseek/deepseek-flash"),
            (
                "openrouter/deepseek/deepseek-v4.1-flash-1017",
                "deepseek/deepseek-flash",
            ),
            ("openrouter/minimax/minimax-m3.1-flash", "deepseek/deepseek-v4-pro"),
        ),
        ("openrouter/z-ai/glm-5.3-flash", "deepseek/deepseek-flash"),
        2,
    ),
    profile(
        "medium",
        (OPENROUTER_NO_TRAINING, VERCEL_NO_TRAINING),
        (
            ("openrouter/anthropic/claude-haiku-5.5", "vercel/anthropic/claude-haiku-5.5"),
            (
                "openrouter/deepseek/deepseek-v4.1-flash-1017",
                "vercel/deepseek/deepseek-v4.1-flash-1017",
            ),
            (
                "openrouter/deepseek/deepseek-v4-flash-0731",
                "vercel/deepseek/deepseek-v4-flash-0731",
            ),
            ("openrouter/z-ai/glm-5.3-flash", "vercel/zai/glm-5.3-flash"),
            ("openrouter/minimax/minimax-m3.1-flash", "vercel/minimax/minimax-m3.1-flash"),
        ),
        ("openrouter/openai/gpt-5.6-luna", "vercel/openai/gpt-5.6-luna"),
        4,
    ),
    profile(
        "high",
        (OPENROUTER_EU, SCALEWAY),
        (
            ("openrouter/anthropic/claude-haiku-5.5", "scaleway/glm-5.3"),
            (
                "openrouter/deepseek/deepseek-v4.1-flash-1017",
                "scaleway/deepseek-v4.1-flash-1017",
            ),
            ("openrouter/z-ai/glm-5.3-flash", "scaleway/deepseek-v4-flash-0731"),
            ("openrouter/z-ai/glm-5.3", "scaleway/glm-5.3"),
            ("openrouter/anthropic/claude-opus-5.5", "scaleway/glm-5.3"),
        ),
        ("openrouter/openai/gpt-5.6-luna", "scaleway/deepseek-v4.1-flash-1017"),
        4,
    ),
)


def default_config() -> Config:
    return Config("medium", {profile.name: profile for profile in DEFAULT_PROFILES})
