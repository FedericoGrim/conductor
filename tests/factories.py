from __future__ import annotations

from pathlib import Path
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
        tuple((tier,) for tier in tiers),
        (reviewer,),
        max_parallel,
    )


def install_git_hook(repo: Path, name: str, script: str) -> None:
    hook = repo / ".git" / "hooks" / name
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("#!/bin/sh\n" + script)
    hook.chmod(0o755)


CONVENTIONAL_COMMIT_HOOK = (
    "grep -qE '^(build|chore|ci|docs|feat|fix|perf|refactor|style|test)(\\(.+\\))?!?: ' \"$1\""
    " || { echo 'Bad commit message'; exit 1; }\n"
)
