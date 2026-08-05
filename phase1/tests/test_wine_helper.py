"""Tests for syntropia.wine_helper — the Wine/yabridge install engine."""

from pathlib import Path

import pytest

from syntropia import wine_helper as WH
from syntropia.brew import parse_brew

SERUM_MANIFEST = {
    "brew": {
        "name": "Xfer Serum VST3",
        "version": "1.368",
        "category": "vst3_synth",
        "maintainer": "Syntropia Team",
    },
    "wine": {
        "version": "cachyos-wine",
        "prefix": "~/.local/share/syntropia/prefixes/serum",
        "arch": "win64",
        "overrides": {"d2d1": "disabled", "gdiplus": "native"},
    },
    "winetricks": {"packages": ["gdiplus", "corefonts"]},
    "yabridge": {"enabled": True, "plugin_dirs": ["~/.vst3/Syntropia"]},
    "environment": {"WINEDLLOVERRIDES": "winemenubuilder.exe=d"},
    "install": {"commands": ["wine /tmp/Serum_Setup.exe /S"]},
}


class FakeResult:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def make_brew() -> object:
    return parse_brew(SERUM_MANIFEST, "serum.brew")


def make_installer(tmp_path: Path, *, dry_run: bool = False) -> WH.WineInstaller:
    return WH.WineInstaller(make_brew(), dry_run=dry_run, home=tmp_path)


# --- environment building ----------------------------------------------


def test_env_sets_prefix_and_arch(tmp_path: Path):
    installer = make_installer(tmp_path)
    env = installer.build_env()
    assert env["WINEPREFIX"] == str(installer.prefix)
    assert env["WINEARCH"] == "win64"


def test_env_merges_overrides_and_environment(tmp_path: Path):
    installer = make_installer(tmp_path)
    env = installer.build_env()
    dll = env["WINEDLLOVERRIDES"]
    assert "d2d1=disabled" in dll
    assert "gdiplus=native" in dll
    assert "winemenubuilder.exe=d" in dll


def test_env_applies_environment_section(tmp_path: Path):
    manifest = dict(SERUM_MANIFEST)
    manifest["environment"] = {"FOO": "bar", "LANG": "en_US.UTF-8"}
    installer = WH.WineInstaller(parse_brew(manifest, "x.brew"), home=tmp_path)
    env = installer.build_env()
    assert env["FOO"] == "bar"
    assert env["LANG"] == "en_US.UTF-8"


def test_expand_path_home_and_var(tmp_path: Path):
    assert WH.expand_path("~/.vst3/Syntropia", tmp_path) == tmp_path / ".vst3" / "Syntropia"
    # unset vars pass through, then anchor to home
    assert WH.expand_path("$WINEPREFIX/drive_c", tmp_path) == tmp_path / "$WINEPREFIX" / "drive_c"
    # relative paths anchor to home
    assert WH.expand_path("prefixes/vital", tmp_path) == tmp_path / "prefixes" / "vital"


# --- prefix -------------------------------------------------------------


def test_prefix_path_expanded(tmp_path: Path):
    installer = make_installer(tmp_path)
    assert str(installer.prefix).startswith(str(tmp_path))


def test_prefix_provision_detection(tmp_path: Path):
    installer = make_installer(tmp_path)
    assert not installer.prefix_is_provisioned()
    installer.prefix.mkdir(parents=True)
    (installer.prefix / "system.reg").write_text("", encoding="utf-8")
    assert installer.prefix_is_provisioned()


# --- toolchain ----------------------------------------------------------


def test_toolchain_missing_detected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(WH.shutil, "which", lambda cmd: None)
    installer = make_installer(tmp_path)
    assert installer.toolchain_missing() == list(WH.TOOLCHAIN)


def test_toolchain_all_present(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(WH.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    installer = make_installer(tmp_path)
    assert installer.toolchain_missing() == []


def test_step_toolchain_raises_when_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(WH.shutil, "which", lambda cmd: None)
    installer = make_installer(tmp_path)
    with pytest.raises(WH.WineHelperError, match="transform"):
        installer.step_toolchain()


# --- dry-run safety -----------------------------------------------------


def test_dry_run_runs_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls: list = []
    monkeypatch.setattr(WH, "run_command", lambda cmd, env=None: (calls.append(cmd), FakeResult(0))[1])
    monkeypatch.setattr(WH.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    installer = make_installer(tmp_path, dry_run=True)
    installer.run_all()
    assert calls == []  # --check may never execute anything
    assert not installer.prefix.exists()


# --- real run ordering --------------------------------------------------


def test_run_all_orders_steps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls: list = []
    monkeypatch.setattr(WH, "run_command", lambda cmd, env=None: (calls.append(cmd), FakeResult(0))[1])
    monkeypatch.setattr(WH.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    installer = make_installer(tmp_path, dry_run=False)
    installer.run_all()
    names = [c[0] for c in calls]
    assert "wineboot" in names
    assert names.index("wineboot") < names.index("winetricks")
    assert names.index("winetricks") < names.index("yabridgectl")
    assert names.index("yabridgectl") < names.index("bash")


def test_yabridge_plugin_dir_expands_tilde(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls: list = []
    monkeypatch.setattr(WH, "run_command", lambda cmd, env=None: (calls.append(cmd), FakeResult(0))[1])
    monkeypatch.setattr(WH.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    installer = make_installer(tmp_path, dry_run=False)
    installer.step_yabridge()
    add_calls = [c for c in calls if c[0] == "yabridgectl" and c[1] == "add"]
    assert add_calls, "yabridgectl add should have been invoked"
    # the plugin dir must be resolved against the injected home, not a literal ~
    assert add_calls[0][2] == str(tmp_path / ".vst3" / "Syntropia")


def test_install_command_failure_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def flaky(cmd: list, env=None) -> FakeResult:
        if cmd[0] == "bash":
            return FakeResult(1, stderr="boom")
        return FakeResult(0)
    monkeypatch.setattr(WH, "run_command", flaky)
    monkeypatch.setattr(WH.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    installer = make_installer(tmp_path, dry_run=False)
    with pytest.raises(WH.WineHelperError, match="install command failed"):
        installer.run_all()
