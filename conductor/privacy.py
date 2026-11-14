from __future__ import annotations

import json
import urllib.parse
from pathlib import Path
from typing import Any

from conductor.config import Profile, Provider
from conductor.worker import exclude_from_git

VERCEL_GATEWAY_HOST = "ai-gateway.vercel.sh"
OPENROUTER_HOST = "openrouter.ai"
OPENCODE = "opencode"
PI = "pi"
# Pi reads provider configuration from models.json in its agent directory (PI_CODING_AGENT_DIR).
PI_AGENT_DIR = ".pi-agent"
PI_CONFIG_NAME = "models.json"
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


def pi_compat(provider: Provider, options: dict[str, Any]) -> dict[str, Any] | None:
    """compat.openRouterRouting carries OpenRouter routing options, on openrouter.ai only."""
    routing = options.get("provider")
    host = urllib.parse.urlsplit(provider.base_url).hostname or ""
    if routing is None or OPENROUTER_HOST not in host:
        return None
    return {"openRouterRouting": routing}


def pi_config(profile: Profile) -> dict[str, Any]:
    """The models.json for Pi: one entry per provider of the profile on the pi harness.

    apiKey is the environment variable NAME, never a value; the Vercel gateway training flag
    has no Pi equivalent and is refused when the profile loads.
    """
    written = {
        name: provider
        for name, provider in profile.providers.items()
        if provider.harness == PI and provider.has_endpoint
    }
    providers: dict[str, dict[str, Any]] = {}
    for name, provider in written.items():
        model_ids = dict.fromkeys(
            api_model_id(name, model)
            for model in profile.models()
            if profile.provider_for(model).name == name
        )
        entry: dict[str, Any] = {
            "baseUrl": provider.base_url,
            "api": "openai-completions",
            "apiKey": provider.api_key_env,
            "models": [{"id": model_id} for model_id in model_ids],
        }
        compat = pi_compat(provider, provider.request_options)
        if compat is not None:
            entry["compat"] = compat
        providers[name] = entry
    return {"providers": providers}


def write_pi_config(worktree: Path, config: dict[str, Any]) -> None:
    agent_dir = worktree / PI_AGENT_DIR
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / PI_CONFIG_NAME).write_text(json.dumps(config, indent=2) + "\n")
    exclude_from_git(worktree, PI_AGENT_DIR + "/")
