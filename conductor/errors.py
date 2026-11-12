from __future__ import annotations

from dataclasses import dataclass

TRANSIENT = "transient"
PROVIDER_UNUSABLE = "provider_unusable"
MODEL_UNSUITABLE = "model_unsuitable"
UNCLASSIFIED = "unclassified"

MESSAGE_LIMIT = 500


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
