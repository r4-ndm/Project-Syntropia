"""Tests for syntropia.update — the update subcommand."""

from pathlib import Path

import pytest

from syntropia_transform import update as U


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


# -- _update_via_pacman ----------------------------------------------


def test_update_via_pacman_check(capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        U.shutil, "which", lambda name: f"/usr/bin/{name}" if name in ("paru", "yay") else None
    )
    U._update_via_pacman(check=True)
    out = capsys.readouterr().out
    assert "paru -Syu" in out
    assert "would run" in out


def test_update_via_pacman_prefers_paru(monkeypatch: pytest.MonkeyPatch):
    calls: list = []
    monkeypatch.setattr(
        U.shutil, "which", lambda name: f"/usr/bin/{name}" if name in ("paru", "yay") else None
    )

    def fake_run(cmd: list) -> FakeResult:
        calls.append(cmd)
        return FakeResult(0)

    monkeypatch.setattr(U.subprocess, "run", fake_run)
    U._update_via_pacman()
    assert calls == [["paru", "-Syu"]]


def test_update_via_pacman_falls_back_to_yay(monkeypatch: pytest.MonkeyPatch):
    calls: list = []
    monkeypatch.setattr(
        U.shutil, "which", lambda name: "/usr/bin/yay" if name == "yay" else None
    )

    def fake_run(cmd: list) -> FakeResult:
        calls.append(cmd)
        return FakeResult(0)

    monkeypatch.setattr(U.subprocess, "run", fake_run)
    U._update_via_pacman()
    assert calls == [["yay", "-Syu"]]


def test_update_via_pacman_no_helper_prints_advice(
    capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(U.shutil, "which", lambda _: None)
    U._update_via_pacman()
    out = capsys.readouterr().out
    assert "no AUR helper found" in out


def test_update_via_pacman_nonzero_continues(
    capsys: pytest.CaptureFixture, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        U.shutil, "which", lambda name: f"/usr/bin/{name}" if name in ("paru", "yay") else None
    )
    monkeypatch.setattr(U.subprocess, "run", lambda cmd: FakeResult(1))
    # Must not raise — an aborted/failed system update shouldn't kill the flow.
    U._update_via_pacman()
    out = capsys.readouterr().out
    assert "continuing with brews + transform" in out


# -- _rerun_transform -------------------------------------------------


def test_rerun_transform_check_prints_only(capsys: pytest.CaptureFixture):
    """Check mode prints the sudo command and never runs anything."""
    U._rerun_transform(check=True)
    out = capsys.readouterr().out
    assert "sudo syntropia transform --yes" in out


def test_rerun_transform_as_root_runs_in_process(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(U.os, "geteuid", lambda: 0)
    calls: list = []

    def fake_run_transform(**kwargs) -> None:
        calls.append(kwargs)

    monkeypatch.setattr("syntropia_transform.transform.run_transform", fake_run_transform)
    U._rerun_transform()
    assert calls == [
        {"check": False, "yes": True, "branding_dir": "/usr/share/syntropia/branding"}
    ]


def test_rerun_transform_sudo_runs_binary(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(U.os, "geteuid", lambda: 1000)

    def which(name: str) -> str | None:
        return "/usr/bin/syntropia" if name == "syntropia" else "/usr/bin/sudo"

    monkeypatch.setattr(U.shutil, "which", which)
    calls: list = []

    def fake_subprocess_run(cmd: list) -> FakeResult:
        calls.append(cmd)
        return FakeResult(0)

    monkeypatch.setattr(U.subprocess, "run", fake_subprocess_run)
    U._rerun_transform()
    assert calls == [["sudo", "/usr/bin/syntropia", "transform", "--yes"]]


def test_rerun_transform_sudo_failure_raises(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(U.os, "geteuid", lambda: 1000)

    def which(name: str) -> str | None:
        return "/usr/bin/syntropia" if name == "syntropia" else "/usr/bin/sudo"

    monkeypatch.setattr(U.shutil, "which", which)

    class FailingResult:
        returncode = 1

    monkeypatch.setattr(U.subprocess, "run", lambda cmd: FailingResult())
    with pytest.raises(U.UpdateError, match="transform re-run failed"):
        U._rerun_transform()


def test_rerun_transform_without_sudo_raises(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(U.os, "geteuid", lambda: 1000)

    def which(name: str) -> str | None:
        return "/usr/bin/syntropia" if name == "syntropia" else None

    monkeypatch.setattr(U.shutil, "which", which)
    with pytest.raises(U.UpdateError, match="sudo is not available"):
        U._rerun_transform()


def test_rerun_transform_without_binary_raises(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(U.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(U.shutil, "which", lambda _: None)
    with pytest.raises(U.UpdateError, match="cannot find the syntropia binary"):
        U._rerun_transform()


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


def test_run_update_skips_brews_when_not_installed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture,
):
    """A rebrand-only install has no `syntropia_brews` — the registry pull
    must be skipped instead of hinting `syntropia save` (a brews command)."""
    monkeypatch.setattr(U, "detect_source", lambda: "aur")
    monkeypatch.setattr(U.importlib.util, "find_spec", lambda name: None)
    called: list = []
    monkeypatch.setattr(U, "pull_brews", lambda: called.append(1) or (False, "x"))
    monkeypatch.setattr(U, "_update_via_pacman", lambda check=False: None)
    monkeypatch.setattr(U, "_rerun_transform", lambda check=False: None)
    U.run_update(check=False)
    assert called == []
    assert "syntropia-brews not installed" in capsys.readouterr().out


def test_run_update_aur_runs_pacman_then_transform(
    monkeypatch: pytest.MonkeyPatch,
):
    """AUR source: paru step runs first, then brews, then the transform."""
    monkeypatch.setattr(U, "detect_source", lambda: "aur")
    monkeypatch.setattr(U, "pull_brews", lambda: (False, "already up to date"))
    calls: list = []
    monkeypatch.setattr(
        U, "_update_via_pacman", lambda check=False: calls.append(("pacman", check))
    )
    monkeypatch.setattr(
        U, "_rerun_transform", lambda check=False: calls.append(("transform", check))
    )
    U.run_update(check=False)
    assert calls == [("pacman", False), ("transform", False)]


def test_run_update_aur_check_never_runs_paru(
    monkeypatch: pytest.MonkeyPatch,
):
    """Check mode with AUR source prints the plan and runs nothing."""
    monkeypatch.setattr(U, "detect_source", lambda: "aur")
    monkeypatch.setattr(U, "pull_brews", lambda: (False, "not cloned"))
    calls: list = []
    monkeypatch.setattr(
        U, "_update_via_pacman", lambda check=False: calls.append(("pacman", check))
    )
    monkeypatch.setattr(
        U, "_rerun_transform", lambda check=False: calls.append(("transform", check))
    )
    U.run_update(check=True)
    assert calls == [("pacman", True), ("transform", True)]


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
