from conductor.commits import (
    choose_commit_message,
    commit_line_in,
    fallback_subject,
    is_conventional,
)


def test_is_conventional_accepts_supported_subjects() -> None:
    assert is_conventional("feat(cli): add stats")
    assert is_conventional("fix!: drop x")
    assert is_conventional("docs: y")


def test_is_conventional_rejects_invalid_subjects() -> None:
    assert not is_conventional(": no type")
    assert not is_conventional("feature: add x")
    assert not is_conventional("feat(CLI): add x")
    assert not is_conventional("feat: ")
    assert not is_conventional("feat: " + "x" * 73)
    assert not is_conventional("feat: add x\nfix: add y")


def test_fallback_subject_is_a_conventional_commit() -> None:
    assert fallback_subject("parse-input", 2) == (
        "chore(conductor): apply step parse-input attempt 2"
    )


def test_commit_line_in_uses_the_last_marker() -> None:
    assert commit_line_in("COMMIT: feat: first\nCOMMIT: fix: last") == "fix: last"


def test_commit_line_in_handles_wrapped_marker_and_message() -> None:
    assert commit_line_in("**COMMIT:** feat: x") == "feat: x"
    assert commit_line_in("`COMMIT: `feat: x`") == "feat: x"


def test_commit_line_in_returns_none_without_a_marker_or_message() -> None:
    assert commit_line_in("no proposal here") is None
    assert commit_line_in("COMMIT:   ") is None


def test_choose_commit_message_uses_a_valid_worker_proposal() -> None:
    message = choose_commit_message("parse", 2, "provider/model", "COMMIT: feat: parse input")
    assert message == (
        "feat: parse input\n\n"
        "Written by a Conductor worker: step parse, attempt 2, on provider/model."
    )


def test_choose_commit_message_prefers_the_planned_subject() -> None:
    message = choose_commit_message(
        "parse", 2, "provider/model", "COMMIT: feat: worker proposal", "fix: planned change"
    )
    assert message.startswith("fix: planned change\n\n")


def test_choose_commit_message_falls_back_for_an_invalid_or_missing_proposal() -> None:
    for text in ("COMMIT: not conventional", "no proposal"):
        message = choose_commit_message("parse", 2, "provider/model", text)
        assert message.startswith(fallback_subject("parse", 2) + "\n\n")


def test_choose_commit_message_always_appends_the_worker_body() -> None:
    message = choose_commit_message("step-id", 7, "provider/model", "COMMIT: docs: update")
    assert message.endswith(
        "Written by a Conductor worker: step step-id, attempt 7, on provider/model."
    )
