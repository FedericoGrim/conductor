from __future__ import annotations

from typing import Any

from conductor.config import Profile


def api_model_id(provider: str, model: str) -> str:
    prefix = provider + "/"
    return model[len(prefix) :] if model.startswith(prefix) else model


def opencode_config(profile: Profile) -> dict[str, Any]:
    models: dict[str, dict[str, Any]] = {name: {} for name in profile.providers}
    for model in (model for tier in profile.tiers for model in tier):
        provider = profile.provider_for(model)
        models[provider.name][api_model_id(provider.name, model)] = {
            "options": profile.options_for(model)
        }
    return {
        "$schema": "https://opencode.ai/config.json",
        # OpenCode sends title and summary requests to a model of its own choosing: pin it to
        # the profile, and put the provider options at provider level so they reach it anyway.
        "small_model": profile.tiers[0][0],
        "provider": {
            name: {
                "options": {
                    **profile.providers[name].request_options,
                    "baseURL": profile.providers[name].base_url,
                },
                "models": models[name],
            }
            for name in profile.providers
        },
    }
