import pytest

from conductor.errors import (
    MODEL_UNSUITABLE,
    PROVIDER_UNUSABLE,
    TRANSIENT,
    UNCLASSIFIED,
    ModelError,
)
from conductor.worker import attempt_error, classify_opencode_error


def error_event(kind: str, message: str = "boom", event: str = "error") -> dict[str, object]:
    return {"type": event, "sessionID": "ses", "error": {"type": kind, "message": message}}


@pytest.mark.parametrize(
    ("opencode_type", "message", "expected"),
    [
        ("provider.rate-limit", "Rate limit exceeded", TRANSIENT),
        ("provider.internal", "Internal error", TRANSIENT),
        ("provider.transport", "ECONNREFUSED", TRANSIENT),
        ("provider.auth", "Invalid API key", PROVIDER_UNUSABLE),
        ("provider.quota", "Insufficient credits", PROVIDER_UNUSABLE),
        ("provider.no-route", "Model unavailable: fake/nope", MODEL_UNSUITABLE),
        (
            "provider.invalid-request",
            "This model's maximum context length is 8192 tokens.",
            MODEL_UNSUITABLE,
        ),
        ("provider.invalid-request", "Model not found: foo", UNCLASSIFIED),
        ("tool.crashed", "whatever", UNCLASSIFIED),
    ],
)
def test_classifies_opencode_error_types(opencode_type: str, message: str, expected: str) -> None:
    error = classify_opencode_error({"type": opencode_type, "message": message})
    assert error == ModelError(expected, opencode_type, message)


def test_classification_truncates_long_messages() -> None:
    error = classify_opencode_error({"type": "provider.auth", "message": "x" * 5000})
    assert len(error.message) == 500


def test_no_error_when_the_run_succeeded() -> None:
    assert attempt_error([{"type": "text"}], exit_code=0, stderr="") is None


def test_last_error_event_decides_the_class() -> None:
    events = [
        error_event("provider.rate-limit", event="retry"),
        error_event("provider.auth", "Invalid API key"),
    ]
    error = attempt_error(events, exit_code=1, stderr="")
    assert error == ModelError(PROVIDER_UNUSABLE, "provider.auth", "Invalid API key")


def test_retry_events_alone_are_transient() -> None:
    events = [error_event("provider.internal", event="retry")]
    error = attempt_error(events, exit_code=-15, stderr="")
    assert error is not None
    assert error.kind == TRANSIENT


def test_failure_without_error_event_is_unclassified_with_stderr() -> None:
    error = attempt_error([], exit_code=2, stderr="panic: something\n")
    assert error == ModelError(UNCLASSIFIED, "exit 2", "panic: something")
