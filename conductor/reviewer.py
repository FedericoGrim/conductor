from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from conductor import credentials
from conductor.config import Profile
from conductor.errors import (
    MODEL_UNSUITABLE,
    PROVIDER_UNUSABLE,
    TRANSIENT,
    UNCLASSIFIED,
    ModelError,
    mentions_context_limit,
)
from conductor.privacy import api_model_id
from conductor.verify import CheckResult

Post = Callable[[str, dict[str, str], dict[str, Any]], dict[str, Any]]

SYSTEM_PROMPT = (
    "You are a strict code reviewer. You receive a task specification, the diff a model "
    "produced for it, the domain rules of the project and the verification commands that "
    "already passed. Approve only if every criterion holds:\n"
    "1. The diff implements the specification completely.\n"
    "2. New or changed behaviour comes with tests in the diff that exercise it; documentation "
    "and configuration need none.\n"
    "3. The domain rules hold: names, invariants and boundaries.\n"
    "4. There are no obvious bugs or security issues.\n"
    "On rejection, name the criterion and what to change. "
    'Answer with JSON only: {"ok": true|false, "reason": "<one or two sentences>"}.'
)
CHECK_OUTPUT_LIMIT = 1000

JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)
PROVIDER_UNUSABLE_STATUSES = {401, 402, 403}
UNPARSEABLE = "unparseable verdict"


@dataclass
class Verdict:
    ok: bool
    reason: str
    raw: str
    usage: dict[str, Any] = field(default_factory=dict)
    error: ModelError | None = None

    @classmethod
    def failed(cls, error: ModelError, raw: str = "") -> Verdict:
        return cls(False, f"reviewer error: {error.describe()}", raw, error=error)

    @property
    def cost(self) -> float | None:
        reported = self.usage.get("cost")
        return float(reported) if isinstance(reported, int | float) else None


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


def classify_http_error(error: urllib.error.HTTPError) -> ModelError:
    body = error.read().decode(errors="replace") if error.fp else ""
    kind = UNCLASSIFIED
    if error.code == 429 or error.code >= 500:
        kind = TRANSIENT
    elif error.code in PROVIDER_UNUSABLE_STATUSES:
        kind = PROVIDER_UNUSABLE
    elif error.code == 404 or mentions_context_limit(body):
        kind = MODEL_UNSUITABLE
    return ModelError.of(kind, f"http-{error.code}", body or str(error.reason))


def review_request(spec: str, diff: str, rules: tuple[str, ...], checks: list[CheckResult]) -> str:
    sections = [f"## Specification\n{spec}"]
    if rules:
        sections.append("## Domain rules\n" + "\n".join(f"- {rule}" for rule in rules))
    if checks:
        outcomes = "\n".join(
            f"- `{check.command}`: exit {check.exit_code}\n"
            f"```\n{check.output[-CHECK_OUTPUT_LIMIT:].strip()}\n```"
            for check in checks
        )
        sections.append(f"## Verification (run by Conductor)\n{outcomes}")
    sections.append(f"## Diff\n```diff\n{diff}\n```")
    return "\n\n".join(sections)


def review(
    profile: Profile,
    model: str,
    spec: str,
    diff: str,
    post: Post | None = None,
    rules: tuple[str, ...] = (),
    checks: list[CheckResult] | None = None,
) -> Verdict:
    post = post or http_post
    provider = profile.provider_for(model)
    if not provider.is_https:
        return Verdict.failed(
            ModelError.of(
                PROVIDER_UNUSABLE,
                "insecure-base-url",
                f"refusing to send the API key to {provider.base_url}: base_url must be https",
            )
        )
    api_key = credentials.api_key(provider.api_key_env)
    if not api_key:
        return Verdict.failed(
            ModelError.of(
                PROVIDER_UNUSABLE,
                "missing-key",
                f"no API key: set {provider.api_key_env} or store it with `conductor setup`",
            )
        )
    body = {
        **profile.options_for(model),
        "model": api_model_id(provider.name, model),
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": review_request(spec, diff, rules, checks or [])},
        ],
    }
    try:
        response = post(
            f"{provider.base_url.rstrip('/')}/chat/completions",
            {"Authorization": f"Bearer {api_key}"},
            body,
        )
    except urllib.error.HTTPError as error:
        return Verdict.failed(classify_http_error(error))
    except (urllib.error.URLError, TimeoutError) as error:
        return Verdict.failed(ModelError.of(TRANSIENT, "network", str(error)))
    try:
        content = str(response["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError):
        return Verdict.failed(
            ModelError.of(UNCLASSIFIED, "malformed-response", json.dumps(response)), raw=""
        )
    parsed = parse_verdict(content)
    usage = dict(response.get("usage", {}))
    if parsed is None:
        unparseable = ModelError.of(MODEL_UNSUITABLE, "unparseable-verdict", content)
        return Verdict(False, UNPARSEABLE, content, usage, unparseable)
    return Verdict(parsed[0], parsed[1], content, usage)
