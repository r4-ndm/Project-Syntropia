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
