from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Tokens:
    """Token counts from a model call. None means the harness did not report that field."""

    input: int | None = None
    output: int | None = None
    reasoning: int | None = None
    cache_read: int | None = None
    cache_write: int | None = None

    def plus(self, other: Tokens) -> Tokens:
        """Add two Tokens together. None + None = None, otherwise None counts as 0."""
        return Tokens(
            input=_add_opt(self.input, other.input),
            output=_add_opt(self.output, other.output),
            reasoning=_add_opt(self.reasoning, other.reasoning),
            cache_read=_add_opt(self.cache_read, other.cache_read),
            cache_write=_add_opt(self.cache_write, other.cache_write),
        )

    def to_dict(self) -> dict[str, int | None]:
        return {
            "input": self.input,
            "output": self.output,
            "reasoning": self.reasoning,
            "cache_read": self.cache_read,
            "cache_write": self.cache_write,
        }

    @classmethod
    def from_dict(cls, data: object) -> Tokens:
        if not isinstance(data, dict):
            return Tokens()
        return Tokens(
            input=_int_or_none(data.get("input")),
            output=_int_or_none(data.get("output")),
            reasoning=_int_or_none(data.get("reasoning")),
            cache_read=_int_or_none(data.get("cache_read")),
            cache_write=_int_or_none(data.get("cache_write")),
        )

    @property
    def cache_share(self) -> float | None:
        if self.input is None or self.cache_read is None:
            return None
        total = self.input + self.cache_read
        if total == 0:
            return None
        return self.cache_read / total


def _add_opt(a: int | None, b: int | None) -> int | None:
    if a is None and b is None:
        return None
    return (a or 0) + (b or 0)


def _int_or_none(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def total(items: Iterable[Tokens]) -> Tokens:
    result = Tokens()
    for item in items:
        result = result.plus(item)
    return result


def no_tokens(events: list[dict[str, Any]]) -> Tokens:
    """Default token reader that returns empty Tokens."""
    return Tokens()
