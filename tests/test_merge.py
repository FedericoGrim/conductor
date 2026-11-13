from pathlib import Path

from conductor.merge import merge_branch
from conductor.worker import commit_work, create_worktree, git
from tests.factories import CONVENTIONAL_COMMIT_HOOK, install_git_hook


def init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "shared.txt").write_text("base\n")
    commit_work(repo, "init")
    return repo


def test_merges_an_approved_branch_into_the_base(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    worktree = tmp_path / "wt"
    create_worktree(repo, worktree, "conductor/s1-1", "main")
    (worktree / "new.txt").write_text("hello\n")
    commit_work(worktree, "work")

    assert merge_branch(repo, "conductor/s1-1", into="main") is None
    assert (repo / "new.txt").read_text() == "hello\n"


def test_conflict_is_reported_and_the_base_stays_clean(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    worktree = tmp_path / "wt"
    create_worktree(repo, worktree, "conductor/s1-1", "main")
    (worktree / "shared.txt").write_text("from model\n")
    commit_work(worktree, "work")
    (repo / "shared.txt").write_text("from main\n")
    commit_work(repo, "main moved")

    problem = merge_branch(repo, "conductor/s1-1", into="main")
    assert problem is not None and "shared.txt" in problem
    assert git(repo, "status", "--porcelain") == ""
    assert (repo / "shared.txt").read_text() == "from main\n"


def test_the_merge_commit_message_is_a_conventional_commit(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    worktree = tmp_path / "wt"
    create_worktree(repo, worktree, "conductor/s1-1", "main")
    (worktree / "new.txt").write_text("hello\n")
    commit_work(worktree, "chore(conductor): apply step s1 attempt 1")
    install_git_hook(repo, "commit-msg", CONVENTIONAL_COMMIT_HOOK)

    assert merge_branch(repo, "conductor/s1-1", into="main") is None
    assert git(repo, "log", "-1", "--format=%s") == "chore(conductor): merge conductor/s1-1\n"


def test_a_hook_rejecting_the_merge_is_reported_and_the_base_stays_clean(tmp_path: Path) -> None:
    repo = init_repo(tmp_path)
    worktree = tmp_path / "wt"
    create_worktree(repo, worktree, "conductor/s1-1", "main")
    (worktree / "new.txt").write_text("hello\n")
    commit_work(worktree, "work")
    install_git_hook(repo, "commit-msg", "echo 'merge refused by policy'\nexit 1\n")

    problem = merge_branch(repo, "conductor/s1-1", into="main")

    assert problem is not None and "merge refused by policy" in problem
    assert git(repo, "status", "--porcelain") == ""
    assert not (repo / "new.txt").exists()
