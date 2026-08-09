"""Tests for syntropia.vendor — Arturia-class vendor data linking."""

from pathlib import Path

import pytest

from syntropia import vendor as V


class FakeResult:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


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
        f"[Software\\\\{vendor}] 1753983202\n"
        "#time=1dc024136b5d70c\n"
        '"InstallVST364Dir"="C:\\\\Program Files\\\\Common Files\\\\VST3"\n'
        "\n"
        f"[Software\\\\{vendor}\\\\Delay ETERNITY] 1753983202\n"
        f'"installdir"="C:\\\\ProgramData\\\\{vendor}\\\\Delay ETERNITY"\n'
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
    dirs = V.find_vendor_data(src, "Arturia")
    names = sorted(str(d.relative_to(src / "drive_c")) for d in dirs)
    assert names == ["Program Files/Arturia", "ProgramData/Arturia"]


def test_find_vendor_data_respects_exact_dir_name(tmp_path: Path):
    """Data dir lookup is case-sensitive (Linux paths) — a lowercase
    vendor dir is only found by the exact same name."""
    src = _make_source_prefix(tmp_path, "arturia")
    assert V.find_vendor_data(src, "Arturia") == []
    assert len(V.find_vendor_data(src, "arturia")) >= 1


def test_parse_vendor_registry(tmp_path: Path):
    src = _make_source_prefix(tmp_path)
    reg = V.parse_vendor_registry(src, "Arturia")
    assert "Software\\Arturia" in reg
    assert reg["Software\\Arturia"]["InstallVST364Dir"] == "C:\\Program Files\\Common Files\\VST3"
    assert "Software\\Arturia\\Delay ETERNITY" in reg
    assert reg["Software\\Arturia\\Delay ETERNITY"]["installdir"] == "C:\\ProgramData\\Arturia\\Delay ETERNITY"


def test_parse_vendor_registry_skips_other_vendors(tmp_path: Path):
    src = _make_source_prefix(tmp_path)
    assert V.parse_vendor_registry(src, "Native Instruments") == {}


def test_parse_vendor_registry_no_file(tmp_path: Path):
    assert V.parse_vendor_registry(tmp_path / "missing", "Arturia") == {}


def test_resolve_wine_prefers_custom(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    target = _make_target(tmp_path)
    monkeypatch.setattr(
        V.shutil, "which",
        lambda cmd: "/opt/syntropia-wine/bin/wine" if cmd == "/opt/syntropia-wine/bin/wine" else None,
    )
    monkeypatch.setattr(
        V, "run_command",
        lambda cmd, env=None: FakeResult(0, stdout="\r\nMicrosoft Windows 11\r\n"),
    )
    assert V.resolve_wine(target) == "/opt/syntropia-wine/bin/wine"


def test_resolve_wine_rejects_version_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    target = _make_target(tmp_path)
    monkeypatch.setattr(V.shutil, "which", lambda cmd: cmd)

    def probe(cmd: list, env=None) -> FakeResult:
        if cmd[0] == "/opt/syntropia-wine/bin/wine":
            return FakeResult(1, stderr="wine client error:0: version mismatch 956/848.")
        return FakeResult(0, stdout="\r\nMicrosoft Windows 11\r\n")
    monkeypatch.setattr(V, "run_command", probe)
    assert V.resolve_wine(target) == "/opt/ableton-wine/bin/wine"


def test_link_vendor_data_dry_run_changes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    src = _make_source_prefix(tmp_path)
    target = _make_target(tmp_path)
    calls: list = []
    monkeypatch.setattr(
        V, "run_command",
        lambda cmd, env=None: (calls.append(cmd), FakeResult(0, stdout="\r\nMicrosoft Windows 11\r\n"))[1],
    )
    monkeypatch.setattr(V.shutil, "which", lambda cmd: cmd)

    result = V.link_vendor_data("Arturia", src, target_prefixes=[target], dry_run=True)

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
    monkeypatch.setattr(V, "run_command", run)
    monkeypatch.setattr(V.shutil, "which", lambda cmd: cmd)

    result = V.link_vendor_data("Arturia", src, target_prefixes=[target])

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
        '"installdir"="C:\\\\Somewhere\\\\Else"\n'
        "\n",
        encoding="utf-8",
    )
    calls: list = []

    def run(cmd: list, env=None) -> FakeResult:
        calls.append(cmd)
        if cmd[1:2] == ["reg"] and cmd[2] == "add":
            return FakeResult(0, stdout="reg: The operation completed successfully")
        return FakeResult(0, stdout="\r\nMicrosoft Windows 11\r\n")
    monkeypatch.setattr(V, "run_command", run)
    monkeypatch.setattr(V.shutil, "which", lambda cmd: cmd)

    result = V.link_vendor_data("Arturia", src, target_prefixes=[target])

    reg_adds = [c for c in calls if c[1:2] == ["reg"] and c[2] == "add"]
    # installdir exists → skipped; the parent InstallVST364Dir is missing → added
    assert len(reg_adds) == 1
    assert "InstallVST364Dir" in reg_adds[0]
    # the target's existing (deliberately different) value is untouched
    parsed = V._read_hklm(target)
    assert parsed["Software\\Arturia\\Delay ETERNITY"]["installdir"] == "C:\\Somewhere\\Else"


def test_link_vendor_data_requires_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    src = tmp_path / "empty"
    src.mkdir()
    target = _make_target(tmp_path)
    monkeypatch.setattr(V.shutil, "which", lambda cmd: cmd)
    with pytest.raises(V.VendorError, match="no 'Arturia' data or registry keys"):
        V.link_vendor_data("Arturia", src, target_prefixes=[target])


def test_link_vendor_data_skips_existing_symlink(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    src = _make_source_prefix(tmp_path)
    target = _make_target(tmp_path)
    dest = target / "drive_c" / "ProgramData" / "Arturia"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.symlink_to(src / "drive_c" / "ProgramData" / "Arturia", target_is_directory=True)
    monkeypatch.setattr(
        V, "run_command",
        lambda cmd, env=None: FakeResult(0, stdout="\r\nMicrosoft Windows 11\r\n"),
    )
    monkeypatch.setattr(V.shutil, "which", lambda cmd: cmd)

    result = V.link_vendor_data("Arturia", src, target_prefixes=[target])
    # the pre-existing symlink is not re-created
    assert not any(d == dest for d, _ in result.data_dirs)
