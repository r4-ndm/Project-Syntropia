"""Tests for syntropia_brews.inventory — pure scans over scratch dirs."""

from __future__ import annotations

from pathlib import Path

from syntropia_brews.inventory import (
    scan_all,
    scan_installed_apps,
    scan_linux_plugins,
    scan_registry,
    scan_windows_plugins,
)


def _make_layout(root: Path) -> dict[str, Path]:
    """Create a fake Syntropia home layout; return the interesting paths."""
    root = root.resolve()
    prefixes = root / "prefixes"
    drop = root / "VST3"
    vst3 = root / ".vst3"
    reg = root / "brews"

    # Two provisioned Wine prefixes (drive_c present).
    (prefixes / "ableton" / "drive_c").mkdir(parents=True)
    (prefixes / "serum" / "drive_c").mkdir(parents=True)
    # A stray dir that is NOT a prefix (no drive_c) — must be ignored.
    (prefixes / "not-a-prefix").mkdir(parents=True)

    # Windows plugins in the drop folder: one flat DLL, one bundle dir.
    (drop / "CRMBL.vst3").mkdir(parents=True)
    (drop / "MiniFreak V.vst3").mkdir(parents=True)
    (drop / "unrelated.txt").write_text("hi", encoding="utf-8")

    # yabridge stubs: CRMBL bridged, MiniFreak not.
    (vst3 / "yabridge" / "CRMBL.vst3").mkdir(parents=True)

    # Native Linux VST3s.
    (vst3 / "MiniMeters.vst3").mkdir(parents=True)
    (vst3 / "Other.vst3").mkdir(parents=True)

    # Registry brews. The manifest declares the SAME prefix path the layout
    # uses (scan_installed_apps matches by the manifest's [wine] prefix).
    reg.mkdir(parents=True, exist_ok=True)
    (reg / "ableton-live-12.brew").write_text(
        "[brew]\n"
        'name = "Ableton Live 12"\n'
        'version = "12.1"\n'
        'category = "DAW"\n'
        'maintainer = "Syntropia"\n'
        "[wine]\n"
        'version = "ableton-wine"\n'
        f'prefix = "{prefixes / "ableton"}"\n'
        'arch = "win64"\n'
        "[install]\n"
        'commands = ["echo hi"]\n',
        encoding="utf-8",
    )
    (reg / "broken.brew").write_text("this is [ not toml", encoding="utf-8")

    return {
        "prefixes": prefixes,
        "drop": drop,
        "vst3": vst3,
        "registry": reg,
    }


def test_scan_installed_apps_finds_prefixes_only(tmp_path):
    paths = _make_layout(tmp_path)
    apps = scan_installed_apps(paths["prefixes"], paths["registry"])
    names = [a.name for a in apps]
    assert names == ["ableton", "serum"]  # not-a-prefix excluded
    ableton = apps[0]
    assert ableton.brew is not None and ableton.brew.name == "ableton-live-12.brew"
    serum = apps[1]
    assert serum.brew is None  # no matching manifest in this registry


def test_scan_windows_plugins_reports_bridge_state(tmp_path):
    paths = _make_layout(tmp_path)
    plugins = scan_windows_plugins(paths["drop"], paths["vst3"])
    by_name = {p.name: p for p in plugins}
    assert set(by_name) == {"CRMBL.vst3", "MiniFreak V.vst3"}  # txt excluded
    assert by_name["CRMBL.vst3"].bridged is True
    assert by_name["CRMBL.vst3"].stub_path is not None
    assert by_name["MiniFreak V.vst3"].bridged is False
    assert by_name["MiniFreak V.vst3"].stub_path is None


def test_scan_linux_plugins_excludes_yabridge_stubs(tmp_path):
    paths = _make_layout(tmp_path)
    plugins = scan_linux_plugins(paths["vst3"])
    names = [p.name for p in plugins]
    assert names == ["MiniMeters.vst3", "Other.vst3"]  # yabridge/ excluded


def test_scan_registry_lists_brews_and_tolerates_broken_manifest(tmp_path):
    paths = _make_layout(tmp_path)
    brews = scan_registry(paths["registry"])
    by_name = {b.name: b for b in brews}
    assert "Ableton Live 12" in by_name
    assert by_name["Ableton Live 12"].category == "DAW"
    assert by_name["Ableton Live 12"].version == "12.1"
    # Broken manifest still listed, flagged via description.
    assert "broken" in by_name
    assert "fails to parse" in by_name["broken"].description


def test_scan_all_missing_dirs_returns_empty():
    inv = scan_all("/nonexistent/prefixes", "/nonexistent/VST3", "/nonexistent/.vst3", "/nonexistent/brews")
    assert inv.counts() == {"apps": 0, "windows_vsts": 0, "linux_vsts": 0, "brews": 0}
