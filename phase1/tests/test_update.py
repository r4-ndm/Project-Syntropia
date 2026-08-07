"""Tests for syntropia.update — the update subcommand."""

from pathlib import Path

import pytest

from syntropia import update as U


class FakeResult:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def noop_run(calls: list) -> callable:
    def _run(cmd: list, cwd=None) -> FakeResult:
        calls.append((cmd, cwd))
        return FakeResult(0)
    return _run


# -- detect_source ------------------------------------------------------

def test_detect_aur_when_pacman_q_succeeds(monkeypatch: pytest.MonkeyPatch):
    calls: list = []
    monkeypatch.setattr(U, "run_command", noop_run(calls))
    monkeypatch.setattr(U.shutil, "which", lambda _: "/usr/bin/pacman")
    assert U.detect_source() == "aur"


def test_detect_git_when_repo_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls: list = []
    monkeypatch.setattr(U, "run_command", noop_run(calls))
    monkeypatch.setattr(U.shutil, "which", lambda _: None)
    repo = tmp_path / "syntropia"
    repo.mkdir()
    (repo / ".git").mkdir()
    monkeypatch.setattr(U, "_repo_root", lambda: repo)
    assert U.detect_source() == "git"


def test_detect_pip_when_pip_show_succeeds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls: list = []
    monkeypatch.setattr(U, "run_command", noop_run(calls))
    monkeypatch.setattr(U.shutil, "which", lambda _: None)
    monkeypatch.setattr(U, "_repo_root", lambda: None)
    assert U.detect_source() == "pip"


def test_detect_unknown_when_nothing_matches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls: list = []

    def failing(cmd: list, cwd=None) -> FakeResult:
        return FakeResult(1, stderr="not found")

    monkeypatch.setattr(U, "run_command", failing)
    monkeypatch.setattr(U.shutil, "which", lambda _: None)
    monkeypatch.setattr(U, "_repo_root", lambda: None)
    assert U.detect_source() == "unknown"


# -- _repo_root ---------------------------------------------------------


def test_repo_root_from_syntropia_src_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo = tmp_path / "my-syntropia"
    repo.mkdir()
    (repo / ".git").mkdir()
    monkeypatch.setenv("SYNTROPIA_SRC", str(repo))
    assert U._repo_root() == repo


def test_repo_root_from_default_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    home = tmp_path / "home"
    home.mkdir()
    repo = home / "syntropia"
    repo.mkdir()
    (repo / ".git").mkdir()
    monkeypatch.setattr(U.Path, "home", lambda: home)
    monkeypatch.delenv("SYNTROPIA_SRC", raising=False)
    assert U._repo_root() == repo


def test_repo_root_returns_none_when_no_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.delenv("SYNTROPIA_SRC", raising=False)
    monkeypatch.setattr(U.Path, "home", lambda: tmp_path)
    # The heuristic walks up from __file__; we're inside the real repo, so
    # monkeypatch the __file__ location to point at the empty tmp_path.
    monkeypatch.setattr(U, "__file__", str(tmp_path / "nowhere" / "update.py"))
    assert U._repo_root() is None


# -- pull_git -----------------------------------------------------------


def test_pull_git_already_up_to_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()

    calls: list = []

    def fake_run(cmd: list, cwd=None) -> FakeResult:
        calls.append(cmd)
        if cmd[:2] == ["git", "rev-parse"]:
            return FakeResult(0, stdout="abc123\n")
        return FakeResult(0, stdout="Already up to date.\n")

    monkeypatch.setattr(U, "run_command", fake_run)
    updated, msg = U.pull_git(repo)
    assert not updated
    assert "up to date" in msg


def test_pull_git_has_updates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()

    rev_calls = iter(["abc123\n", "def456\n"])

    def fake_run(cmd: list, cwd=None) -> FakeResult:
        if cmd[:2] == ["git", "rev-parse"]:
            return FakeResult(0, stdout=next(rev_calls))
        if cmd[:2] == ["git", "log"]:
            return FakeResult(0, stdout="def456 new feature\nabc123 old\n")
        return FakeResult(0)

    monkeypatch.setattr(U, "run_command", fake_run)
    updated, msg = U.pull_git(repo)
    assert updated
    assert "def456" in msg


def test_pull_git_raises_when_not_a_repo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    not_repo = tmp_path / "not-repo"
    not_repo.mkdir()
    with pytest.raises(U.UpdateError, match="not a git"):
        U.pull_git(not_repo)


# -- pull_brews ---------------------------------------------------------


def test_pull_brews_no_registry_cloned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(U.Path, "home", lambda: tmp_path)
    updated, msg = U.pull_brews()
    assert not updated
    assert "not cloned" in msg


# -- changelog ----------------------------------------------------------


def test_changelog_returns_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()

    def fake_run(cmd: list, cwd=None) -> FakeResult:
        return FakeResult(0, stdout="1 commit\n2 commit\n3 commit\n")

    monkeypatch.setattr(U, "run_command", fake_run)
    log = U.changelog(repo, n=3)
    assert "1 commit" in log


def test_changelog_empty_for_non_repo(tmp_path: Path):
    assert U.changelog(tmp_path) == ""


# -- run_update ---------------------------------------------------------


def test_run_update_check_aur_does_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Check mode with AUR source: prints advice, no side effects."""
    monkeypatch.setattr(U, "detect_source", lambda: "aur")
    monkeypatch.setattr(U, "_repo_root", lambda: None)
    monkeypatch.setattr(U, "pull_brews", lambda: (False, "not cloned"))
    # Must not raise — check mode is read-only.
    U.run_update(check=True)


def test_run_update_unknown_prints_advice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(U, "detect_source", lambda: "unknown")
    monkeypatch.setattr(U, "pull_brews", lambda: (False, "not cloned"))
    U.run_update(check=True)  # should not raise


def test_run_update_git_no_changes_skips_transform(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(U, "detect_source", lambda: "git")
    monkeypatch.setattr(
        U, "_repo_root", lambda: tmp_path / "fake-repo"
    )
    monkeypatch.setattr(U, "pull_git", lambda _: (False, "already up to date"))
    monkeypatch.setattr(U, "pull_brews", lambda: (False, "already up to date"))
    # Should not raise — no transform call needed when nothing updated.
    U.run_update(check=False)
