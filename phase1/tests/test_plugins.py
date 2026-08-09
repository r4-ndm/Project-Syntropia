"""Tests for syntropia.plugins — the drop-folder VST3 workflow."""

from pathlib import Path

import pytest

from syntropia import plugins as PL


class FakeResult:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# --- folder resolution --------------------------------------------------


def test_drop_folder_defaults_to_home_vst3(tmp_path: Path):
    assert PL.drop_folder(tmp_path) == tmp_path / "VST3"


def test_drop_folder_uses_default_constant():
    assert PL.DEFAULT_PLUGIN_DIR == "~/VST3"


def test_ensure_drop_folder_creates(tmp_path: Path):
    target = tmp_path / "VST3"
    assert not target.exists()
    result = PL.ensure_drop_folder(target)
    assert target.is_dir()
    assert result == target


# --- plugin discovery ---------------------------------------------------


def test_find_plugins_flat_vst3_and_bundle(tmp_path: Path):
    (tmp_path / "FlatCRMBL.vst3").write_bytes(b"dll-bytes")
    bundle = tmp_path / "Serum.vst3"
    (bundle / "Contents" / "x86_64-win").mkdir(parents=True)
    (bundle / "Contents" / "x86_64-win" / "Serum.vst3").write_bytes(b"dll")
    (tmp_path / "notes.txt").write_text("ignore me", encoding="utf-8")

    found = PL.find_plugins(tmp_path)
    names = sorted(p.name for p in found)
    assert names == ["FlatCRMBL.vst3", "Serum.vst3"]


def test_find_plugins_includes_dll_and_clap(tmp_path: Path):
    (tmp_path / "old.vst.dll").write_bytes(b"x")
    (tmp_path / "synth.clap").write_bytes(b"x")
    found = PL.find_plugins(tmp_path)
    assert sorted(p.suffix for p in found) == [".clap", ".dll"]


def test_find_plugins_empty_dir(tmp_path: Path):
    assert PL.find_plugins(tmp_path) == []


# --- sync flow ----------------------------------------------------------


def test_sync_dry_run_creates_folder_but_runs_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls: list = []
    monkeypatch.setattr(PL, "run_command", lambda cmd, env=None: (calls.append(cmd), FakeResult(0))[1])
    monkeypatch.setattr(PL.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")

    result = PL.sync_plugins(drop_dir=tmp_path / "VST3", home=tmp_path, dry_run=True)

    assert (tmp_path / "VST3").is_dir()  # folder still gets created for discovery
    assert calls == []  # dry-run never runs yabridgectl
    assert result.dry_run
    assert result.plugins_found == []


def test_sync_requires_yabridgectl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(PL.shutil, "which", lambda cmd: None)
    with pytest.raises(PL.PluginsError, match="transform"):
        PL.sync_plugins(drop_dir=tmp_path / "VST3", home=tmp_path, dry_run=False)


def test_sync_registers_then_syncs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls: list = []
    monkeypatch.setattr(PL, "run_command", lambda cmd, env=None: (calls.append(cmd), FakeResult(0))[1])
    monkeypatch.setattr(PL.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")

    (tmp_path / "VST3").mkdir(parents=True)
    (tmp_path / "VST3" / "FlatCRMBL.vst3").write_bytes(b"x")

    result = PL.sync_plugins(drop_dir=tmp_path / "VST3", home=tmp_path)

    add_calls = [c for c in calls if c[:2] == ["yabridgectl", "add"]]
    assert add_calls, "must register the drop folder"
    assert add_calls[0][2] == str(tmp_path / "VST3")
    assert ["yabridgectl", "sync"] in calls
    # register happens before sync
    assert calls.index(["yabridgectl", "add", str(tmp_path / "VST3")]) < calls.index(["yabridgectl", "sync"])
    assert result.plugins_found == [tmp_path / "VST3" / "FlatCRMBL.vst3"]
    assert result.bridged_count == 0  # not parsed from this fake output


def test_sync_parses_bridged_count(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        PL,
        "run_command",
        lambda cmd, env=None: FakeResult(0, stdout="Finished setting up 37 plugins (37 new)"),
    )
    monkeypatch.setattr(PL.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    result = PL.sync_plugins(drop_dir=tmp_path / "VST3", home=tmp_path)
    assert result.bridged_count == 37


def test_sync_add_failure_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(PL, "run_command", lambda cmd, env=None: FakeResult(1, stderr="boom"))
    monkeypatch.setattr(PL.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    with pytest.raises(PL.PluginsError, match="yabridgectl add"):
        PL.sync_plugins(drop_dir=tmp_path / "VST3", home=tmp_path)


def test_sync_failure_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def flaky(cmd: list, env=None):
        if cmd == ["yabridgectl", "sync"]:
            return FakeResult(1, stderr="boom")
        return FakeResult(0)
    monkeypatch.setattr(PL, "run_command", flaky)
    monkeypatch.setattr(PL.shutil, "which", lambda cmd: f"/usr/bin/{cmd}")
    with pytest.raises(PL.PluginsError, match="yabridgectl sync"):
        PL.sync_plugins(drop_dir=tmp_path / "VST3", home=tmp_path)


# --- stub mapping -------------------------------------------------------


def test_stub_for_vst3(tmp_path: Path):
    plugin = tmp_path / "CRMBL.vst3"
    assert PL.stub_for(plugin, tmp_path / ".vst3" / "yabridge") == tmp_path / ".vst3" / "yabridge" / "CRMBL.vst3"


def test_stub_for_dll_is_none(tmp_path: Path):
    plugin = tmp_path / "old.vst.dll"
    assert PL.stub_for(plugin, tmp_path / ".vst3" / "yabridge") is None


# --- vendor data linking -------------------------------------------------


def _make_source_prefix(tmp_path: Path, vendor: str = "Arturia") -> Path:
    """Build a fake source wine prefix with vendor data + registry."""
    prefix = tmp_path / "src-wine"
    drive_c = prefix / "drive_c"
    (drive_c / "ProgramData" / vendor / "Delay ETERNITY").mkdir(parents=True)
    (drive_c / "Program Files" / vendor).mkdir(parents=True)
    system_reg = prefix / "system.reg"
    # Real wine system.reg files store Windows paths with two literal
    # backslashes (e.g. [Software\\Arturia]); the fixture mirrors that.
    system_reg.write_text(
        "WINE REGISTRY Version 2\n"
        f"[Software\\{vendor}] 1753983202\n"
        "#time=1dc024136b5d70c\n"
        '"InstallVST364Dir"="C:\\Program Files\\Common Files\\VST3"\n'
        "\n"
        f"[Software\\{vendor}\\Delay ETERNITY] 1753983202\n"
        f'"installdir"="C:\\ProgramData\\{vendor}\\Delay ETERNITY"\n'
        "\n",
        encoding="utf-8",
    )
    return prefix


def _make_target(tmp_path: Path, name: str = "ableton") -> Path:
    target = tmp_path / "prefixes" / name
    (target / "drive_c").mkdir(parents=True)
    return target


def test_find_vendor_data(tmp_path: Path):
    src = _make_source_prefix(tmp_path)
    dirs = PL.find_vendor_data(src, "Arturia")
    names = sorted(str(d.relative_to(src / "drive_c")) for d in dirs)
    assert names == ["Program Files/Arturia", "ProgramData/Arturia"]


def test_find_vendor_data_respects_exact_dir_name(tmp_path: Path):
    """Data dir lookup is case-sensitive (Linux paths) — a lowercase
    vendor dir is only found by the exact same name."""
    src = _make_source_prefix(tmp_path, "arturia")
    assert PL.find_vendor_data(src, "Arturia") == []
    assert len(PL.find_vendor_data(src, "arturia")) >= 1


def test_parse_vendor_registry(tmp_path: Path):
    src = _make_source_prefix(tmp_path)
    reg = PL.parse_vendor_registry(src, "Arturia")
    assert "Software\\Arturia" in reg
    assert reg["Software\\Arturia"]["InstallVST364Dir"] == "C:\\Program Files\\Common Files\\VST3"
    assert "Software\\Arturia\\Delay ETERNITY" in reg
    assert reg["Software\\Arturia\\Delay ETERNITY"]["installdir"] == "C:\\ProgramData\\Arturia\\Delay ETERNITY"


def test_parse_vendor_registry_skips_other_vendors(tmp_path: Path):
    src = _make_source_prefix(tmp_path)
    assert PL.parse_vendor_registry(src, "Native Instruments") == {}


def test_parse_vendor_registry_no_file(tmp_path: Path):
    assert PL.parse_vendor_registry(tmp_path / "missing", "Arturia") == {}


def test_resolve_wine_prefers_custom(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    target = _make_target(tmp_path)
    monkeypatch.setattr(
        PL.shutil, "which",
        lambda cmd: "/opt/syntropia-wine/bin/wine" if cmd == "/opt/syntropia-wine/bin/wine" else None,
    )
    monkeypatch.setattr(
        PL, "run_command",
        lambda cmd, env=None: FakeResult(0, stdout="\r\nMicrosoft Windows 11\r\n"),
    )
    assert PL.resolve_wine(target) == "/opt/syntropia-wine/bin/wine"


def test_resolve_wine_rejects_version_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    target = _make_target(tmp_path)
    monkeypatch.setattr(PL.shutil, "which", lambda cmd: cmd)

    def probe(cmd: list, env=None) -> FakeResult:
        if cmd[0] == "/opt/syntropia-wine/bin/wine":
            return FakeResult(1, stderr="wine client error:0: version mismatch 956/848.")
        return FakeResult(0, stdout="\r\nMicrosoft Windows 11\r\n")
    monkeypatch.setattr(PL, "run_command", probe)
    assert PL.resolve_wine(target) == "/opt/ableton-wine/bin/wine"


def test_link_vendor_data_dry_run_changes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    src = _make_source_prefix(tmp_path)
    target = _make_target(tmp_path)
    calls: list = []
    monkeypatch.setattr(
        PL, "run_command",
        lambda cmd, env=None: (calls.append(cmd), FakeResult(0, stdout="\r\nMicrosoft Windows 11\r\n"))[1],
    )
    monkeypatch.setattr(PL.shutil, "which", lambda cmd: cmd)

    result = PL.link_vendor_data("Arturia", src, target_prefixes=[target], dry_run=True)

    assert result.dry_run
    assert len(result.data_dirs) == 2
    assert len(result.registry_keys) == 2
    # dry-run must not touch the filesystem or run wine reg add
    assert not (target / "drive_c" / "ProgramData" / "Arturia").exists()
    assert calls == []  # dry-run never runs any command


def test_link_vendor_data_real_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    src = _make_source_prefix(tmp_path)
    target = _make_target(tmp_path)
    calls: list = []

    def run(cmd: list, env=None) -> FakeResult:
        calls.append(cmd)
        if cmd[:2] == ["wine", "reg"]:
            return FakeResult(0, stdout="reg: The operation completed successfully")
        return FakeResult(0, stdout="\r\nMicrosoft Windows 11\r\n")
    monkeypatch.setattr(PL, "run_command", run)
    monkeypatch.setattr(PL.shutil, "which", lambda cmd: cmd)

    result = PL.link_vendor_data("Arturia", src, target_prefixes=[target])

    # data dirs symlinked
    linked = target / "drive_c" / "ProgramData" / "Arturia"
    assert linked.is_symlink()
    assert linked.resolve() == (src / "drive_c" / "ProgramData" / "Arturia").resolve()
    # registry keys added via wine reg add
    reg_adds = [c for c in calls if c[1:2] == ["reg"] and c[2] == "add"]
    assert len(reg_adds) == 2
    assert any("Delay ETERNITY" in c[3] and "installdir" in c for c in reg_adds)
    assert result.registry_keys[0][0] == target


def test_link_vendor_data_skips_existing_registry_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Values already present in the target prefix must never be overwritten
    (protects a previously-configured prefix from source-registry quirks)."""
    src = _make_source_prefix(tmp_path)
    target = _make_target(tmp_path)
    # Target already has one of the two registry values with a DIFFERENT value.
    system_reg = target / "system.reg"
    system_reg.write_text(
        "WINE REGISTRY Version 2\n"
        "[Software\\\\Arturia\\\\Delay ETERNITY] 123\n"
        '"installdir"="C:\\\\Somewhere\\Else"\n'
        "\n",
        encoding="utf-8",
    )
    calls: list = []

    def run(cmd: list, env=None) -> FakeResult:
        calls.append(cmd)
        if cmd[1:2] == ["reg"] and cmd[2] == "add":
            return FakeResult(0, stdout="reg: The operation completed successfully")
        return FakeResult(0, stdout="\r\nMicrosoft Windows 11\r\n")
    monkeypatch.setattr(PL, "run_command", run)
    monkeypatch.setattr(PL.shutil, "which", lambda cmd: cmd)

    result = PL.link_vendor_data("Arturia", src, target_prefixes=[target])

    reg_adds = [c for c in calls if c[1:2] == ["reg"] and c[2] == "add"]
    # installdir exists → skipped; the parent InstallVST364Dir is missing → added
    assert len(reg_adds) == 1
    assert "InstallVST364Dir" in reg_adds[0]
    # the target's existing (deliberately different) value is untouched
    parsed = PL._read_hklm(target)
    assert parsed["Software\\Arturia\\Delay ETERNITY"]["installdir"] == "C:\\Somewhere\\Else"


def test_link_vendor_data_requires_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    src = tmp_path / "empty"
    src.mkdir()
    target = _make_target(tmp_path)
    monkeypatch.setattr(PL.shutil, "which", lambda cmd: cmd)
    with pytest.raises(PL.PluginsError, match="no 'Arturia' data or registry keys"):
        PL.link_vendor_data("Arturia", src, target_prefixes=[target])


def test_link_vendor_data_skips_existing_symlink(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    src = _make_source_prefix(tmp_path)
    target = _make_target(tmp_path)
    dest = target / "drive_c" / "ProgramData" / "Arturia"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.symlink_to(src / "drive_c" / "ProgramData" / "Arturia", target_is_directory=True)
    monkeypatch.setattr(
        PL, "run_command",
        lambda cmd, env=None: FakeResult(0, stdout="\r\nMicrosoft Windows 11\r\n"),
    )
    monkeypatch.setattr(PL.shutil, "which", lambda cmd: cmd)

    result = PL.link_vendor_data("Arturia", src, target_prefixes=[target])
    # the pre-existing symlink is not re-created
    assert not any(d == dest for d, _ in result.data_dirs)
