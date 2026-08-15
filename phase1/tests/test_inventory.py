"""Tests for syntropia_brews.inventory — pure scans over scratch dirs."""

from __future__ import annotations

from pathlib import Path

from syntropia_brews.inventory import (
    scan_all,
    scan_installed_apps,
    scan_linux_plugins,
    scan_registry,
    scan_windows_plugins,
    scan_windows_programs,
    windows_location_to_host,
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
    assert inv.counts() == {
        "apps": 0,
        "windows_programs": 0,
        "windows_vsts": 0,
        "linux_vsts": 0,
        "brews": 0,
    }


_SYSTEM_REG = r"""WINE REGISTRY Version 2
;; All keys relative to \\Machine

[Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{11111111-1111-1111-1111-111111111111}] 1786215206
#time=1d2e3f4g
"DisplayName"="Ableton Live 12"
"DisplayVersion"="12.1"
"InstallLocation"="C:\\Program Files\\Ableton"
"Publisher"="Ableton AG"
"UninstallString"=str(2):"C:\\Program Files\\Ableton\\uninstall.exe"

[Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{22222222-2222-2222-2222-222222222222}] 1786215206
"DisplayName"="Microsoft Visual C++ 2013 Additional Runtime"
"Publisher"="Microsoft Corporation"
"SystemComponent"=dword:00000001

[Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{33333333-3333-3333-3333-333333333333}] 1786215206
"DisplayName"="Microsoft Visual C++ 2015-2022 Redistributable (x64)"
"Publisher"="Microsoft Corporation"

[Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{44444444-4444-4444-4444-444444444444}] 1786215206
"DisplayName"="Wine Mono Runtime"
"Publisher"="The Wine Project"

[Software\\Wow6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{55555555-5555-5555-5555-555555555555}] 1786215206
"DisplayName"="MiniFreak V"
"DisplayVersion"="2.0"
"InstallLocation"="C:\\Program Files (x86)\\Arturia\\MiniFreak V"

[Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\{66666666-6666-6666-6666-666666666666}] 1786215206
"DisplayName"="Some Patch"
"ReleaseType"="Update"
"""


def test_scan_windows_programs_reads_uninstall_entries(tmp_path):
    prefix = tmp_path / "ableton"
    (prefix / "drive_c").mkdir(parents=True)
    (prefix / "system.reg").write_text(_SYSTEM_REG, encoding="utf-8")

    programs = scan_windows_programs(tmp_path)
    by_name = {p.name: p for p in programs}

    # The two real apps survive; system components, MSVC redistributables,
    # Wine's own Mono support, and updates are all filtered out.
    assert set(by_name) == {"Ableton Live 12", "MiniFreak V"}

    ableton = by_name["Ableton Live 12"]
    assert ableton.version == "12.1"
    assert ableton.publisher == "Ableton AG"
    assert ableton.location == r"C:\Program Files\Ableton"
    assert ableton.registry_key == "{11111111-1111-1111-1111-111111111111}"
    assert ableton.prefix_path == prefix

    # The WOW6432Node (32-bit) hive is scanned too.
    assert by_name["MiniFreak V"].location == r"C:\Program Files (x86)\Arturia\MiniFreak V"


def test_scan_windows_programs_ignores_non_prefix_dirs(tmp_path):
    (tmp_path / "not-a-prefix").mkdir()  # no drive_c
    assert scan_windows_programs(tmp_path) == []


def test_windows_location_to_host_maps_drive_paths(tmp_path):
    prefix = tmp_path / "ableton"
    assert windows_location_to_host(prefix, r"C:\Program Files\Arturia") == (
        prefix / "drive_c" / "Program Files" / "Arturia"
    )
    assert windows_location_to_host(prefix, "not a drive path") is None
    assert windows_location_to_host(prefix, "") is None
