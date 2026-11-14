from __future__ import annotations

import urllib.parse
from typing import Any

from conductor.config import Profile, Provider

VERCEL_GATEWAY_HOST = "ai-gateway.vercel.sh"
OPENCODE = "opencode"
# OpenCode also loads the user's personal skills (~/.claude/skills, ~/.agents/skills): a worker
# must see only Conductor's prompt and the target repository.
NO_SKILLS = [{"action": "skill", "resource": "*", "effect": "deny"}]


def api_model_id(provider: str, model: str) -> str:
    prefix = provider + "/"
    return model[len(prefix) :] if model.startswith(prefix) else model


def opencode_options(provider: Provider, options: dict[str, Any]) -> dict[str, Any]:
    # Request options are the body of a direct OpenAI-compatible call (the reviewer). Vercel's
    # gateway takes them under "providerOptions"; OpenCode puts its model options there itself.
    if urllib.parse.urlsplit(provider.base_url).hostname != VERCEL_GATEWAY_HOST:
        return options
    unwrapped = {key: value for key, value in options.items() if key != "providerOptions"}
    return {**unwrapped, **options.get("providerOptions", {})}


def opencode_config(profile: Profile) -> dict[str, Any]:
    written = {
        name: provider
        for name, provider in profile.providers.items()
        if provider.harness == OPENCODE and provider.has_endpoint
    }
    models: dict[str, dict[str, Any]] = {name: {} for name in written}
    for model in (model for tier in profile.tiers for model in tier):
        provider = profile.provider_for(model)
        if provider.name in written:
            models[provider.name][api_model_id(provider.name, model)] = {
                "options": opencode_options(provider, profile.options_for(model))
            }
    small_model = next(
        (
            model
            for tier in profile.tiers
            for model in tier
            if profile.provider_for(model).harness == OPENCODE
        ),
        None,
    )
    config: dict[str, Any] = {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            name: {
                "options": {
                    **opencode_options(provider, provider.request_options),
                    "baseURL": provider.base_url,
                },
                "models": models[name],
            }
            for name, provider in written.items()
        },
        "permissions": NO_SKILLS,
    }
    # OpenCode sends title and summary requests to a model of its own choosing: pin it to
    # the profile, and put the provider options at provider level so they reach it anyway.
    if small_model is not None:
        config["small_model"] = small_model
    return config
