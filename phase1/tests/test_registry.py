"""Tests for syntropia.registry — the AUR-style submit flow."""

from pathlib import Path

import pytest

from syntropia_brews import registry as REG
from syntropia_brews.registry import RegistryError


class FakeResult:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def make_brew(tmp_path: Path, name: str = "surge.brew") -> Path:
    path = tmp_path / "reg" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "[brew]\nname = \"Surge XT\"\nversion = \"1.3.4\"\ncategory = \"vst\"\nmaintainer = \"T\"\n\n"
        "[wine]\nversion = \"w\"\nprefix = \"~/p\"\narch = \"win64\"\n\n"
        "[install]\ncommands = [\"echo hi\"]\n",
        encoding="utf-8",
    )
    return path


def make_flow_fake(tmp_path: Path, calls: list, *, head_has_brew: bool = False):
    """Fake run_command for the happy-path submit flow."""
    def fake(cmd: list, cwd: Path | None = None) -> FakeResult:
        calls.append(cmd)
        joined = " ".join(cmd)
        if "rev-parse --show-toplevel" in joined:
            return FakeResult(0, str(tmp_path))
        if "remote get-url origin" in joined:
            return FakeResult(0, REG.SHARED_REGISTRY_URL)
        if "rev-parse --verify" in joined:
            return FakeResult(1)  # feature branch does not exist yet
        if "cat-file" in joined:
            return FakeResult(0 if head_has_brew else 1)  # on HEAD?
        if "gh pr create" in joined:
            return FakeResult(0, "https://github.com/r4-ndm/syntropia-brews/pull/1")
        return FakeResult(0)
    return fake


def test_submit_flow_opens_pr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls: list[list] = []
    brew_path = make_brew(tmp_path)
    reg = tmp_path / "reg"

    monkeypatch.setattr(REG, "run_command", make_flow_fake(tmp_path, calls))
    monkeypatch.setattr(REG.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")

    url = REG.submit_brew(brew_path, reg)

    flat = [" ".join(c) for c in calls]
    assert any("checkout -b brews/surge" in c for c in flat)
    assert any("add -- reg/surge.brew" in c for c in flat)
    # Pathspec-limited commit: only the brew is ever committed.
    assert any("commit -m brews: add surge -- reg/surge.brew" in c for c in flat)
    assert any("push -u origin brews/surge" in c for c in flat)
    assert any("gh pr create --base main --head brews/surge" in c for c in flat)
    assert any("checkout main" in c for c in flat)  # restored to base after the PR
    assert any("branch -D brews/surge" in c for c in flat)  # local branch cleaned up
    assert url == "https://github.com/r4-ndm/syntropia-brews/pull/1"


def test_submit_update_detection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls: list[list] = []
    brew_path = make_brew(tmp_path)
    reg = tmp_path / "reg"

    monkeypatch.setattr(
        REG, "run_command", make_flow_fake(tmp_path, calls, head_has_brew=True)
    )
    monkeypatch.setattr(REG.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")

    REG.submit_brew(brew_path, reg)

    flat = [" ".join(c) for c in calls]
    assert any("commit -m brews: update surge -- reg/surge.brew" in c for c in flat)
    assert any("gh pr create --base main --head brews/surge" in c for c in flat)


def test_submit_requires_git_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        REG, "run_command", lambda cmd, cwd=None: FakeResult(128, stderr="not a git repository")
    )
    monkeypatch.setattr(REG.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    with pytest.raises(RegistryError, match="not inside a git repository"):
        REG.submit_brew(tmp_path / "nope.brew", tmp_path)


def test_submit_requires_gh(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        REG, "run_command", lambda cmd, cwd=None: FakeResult(0, str(tmp_path))
        if "show-toplevel" in " ".join(cmd) else FakeResult(0)
    )
    monkeypatch.setattr(REG.shutil, "which", lambda cmd: None)
    with pytest.raises(RegistryError, match="gh.* not installed"):
        REG.submit_brew(tmp_path / "nope.brew", tmp_path)


def test_submit_branch_conflict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    brew_path = make_brew(tmp_path)
    reg = tmp_path / "reg"

    def fake(cmd: list, cwd: Path | None = None) -> FakeResult:
        joined = " ".join(cmd)
        if "rev-parse --verify" in joined:
            return FakeResult(0)  # branch exists
        if "show-toplevel" in joined:
            return FakeResult(0, str(tmp_path))
        return FakeResult(0)

    monkeypatch.setattr(REG, "run_command", fake)
    monkeypatch.setattr(REG.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    with pytest.raises(RegistryError, match="already exists"):
        REG.submit_brew(brew_path, reg)


def test_submit_commit_failure_aborts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    brew_path = make_brew(tmp_path)
    reg = tmp_path / "reg"
    calls: list[list] = []

    def fake(cmd: list, cwd: Path | None = None) -> FakeResult:
        calls.append(cmd)
        joined = " ".join(cmd)
        if "show-toplevel" in joined:
            return FakeResult(0, str(tmp_path))
        if "rev-parse --verify" in joined:
            return FakeResult(1)
        if cmd[0] == "git" and "commit" in cmd and "-m" in cmd:
            return FakeResult(1, stderr="nothing to commit")
        return FakeResult(0)

    monkeypatch.setattr(REG, "run_command", fake)
    monkeypatch.setattr(REG.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    with pytest.raises(RegistryError, match="commit reg/surge.brew: nothing to commit"):
        REG.submit_brew(brew_path, reg)


def test_submit_refuses_brew_outside_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    outside = tmp_path / "elsewhere.brew"
    outside.write_text("x", encoding="utf-8")
    reg = tmp_path / "reg"
    fake_root = tmp_path / "some-other-clone"  # brew lives outside this root
    monkeypatch.setattr(
        REG, "run_command", lambda cmd, cwd=None: FakeResult(0, str(fake_root))
        if "show-toplevel" in " ".join(cmd) else FakeResult(0)
    )
    monkeypatch.setattr(REG.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    with pytest.raises(RegistryError, match="outside the registry repository"):
        REG.submit_brew(outside, reg)


def test_submit_requires_origin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        REG, "run_command", lambda cmd, cwd=None: FakeResult(0, str(tmp_path))
        if "show-toplevel" in " ".join(cmd) else FakeResult(128, stderr="no remote")
    )
    monkeypatch.setattr(REG.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    with pytest.raises(RegistryError, match="no 'origin' remote"):
        REG.submit_brew(tmp_path / "nope.brew", tmp_path)


def test_submit_warns_on_unexpected_origin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
):
    calls: list[list] = []
    brew_path = make_brew(tmp_path)
    reg = tmp_path / "reg"

    def fake(cmd: list, cwd: Path | None = None) -> FakeResult:
        calls.append(cmd)
        joined = " ".join(cmd)
        if "show-toplevel" in joined:
            return FakeResult(0, str(tmp_path))
        if "remote get-url origin" in joined:
            return FakeResult(0, "https://github.com/other/not-the-registry.git")
        if "rev-parse --verify" in joined:
            return FakeResult(1)
        if "gh pr create" in joined:
            return FakeResult(0, "https://pr")
        return FakeResult(0)

    monkeypatch.setattr(REG, "run_command", fake)
    monkeypatch.setattr(REG.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    REG.submit_brew(brew_path, reg)
    assert "warning: registry origin" in capsys.readouterr().out


def test_submit_push_failure_aborts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    brew_path = make_brew(tmp_path)
    reg = tmp_path / "reg"

    def fake(cmd: list, cwd: Path | None = None) -> FakeResult:
        joined = " ".join(cmd)
        if "show-toplevel" in joined:
            return FakeResult(0, str(tmp_path))
        if "remote get-url origin" in joined:
            return FakeResult(0, REG.SHARED_REGISTRY_URL)
        if "rev-parse --verify" in joined:
            return FakeResult(1)
        if cmd[0] == "git" and len(cmd) > 3 and cmd[3] == "push":
            return FakeResult(1, stderr="failed to push")
        return FakeResult(0)

    monkeypatch.setattr(REG, "run_command", fake)
    monkeypatch.setattr(REG.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    with pytest.raises(RegistryError, match="push branch 'brews/surge': failed to push"):
        REG.submit_brew(brew_path, reg)


def test_submit_gh_failure_aborts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    brew_path = make_brew(tmp_path)
    reg = tmp_path / "reg"

    def fake(cmd: list, cwd: Path | None = None) -> FakeResult:
        joined = " ".join(cmd)
        if "show-toplevel" in joined:
            return FakeResult(0, str(tmp_path))
        if "remote get-url origin" in joined:
            return FakeResult(0, REG.SHARED_REGISTRY_URL)
        if "rev-parse --verify" in joined:
            return FakeResult(1)
        if "gh pr create" in joined:
            return FakeResult(1, stderr="GraphQL error")
        return FakeResult(0)

    monkeypatch.setattr(REG, "run_command", fake)
    monkeypatch.setattr(REG.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    with pytest.raises(RegistryError, match="open pull request: GraphQL error"):
        REG.submit_brew(brew_path, reg)
