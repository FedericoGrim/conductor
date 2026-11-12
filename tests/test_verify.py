import asyncio
from pathlib import Path

from conductor.verify import OUTPUT_LIMIT, CheckResult, failure_reason, run_checks


def checks(commands: list[str], tmp_path: Path, timeout: float = 30) -> list[CheckResult]:
    worktree = tmp_path / "wt"
    worktree.mkdir(exist_ok=True)
    return asyncio.run(run_checks(tuple(commands), worktree, tmp_path / "repo", timeout))


def test_commands_run_in_order_in_the_worktree(tmp_path: Path) -> None:
    results = checks(["pwd", "echo second"], tmp_path)
    assert [r.ok for r in results] == [True, True]
    assert results[0].output.strip() == str(tmp_path / "wt")
    assert results[1].output.strip() == "second"


def test_the_main_repository_is_in_conductor_repo(tmp_path: Path) -> None:
    (result,) = checks(['echo "$CONDUCTOR_REPO"'], tmp_path)
    assert result.output.strip() == str(tmp_path / "repo")


def test_the_first_failure_stops_the_rest_and_keeps_stdout_and_stderr(tmp_path: Path) -> None:
    results = checks(["echo out; echo err >&2; exit 3", "echo never"], tmp_path)
    assert len(results) == 1
    assert results[0].exit_code == 3
    assert not results[0].ok
    assert "out" in results[0].output
    assert "err" in results[0].output


def test_a_command_past_the_timeout_fails_and_is_stopped(tmp_path: Path) -> None:
    (result,) = checks(["sleep 30"], tmp_path, timeout=0.3)
    assert result.timed_out
    assert not result.ok
    assert result.seconds < 10


def test_only_the_tail_of_a_long_output_is_kept(tmp_path: Path) -> None:
    (result,) = checks([f"head -c {OUTPUT_LIMIT * 3} /dev/zero | tr '\\\\0' x; echo END"], tmp_path)
    assert len(result.output) == OUTPUT_LIMIT
    assert result.output.endswith("END\n")


def test_failure_reason_names_the_command_and_its_output() -> None:
    failed = CheckResult("pytest -q", 1, "1 failed: test_total", 2.0)
    assert failure_reason(failed) == (
        "verification failed: `pytest -q` (exit 1)\n1 failed: test_total"
    )
    timed_out = CheckResult("pytest -q", None, "", 600.0, timed_out=True)
    assert failure_reason(timed_out).startswith("verification failed: `pytest -q` (timed out")
