"""Tests for syntropia.transform — the system transformation module."""

import os
from pathlib import Path

import pytest

from syntropia import transform as T


class FakeResult:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def make_paths(tmp_path: Path) -> T.TransformPaths:
    return T.TransformPaths(
        home=tmp_path / "home",
        os_release=tmp_path / "etc" / "os-release",
        logo_dir=tmp_path / "usr-share" / "syntropia",
        usr_local_bin=tmp_path / "usr-local-bin",
    )


def make_transform(tmp_path: Path, *, dry_run: bool) -> T.Transform:
    return T.Transform(make_paths(tmp_path), dry_run=dry_run)


def noop_run(calls: list) -> callable:
    def _run(cmd: list) -> FakeResult:
        calls.append(cmd)
        return FakeResult(0)
    return _run


# --- dry-run safety -----------------------------------------------------


def test_check_mode_changes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls: list = []
    monkeypatch.setattr(T, "run_command", noop_run(calls))
    paths = make_paths(tmp_path)
    transform = T.Transform(paths, dry_run=True)
    transform.run_all()
    # nothing may have been created or written
    assert not paths.os_release.exists()
    assert not paths.logo_path.exists()
    assert not paths.bashrc.exists()
    assert not paths.zshrc.exists()
    assert not paths.pipewire_conf_dir.exists()
    assert not paths.fastfetch_dir.exists()
    assert not (paths.usr_local_bin / "syntropia").exists()
    # but package checks DID happen (read-only)
    assert any("pacman" in c and "-Q" in c for c in calls)
    assert transform.planned >= 1


def test_run_transform_check_is_safe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(T, "run_command", noop_run([]))
    monkeypatch.setattr(
        T.TransformPaths, "for_user", classmethod(lambda cls: make_paths(tmp_path))
    )
    T.run_transform(check=True, yes=False)  # --check must work even without --yes
    assert not (tmp_path / "home").exists()


# --- guards -------------------------------------------------------------


def test_real_run_refuses_without_yes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(T, "run_command", noop_run([]))
    monkeypatch.setattr(
        T.TransformPaths, "for_user", classmethod(lambda cls: make_paths(tmp_path))
    )
    with pytest.raises(T.TransformError, match="--yes"):
        T.run_transform(check=False, yes=False)


def test_real_run_requires_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(T, "run_command", noop_run([]))
    monkeypatch.setattr(
        T.TransformPaths, "for_user", classmethod(lambda cls: make_paths(tmp_path))
    )
    monkeypatch.setattr(os, "geteuid", lambda: 1000)  # not root
    with pytest.raises(T.TransformError, match="root"):
        T.run_transform(check=False, yes=True)


# --- idempotency --------------------------------------------------------


def test_shell_prompt_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(T, "run_command", noop_run([]))
    transform = make_transform(tmp_path, dry_run=False)
    transform.apply_shell_prompt()
    transform.apply_shell_prompt()
    bashrc = transform.paths.bashrc.read_text(encoding="utf-8")
    assert bashrc.count(T.SHELL_PROMPT_MARKER) == 1
    assert "PS1='😈 \\u@\\h \\W $ '" in bashrc
    zshrc = transform.paths.zshrc.read_text(encoding="utf-8")
    assert "PROMPT='😈 %n@%m %~ $ '" in zshrc


def test_os_release_backup_and_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(T, "run_command", noop_run([]))
    paths = make_paths(tmp_path)
    paths.os_release.parent.mkdir(parents=True)
    paths.os_release.write_text("NAME=\"CachyOS\"\n", encoding="utf-8")
    transform = T.Transform(paths, dry_run=False)
    transform.apply_os_release()
    transform.apply_os_release()
    assert "ID=syntropia" in paths.os_release.read_text(encoding="utf-8")
    backup = paths.os_release.with_name("os-release.syntropia.bak")
    assert backup.exists()
    assert "CachyOS" in backup.read_text(encoding="utf-8")


def test_pipewire_config_written(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(T, "run_command", noop_run([]))
    transform = make_transform(tmp_path, dry_run=False)
    transform.apply_pipewire()
    conf = (transform.paths.pipewire_conf_dir / "99-syntropia.conf").read_text(encoding="utf-8")
    assert f"default.clock.quantum = {T.PIPEWIRE_QUANTUM}" in conf


def test_directories_created(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(T, "run_command", noop_run([]))
    transform = make_transform(tmp_path, dry_run=False)
    transform.apply_directories()
    for rel in T.SYNTROPIA_DIRS_REL:
        assert (transform.paths.home / rel).is_dir()


# --- logo source -------------------------------------------------------


def test_logo_prefers_branding_dir_logo_txt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A logo.txt dropped in the asset-dir replaces the built-in art."""
    monkeypatch.setattr(T, "run_command", noop_run([]))
    paths = make_paths(tmp_path)
    branding = tmp_path / "branding"
    branding.mkdir(parents=True)
    (branding / "logo.txt").write_text("MY CUSTOM ART\n", encoding="utf-8")
    paths.branding_dir = branding
    transform = T.Transform(paths, dry_run=False)
    transform.apply_logo()
    assert paths.logo_path.read_text(encoding="utf-8") == "MY CUSTOM ART\n"


def test_logo_falls_back_to_builtin_without_asset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(T, "run_command", noop_run([]))
    transform = make_transform(tmp_path, dry_run=False)
    transform.apply_logo()
    assert paths_logo_equals_builtin(transform.paths)


def paths_logo_equals_builtin(paths: T.TransformPaths) -> bool:
    return paths.logo_path.read_text(encoding="utf-8") == T.LOGO_TEXT


def test_logo_dry_run_reports_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(T, "run_command", noop_run([]))
    paths = make_paths(tmp_path)
    branding = tmp_path / "branding"
    branding.mkdir(parents=True)
    (branding / "logo.txt").write_text("CUSTOM\n", encoding="utf-8")
    paths.branding_dir = branding
    transform = T.Transform(paths, dry_run=True)
    transform.apply_logo()
    assert not paths.logo_path.exists()  # dry-run writes nothing
    assert transform.planned == 1


# --- fastfetch color map ------------------------------------------------


def test_fastfetch_conf_without_colors_has_no_color_key():
    conf = T.build_fastfetch_conf(None)
    assert '"source": "/usr/share/syntropia/logo.txt"' in conf
    assert "color" not in conf


def test_fastfetch_conf_merges_color_map():
    conf = T.build_fastfetch_conf({"1": "#FF0000", "2": "#00FF00"})
    assert '"1": "#FF0000"' in conf
    assert '"2": "#00FF00"' in conf
    assert "color" in conf


def test_apply_fastfetch_reads_color_map_from_asset_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(T, "run_command", noop_run([]))
    paths = make_paths(tmp_path)
    branding = tmp_path / "branding"
    branding.mkdir(parents=True)
    (branding / "fastfetch-color.json").write_text(
        '{"1": "#123456"}\n', encoding="utf-8"
    )
    paths.branding_dir = branding
    transform = T.Transform(paths, dry_run=False)
    transform.apply_fastfetch()
    conf = (paths.fastfetch_dir / "config.jsonc").read_text(encoding="utf-8")
    assert '"1": "#123456"' in conf


def test_apply_fastfetch_rejects_bad_color_map(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(T, "run_command", noop_run([]))
    paths = make_paths(tmp_path)
    branding = tmp_path / "branding"
    branding.mkdir(parents=True)
    (branding / "fastfetch-color.json").write_text("not json", encoding="utf-8")
    paths.branding_dir = branding
    transform = T.Transform(paths, dry_run=False)
    with pytest.raises(T.TransformError, match="color map"):
        transform.apply_fastfetch()


# --- packages -----------------------------------------------------------


def test_missing_packages_detected(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(T, "run_command", lambda cmd: FakeResult(1 if "-Q" in cmd else 0))
    transform = T.Transform(make_paths(Path("/tmp")), dry_run=True)
    assert set(transform.missing_packages()) == set(T.AUDIO_PACKAGES)


def test_install_packages_dry_run_does_not_execute(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls: list = []
    monkeypatch.setattr(T, "run_command", noop_run(calls))
    transform = make_transform(tmp_path, dry_run=True)
    transform.apply_packages()
    assert not any("pacman" in c and "-S" in c for c in calls)


def test_install_packages_failure_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def failing(cmd: list) -> FakeResult:
        if "-Q" in cmd:
            return FakeResult(1)
        return FakeResult(1, stderr="could not find package")  # pacman -S fails
    monkeypatch.setattr(T, "run_command", failing)
    transform = make_transform(tmp_path, dry_run=False)
    with pytest.raises(T.TransformError, match="package install failed"):
        transform.apply_packages()
