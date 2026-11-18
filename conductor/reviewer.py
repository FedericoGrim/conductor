from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from conductor import credentials, rejections
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
from conductor.tokens import Tokens
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
    "5. The commit message, when given, describes the diff and has the right Conventional "
    "Commit type (new behaviour is feat, not fix or chore; a bug fix is fix; tests only is "
    "test; documentation only is docs).\n"
    "The verification commands already ran and passed: problems they check (imports, types, "
    "syntax, formatting, lint, failing tests) are settled and never a reason to reject. The "
    "diff shows only part of each file: code you cannot see (imports, definitions elsewhere "
    "in a file) is not missing.\n"
    "On rejection, name the criterion and what to change. "
    "Answer with JSON only: "
    f'{{"ok": true|false, "category": "<one of: {", ".join(rejections.CATEGORIES)}>", '
    f'"reason": "<one or two sentences>"}}. '
    "The category names the main criterion broken; it is required when ok is false."
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
    category: str | None = None

    @classmethod
    def failed(cls, error: ModelError, raw: str = "") -> Verdict:
        return cls(False, f"reviewer error: {error.describe()}", raw, error=error)

    @property
    def cost(self) -> float | None:
        reported = self.usage.get("cost")
        return float(reported) if isinstance(reported, int | float) else None

    @property
    def tokens(self) -> Tokens:
        return usage_tokens(self.usage)


def usage_tokens(usage: dict[str, Any]) -> Tokens:
    """Extract token counts from an OpenAI-compatible usage dict.

    Args:
        usage: The usage dict from the API response.

    Returns:
        Tokens with fields populated from the usage dict. Missing or non-int
        values (excluding bools) become None.
    """
    prompt_tokens = usage.get("prompt_tokens")
    completion_tokens = usage.get("completion_tokens")
    completion_details_raw = usage.get("completion_tokens_details")
    prompt_details_raw = usage.get("prompt_tokens_details")
    completion_details: dict[str, Any] = (
        completion_details_raw if isinstance(completion_details_raw, dict) else {}
    )
    prompt_details: dict[str, Any] = (
        prompt_details_raw if isinstance(prompt_details_raw, dict) else {}
    )

    reasoning = _int_or_none(completion_details.get("reasoning_tokens"))
    cache_read = _int_or_none(prompt_details.get("cached_tokens"))
    cache_write = _int_or_none(prompt_details.get("cache_write_tokens"))

    if isinstance(prompt_tokens, int) and not isinstance(prompt_tokens, bool):
        input_tokens = prompt_tokens - cache_read if isinstance(cache_read, int) else prompt_tokens
    else:
        input_tokens = None

    output_tokens = _int_or_none(completion_tokens)

    return Tokens(
        input=input_tokens,
        output=output_tokens,
        reasoning=reasoning,
        cache_read=cache_read,
        cache_write=cache_write,
    )


def _int_or_none(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def http_post(url: str, headers: dict[str, str], body: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={**headers, "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        payload: dict[str, Any] = json.loads(response.read())
        return payload


def parse_verdict(content: str) -> tuple[bool, str, str | None] | None:
    match = JSON_BLOCK.search(content)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or not isinstance(data.get("ok"), bool):
        return None
    ok = data["ok"]
    if not ok:
        category = data.get("category")
        if not isinstance(category, str) or category not in rejections.CATEGORIES:
            return None
        return ok, str(data.get("reason", "")), category
    return ok, str(data.get("reason", "")), None


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


def review_request(
    spec: str,
    diff: str,
    rules: tuple[str, ...],
    checks: list[CheckResult],
    commit_message: str = "",
) -> str:
    sections = [f"## Specification\n{spec}"]
    if rules:
        sections.append("## Domain rules\n" + "\n".join(f"- {rule}" for rule in rules))
    if checks:
        outcomes = "\n".join(
            f"- `{check.command}`: exit {check.exit_code}\n"
            f"```\n{check.output[-CHECK_OUTPUT_LIMIT:].strip()}\n```"
            for check in checks
        )
        sections.append(
            "## Verification (run by Conductor)\n"
            "All verification commands passed (exit 0); what they check is settled.\n"
            f"{outcomes}"
        )
    if commit_message:
        sections.append(f"## Commit message\n```\n{commit_message}\n```")
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
    commit_message: str = "",
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
            {
                "role": "user",
                "content": review_request(spec, diff, rules, checks or [], commit_message),
            },
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
    return Verdict(parsed[0], parsed[1], content, usage, category=parsed[2])
