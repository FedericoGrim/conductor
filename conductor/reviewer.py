from __future__ import annotations

import json
import os
import re
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from conductor.config import Profile
from conductor.privacy import api_model_id

Post = Callable[[str, dict[str, str], dict[str, Any]], dict[str, Any]]

SYSTEM_PROMPT = (
    "You are a strict code reviewer. You receive a task specification and the diff that "
    "a model produced for it. Decide whether the diff correctly and completely implements "
    "the specification without introducing obvious bugs or security issues. "
    'Answer with JSON only: {"ok": true|false, "reason": "<one or two sentences>"}.'
)

JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


class ReviewerError(RuntimeError):
    pass


@dataclass
class Verdict:
    ok: bool
    reason: str
    raw: str
    usage: dict[str, Any] = field(default_factory=dict)

    @property
    def cost(self) -> float | None:
        raise NotImplementedError


def http_post(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={**headers, "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        payload: dict[str, Any] = json.loads(response.read())
        return payload


def parse_verdict(content: str) -> tuple[bool, str] | None:
    match = JSON_BLOCK.search(content)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("ok"), bool):
        return None
    return data["ok"], str(data.get("reason", ""))


def review(profile: Profile, spec: str, diff: str, post: Post | None = None) -> Verdict:
    post = post or http_post
    api_key = os.environ.get(profile.api_key_env)
    if not api_key:
        raise ReviewerError(f"environment variable {profile.api_key_env} is not set")
    body = {
        **profile.request_options,
        "model": api_model_id(profile, profile.reviewer),
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"## Specification\n{spec}\n\n## Diff\n```diff\n{diff}\n```",
            },
        ],
    }
    response = post(
        f"{profile.base_url.rstrip('/')}/chat/completions",
        {"Authorization": f"Bearer {api_key}"},
        body,
    )
    content = str(response["choices"][0]["message"]["content"])
    parsed = parse_verdict(content)
    usage = dict(response.get("usage", {}))
    if parsed is None:
        return Verdict(False, "unparseable verdict", content, usage)
    return Verdict(parsed[0], parsed[1], content, usage)
