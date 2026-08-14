"""Tests for syntropia.wine_helper — the Wine/yabridge install engine."""

from pathlib import Path

import pytest

from syntropia_brews import wine_helper as WH
from syntropia_brews.brew import parse_brew

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
    "yabridge": {"enabled": True, "plugin_dirs": ["~/VST3"]},
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
    assert WH.expand_path("~/VST3", tmp_path) == tmp_path / "VST3"
    # unset vars pass through, then anchor to home
    assert WH.expand_path("$WINEPREFIX/drive_c", tmp_path) == tmp_path / "$WINEPREFIX" / "drive_c"
    # relative paths anchor to home
    assert WH.expand_path("prefixes/vital", tmp_path) == tmp_path / "prefixes" / "vital"


# --- prefix -------------------------------------------------------------


def _fake_proc(tmp_path: Path, proc_root: Path, pid: int, cmdline: list[str], wineprefix: str | None):
    """Create a fake /proc entry for a process."""
    pdir = proc_root / str(pid)
    pdir.mkdir(parents=True)
    (pdir / "cmdline").write_bytes("\0".join(cmdline).encode())
    if wineprefix is not None:
        env = f"WINEPREFIX={wineprefix}\0PATH=/usr/bin\0".encode()
    else:
        env = b"PATH=/usr/bin\0"
    (pdir / "environ").write_bytes(env)


def test_prefix_holders_empty_when_nothing_running(tmp_path: Path):
    installer = make_installer(tmp_path)
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    # a process with no WINEPREFIX must not count
    _fake_proc(tmp_path, proc_root, 100, ["bash"], None)
    assert installer._prefix_holders(proc_root) == []


def test_prefix_holders_detects_wineserver_on_this_prefix(tmp_path: Path):
    installer = make_installer(tmp_path)
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    _fake_proc(tmp_path, proc_root, 200, ["/usr/bin/wineserver"], str(installer.prefix))
    assert installer._prefix_holders(proc_root) == ["wineserver"]


def test_prefix_holders_ignores_other_prefixes(tmp_path: Path):
    installer = make_installer(tmp_path)
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    _fake_proc(tmp_path, proc_root, 300, ["/usr/bin/wineserver"], str(tmp_path / "other"))
    assert installer._prefix_holders(proc_root) == []


def test_prefix_holders_names_running_app(tmp_path: Path):
    installer = make_installer(tmp_path)
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    _fake_proc(
        tmp_path,
        proc_root,
        400,
        ["C:\\Program Files\\Ableton\\Ableton Live 12 Suite.exe"],
        str(installer.prefix),
    )
    assert installer._prefix_holders(proc_root) == ["Ableton Live 12 Suite.exe"]


def test_step_prefix_fails_fast_when_prefix_in_use(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A real install must refuse when an app holds the prefix, so winetricks
    can't hang on its final `wineserver -w`."""
    installer = make_installer(tmp_path, dry_run=False)
    monkeypatch.setattr(installer, "_prefix_holders", lambda proc_root: ["Ableton Live 12 Suite.exe"])
    with pytest.raises(WH.WineHelperError, match="in use"):
        installer.step_prefix()


def test_step_prefix_dry_run_warns_not_fails_when_in_use(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    installer = make_installer(tmp_path, dry_run=True)
    monkeypatch.setattr(installer, "_prefix_holders", lambda proc_root: ["wineserver"])
    installer.step_prefix()  # must not raise in dry-run
    assert installer._progress_detail == "in use: wineserver"


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
    assert add_calls[0][2] == str(tmp_path / "VST3")


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


def test_post_install_yabridge_sync_bridges_after_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """yabridgectl must re-sync after the install commands, so a freshly
    copied VST3 actually gets bridged (the pre-install sync alone would
    leave it unbridged until a manual sync)."""
    calls: list = []
    monkeypatch.setattr(WH, "run_command", lambda cmd, env=None: (calls.append(cmd), FakeResult(0))[1])
    monkeypatch.setattr(WH.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    installer = make_installer(tmp_path, dry_run=False)
    installer.run_all()
    sync_calls = [c for c in calls if c == ["yabridgectl", "sync"]]
    assert len(sync_calls) == 1, "sync must run exactly once — after the install"
    # the sync comes after the install (bash) commands, so the VST3 is bridged
    sync_idx = next(i for i, c in enumerate(calls) if c == ["yabridgectl", "sync"])
    bash_idx = next(i for i, c in enumerate(calls) if c[0] == "bash")
    assert sync_idx > bash_idx
    assert calls[-1] == ["yabridgectl", "sync"]


def test_dry_run_plans_post_install_sync_without_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls: list = []
    monkeypatch.setattr(WH, "run_command", lambda cmd, env=None: (calls.append(cmd), FakeResult(0))[1])
    monkeypatch.setattr(WH.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    installer = make_installer(tmp_path, dry_run=True)
    installer.run_all()
    assert calls == []  # dry-run never syncs


# --- pipeline definition ------------------------------------------------


def test_step_labels_and_methods_stay_in_sync():
    """STEP_LABELS (shown by the CLI) and _STEP_METHODS (run by run_all)
    must name the same steps — a step added to one but not the other
    silently breaks the install pipeline."""
    assert set(WH._STEP_METHODS) == {label for label, _desc in WH.STEP_LABELS}
    # every mapped method must exist on the installer
    installer = make_installer(Path("/tmp/unused-home"))
    for label, method_name in WH._STEP_METHODS.items():
        assert hasattr(installer, method_name), f"{label} -> {method_name} missing"


# --- vendor data linking ------------------------------------------------


def _manifest_with_vendor(vendors: list[str]) -> dict:
    manifest = dict(SERUM_MANIFEST)
    manifest["vendor_data"] = {"vendors": vendors}
    return manifest


def test_step_vendor_data_skips_when_none_declared(tmp_path: Path):
    installer = make_installer(tmp_path)  # serum manifest: no [vendor_data]
    installer.step_vendor_data()  # must not raise
    assert installer._progress_detail == "none declared"


def test_step_vendor_data_links_into_own_prefix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    installer = WH.WineInstaller(
        parse_brew(_manifest_with_vendor(["Arturia"]), "x.brew"), home=tmp_path
    )
    seen: dict = {}

    def fake_link(vendor, source_prefix, target_prefixes=None, home=None, dry_run=False):
        from syntropia_brews.vendor import LinkResult

        seen.update(
            vendor=vendor,
            source=Path(source_prefix),
            targets=target_prefixes,
            dry_run=dry_run,
        )
        return LinkResult(
            vendor,
            Path(source_prefix),
            target_prefixes or [],
            data_dirs=[(Path(source_prefix) / "d", installer.prefix / "d")],
            registry_keys=[(installer.prefix, r"Software\Arturia\X", "installdir", r"C:\X")],
            dry_run=dry_run,
        )

    monkeypatch.setattr("syntropia_brews.wine_helper.link_vendor_data", fake_link)
    installer.step_vendor_data()

    assert seen["vendor"] == "Arturia"
    # default source ~/.wine anchors to the injected home, not the real one
    assert seen["source"] == tmp_path / ".wine"
    assert seen["targets"] == [installer.prefix]
    assert seen["dry_run"] is False


def test_step_vendor_data_dry_run_plans_without_linking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    installer = WH.WineInstaller(
        parse_brew(_manifest_with_vendor(["Arturia"]), "x.brew"), dry_run=True, home=tmp_path
    )
    seen: dict = {}

    def fake_link(vendor, source_prefix, target_prefixes=None, home=None, dry_run=False):
        from syntropia_brews.vendor import LinkResult

        seen["dry_run"] = dry_run
        return LinkResult(vendor, Path(source_prefix), target_prefixes or [], dry_run=dry_run)

    monkeypatch.setattr("syntropia_brews.wine_helper.link_vendor_data", fake_link)
    installer.step_vendor_data()

    assert seen["dry_run"] is True


def test_step_vendor_data_missing_vendor_warns_not_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A vendor absent from the source prefix must warn, not abort the install."""
    installer = WH.WineInstaller(
        parse_brew(_manifest_with_vendor(["Arturia"]), "x.brew"), home=tmp_path
    )
    from syntropia_brews.vendor import VendorError

    def fake_link(vendor, source_prefix, target_prefixes=None, home=None, dry_run=False):
        raise VendorError("no 'Arturia' data or registry keys found")

    monkeypatch.setattr("syntropia_brews.wine_helper.link_vendor_data", fake_link)
    installer.step_vendor_data()  # must not raise
