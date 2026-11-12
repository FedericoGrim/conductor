from __future__ import annotations

import re
from dataclasses import dataclass

TRANSIENT = "transient"
PROVIDER_UNUSABLE = "provider_unusable"
MODEL_UNSUITABLE = "model_unsuitable"
UNCLASSIFIED = "unclassified"

MESSAGE_LIMIT = 500
CONTEXT_EXCEEDED = re.compile(r"context (length|window)|too many tokens", re.IGNORECASE)


def mentions_context_limit(message: str) -> bool:
    return CONTEXT_EXCEEDED.search(message) is not None


@dataclass(frozen=True)
class ModelError:
    kind: str
    type: str
    message: str

    @classmethod
    def of(cls, kind: str, type_: str, message: str) -> ModelError:
        return cls(kind, type_, message.strip()[-MESSAGE_LIMIT:])

    def describe(self) -> str:
        return f"{self.kind} ({self.type}): {self.message}"
