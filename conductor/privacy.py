from __future__ import annotations

from typing import Any

from conductor.config import Profile


def api_model_id(provider: str, model: str) -> str:
    prefix = provider + "/"
    return model[len(prefix) :] if model.startswith(prefix) else model


def opencode_config(profile: Profile) -> dict[str, Any]:
    models: dict[str, dict[str, Any]] = {name: {} for name in profile.providers}
    for model in profile.tiers:
        provider = profile.provider_for(model)
        models[provider.name][api_model_id(provider.name, model)] = {
            "options": dict(provider.request_options)
        }
    return {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            name: {
                "options": {"baseURL": profile.providers[name].base_url},
                "models": models[name],
            }
            for name in profile.providers
        },
    }
