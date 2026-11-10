from __future__ import annotations

from typing import Any

from conductor.config import Profile


def api_model_id(profile: Profile, model: str) -> str:
    prefix = profile.provider + "/"
    return model[len(prefix) :] if model.startswith(prefix) else model


def opencode_config(profile: Profile) -> dict[str, Any]:
    models = {
        api_model_id(profile, model): {"options": dict(profile.request_options)}
        for model in profile.tiers
    }
    return {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            profile.provider: {"options": {"baseURL": profile.base_url}, "models": models}
        },
    }
