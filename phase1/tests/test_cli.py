"""CLI tests for the registry write ops (save/remove) and name resolution."""

from pathlib import Path

from click.testing import CliRunner

from syntropia.cli import cli

VALID_BREW = """\
# minimal manifest
[brew]
name = "Surge XT"
version = "1.3.4"
category = "vst3_synth"
maintainer = "Syntropia Team <x@y.io>"

[wine]
version = "cachyos-wine"
prefix = "~/.local/share/syntropia/prefixes/surge-xt"
arch = "win64"

[install]
commands = ["echo hello from surge"]
"""


def _write_brew(tmp_path: Path, name: str = "surge.brew", content: str = VALID_BREW) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def _run(*args: str):
    return CliRunner().invoke(cli, list(args))


# --- save ---------------------------------------------------------------


def test_save_adds_brew_to_registry(tmp_path: Path):
    source = _write_brew(tmp_path)
    registry = tmp_path / "registry"
    result = _run("save", str(source), "--registry", str(registry))
    assert result.exit_code == 0, result.output
    assert "saved surge-xt.brew" in result.output
    assert (registry / "surge-xt.brew").exists()


def test_save_rejects_invalid_brew(tmp_path: Path):
    source = _write_brew(tmp_path, content="this is [not toml")
    result = _run("save", str(source), "--registry", str(tmp_path / "registry"))
    assert result.exit_code != 0
    assert "invalid TOML" in result.output


def test_save_uses_registry_filename_slug(tmp_path: Path):
    source = _write_brew(tmp_path)
    result = _run("save", str(source), "--registry", str(tmp_path / "registry"))
    assert result.exit_code == 0
    assert "surge-xt.brew" in result.output


# --- remove -------------------------------------------------------------


def test_remove_deletes_from_registry(tmp_path: Path):
    source = _write_brew(tmp_path)
    registry = tmp_path / "registry"
    _run("save", str(source), "--registry", str(registry))
    assert (registry / "surge-xt.brew").exists()

    result = _run("remove", "surge-xt", "--registry", str(registry))
    assert result.exit_code == 0, result.output
    assert "removed" in result.output
    assert not (registry / "surge-xt.brew").exists()


def test_remove_accepts_extension_suffix(tmp_path: Path):
    source = _write_brew(tmp_path)
    registry = tmp_path / "registry"
    _run("save", str(source), "--registry", str(registry))
    result = _run("remove", "surge-xt.brew", "--registry", str(registry))
    assert result.exit_code == 0, result.output
    assert "removed" in result.output
    assert not (registry / "surge-xt.brew").exists()


def test_remove_unknown_name_fails(tmp_path: Path):
    result = _run("remove", "ghost", "--registry", str(tmp_path / "registry"))
    assert result.exit_code != 0
    assert "no brew named 'ghost'" in result.output


def test_remove_refuses_outside_registry(tmp_path: Path):
    outside = tmp_path / "elsewhere.brew"
    outside.write_text("x", encoding="utf-8")
    registry = tmp_path / "registry"
    # Resolves to the file path (passthrough) — must be refused, not deleted.
    result = _run("remove", str(outside), "--registry", str(registry))
    assert result.exit_code != 0
    assert outside.exists()


# --- install / info by name --------------------------------------------


def test_install_unknown_name_offers_hint(tmp_path: Path):
    result = _run("install", "ghost", "--registry", str(tmp_path / "registry"), "--check")
    assert result.exit_code != 0
    assert "no brew named 'ghost'" in result.output
    assert "syntropia save" in result.output


def test_install_resolves_name_from_registry(tmp_path: Path):
    source = _write_brew(tmp_path)
    registry = tmp_path / "registry"
    _run("save", str(source), "--registry", str(registry))
    result = _run("install", "surge-xt", "--registry", str(registry), "--check")
    # Dry-run still requires the Wine toolchain on this host; the point is
    # that name resolution succeeds and we get past validation to the plan.
    assert "Surge XT" in result.output


JAMMED_BREW = """\
[brew]
name = "Jammed App"
version = "1.0"
category = "utility"
maintainer = "Syntropia Team <x@y.io>"

[wine]
version = "cachyos-wine"
prefix = "~/.local/share/syntropia/prefixes/jammed"
arch = "win64"

[install]
commands = [
  "echo one", "echo two",
]
"""


def test_install_fails_fast_on_jammed_manifest(tmp_path: Path):
    """install must reject a jammed commands line before running anything.

    The lint check runs right after load_brew and before any wine/prefix
    work, so a jammed manifest errors out even in --check dry-run mode
    instead of partially proceeding.
    """
    source = _write_brew(tmp_path, name="jammed.brew", content=JAMMED_BREW)
    result = _run("install", str(source), "--check")
    assert result.exit_code != 0
    assert "fails lint" in result.output
    assert "multiple install commands on one line" in result.output


MYSTERY_BREW = """\
[brew]
name = "Mystery"
version = "1.0"
category = "utility"
maintainer = "Syntropia Team <x@y.io>"

[wine]
version = "cachyos-wine"
prefix = "~/.local/share/syntropia/prefixes/mystery"
arch = "win64"

[install]
commands = ["echo mystery"]
"""


def test_install_warns_when_registry_brew_is_stale(tmp_path: Path, monkeypatch):
    """install must hint `syntropia save` when the registry copy of a brew
    has drifted from the repo's phase1/brews version."""
    source = _write_brew(tmp_path, name="mystery.brew", content=MYSTERY_BREW)
    registry = tmp_path / "registry"
    _run("save", str(source), "--registry", str(registry))
    repo = tmp_path / "repo" / "brews" / "mystery.brew"
    repo.parent.mkdir(parents=True)
    repo.write_text("# fresher\n" + source.read_text(), encoding="utf-8")
    monkeypatch.setattr(
        "syntropia.brew.find_repo_brew",
        lambda filename, start=None: repo if filename == "mystery.brew" else None,
    )
    result = _run("install", "mystery", "--registry", str(registry), "--check")
    assert "registry copy of mystery.brew differs" in result.output
    assert "syntropia save" in result.output


def test_install_silent_when_registry_brew_current(tmp_path: Path, monkeypatch):
    """No warning when the registry copy matches the repo version."""
    source = _write_brew(tmp_path, name="mystery.brew", content=MYSTERY_BREW)
    registry = tmp_path / "registry"
    _run("save", str(source), "--registry", str(registry))
    # the repo copy is byte-identical to what was saved
    monkeypatch.setattr(
        "syntropia.brew.find_repo_brew",
        lambda filename, start=None: source if filename == "mystery.brew" else None,
    )
    result = _run("install", "mystery", "--registry", str(registry), "--check")
    assert "registry copy" not in result.output


def test_info_by_name(tmp_path: Path):
    source = _write_brew(tmp_path)
    registry = tmp_path / "registry"
    _run("save", str(source), "--registry", str(registry))
    result = _run("info", "Surge XT", "--registry", str(registry))
    assert result.exit_code == 0, result.output
    assert "Surge XT 1.3.4" in result.output


def test_list_brews_shows_saved(tmp_path: Path):
    source = _write_brew(tmp_path)
    registry = tmp_path / "registry"
    _run("save", str(source), "--registry", str(registry))
    result = _run("list-brews", "--registry", str(registry))
    assert result.exit_code == 0
    assert "surge-xt.brew" in result.output


# --- submit -------------------------------------------------------------


def test_submit_unknown_name_fails(tmp_path: Path):
    result = _run("submit", "ghost", "--registry", str(tmp_path / "registry"))
    assert result.exit_code != 0
    assert "no brew named 'ghost'" in result.output


def test_submit_prints_pr_url(tmp_path: Path, monkeypatch):
    source = _write_brew(tmp_path)
    registry = tmp_path / "registry"
    _run("save", str(source), "--registry", str(registry))
    monkeypatch.setattr(
        "syntropia.cli.submit_brew",
        lambda brew_path, registry, base="main": "https://github.com/r4-ndm/syntropia-brews/pull/9",
    )
    result = _run("submit", "surge-xt", "--registry", str(registry))
    assert result.exit_code == 0, result.output
    assert "🚀 PR opened" in result.output
    assert "https://github.com/r4-ndm/syntropia-brews/pull/9" in result.output


def test_save_hints_submit(tmp_path: Path):
    source = _write_brew(tmp_path)
    result = _run("save", str(source), "--registry", str(tmp_path / "registry"))
    assert result.exit_code == 0
    assert "syntropia submit surge-xt" in result.output


# --- plugins drop-folder workflow --------------------------------------


def test_plugins_folder_prints_path(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("syntropia.cli.drop_folder", lambda: tmp_path / "VST3")
    result = _run("plugins", "folder")
    assert result.exit_code == 0, result.output
    assert str(tmp_path / "VST3") in result.output


def test_plugins_folder_create_makes_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("syntropia.cli.drop_folder", lambda: tmp_path / "VST3")
    result = _run("plugins", "folder", "--create")
    assert result.exit_code == 0, result.output
    assert (tmp_path / "VST3").is_dir()


def test_plugins_sync_dry_run_changes_nothing(tmp_path: Path, monkeypatch):
    result_obj = type(
        "Result",
        (),
        {
            "drop_dir": tmp_path / "VST3",
            "plugins_found": [tmp_path / "VST3" / "FlatCRMBL.vst3"],
            "stub_dir": tmp_path / ".vst3" / "yabridge",
            "bridged_count": 0,
            "dry_run": True,
        },
    )()
    monkeypatch.setattr("syntropia.cli.sync_plugins", lambda dry_run=False: result_obj)
    result = _run("plugins", "sync", "--check")
    assert result.exit_code == 0, result.output
    assert "Dry-run" in result.output
    assert "Nothing changed" in result.output


def test_plugins_sync_reports_bridged(tmp_path: Path, monkeypatch):
    stub = tmp_path / ".vst3" / "yabridge" / "FlatCRMBL.vst3"
    result_obj = type(
        "Result",
        (),
        {
            "drop_dir": tmp_path / "VST3",
            "plugins_found": [tmp_path / "VST3" / "FlatCRMBL.vst3"],
            "stub_dir": tmp_path / ".vst3" / "yabridge",
            "bridged_count": 1,
            "dry_run": False,
        },
    )()
    monkeypatch.setattr("syntropia.cli.sync_plugins", lambda dry_run=False: result_obj)
    monkeypatch.setattr(
        "syntropia.cli.stub_for",
        lambda plugin, root: stub,
    )
    result = _run("plugins", "sync")
    assert result.exit_code == 0, result.output
    assert "Bridged 1 plugin" in result.output
    assert str(stub) in result.output


def test_plugins_sync_empty_folder_message(tmp_path: Path, monkeypatch):
    result_obj = type(
        "Result",
        (),
        {
            "drop_dir": tmp_path / "VST3",
            "plugins_found": [],
            "stub_dir": tmp_path / ".vst3" / "yabridge",
            "bridged_count": 0,
            "dry_run": False,
        },
    )()
    monkeypatch.setattr("syntropia.cli.sync_plugins", lambda dry_run=False: result_obj)
    result = _run("plugins", "sync")
    assert result.exit_code == 0, result.output
    assert "No Windows VST3/VST2/CLAP plugins found" in result.output


def test_plugins_link_dry_run(tmp_path: Path, monkeypatch):
    link_result = type(
        "LinkResult",
        (),
        {
            "vendor": "Arturia",
            "source_prefix": tmp_path / "wine",
            "target_prefixes": [tmp_path / "prefixes" / "ableton"],
            "data_dirs": [(tmp_path / "wine" / "d", tmp_path / "prefixes" / "ableton" / "d")],
            "registry_keys": [
                (tmp_path / "prefixes" / "ableton", "Software\\Arturia\\X", "installdir", "C:\\data"),
            ],
            "dry_run": True,
        },
    )()
    monkeypatch.setattr(
        "syntropia.cli.link_vendor_data",
        lambda vendor, source, target_prefixes=None, dry_run=False: link_result,
    )
    result = _run("plugins", "link", "--data", "Arturia", "--check")
    assert result.exit_code == 0, result.output
    assert "Linking Arturia" in result.output
    assert "Dry-run: nothing changed" in result.output


def test_plugins_link_reports_summary(tmp_path: Path, monkeypatch):
    link_result = type(
        "LinkResult",
        (),
        {
            "vendor": "Arturia",
            "source_prefix": tmp_path / "wine",
            "target_prefixes": [tmp_path / "prefixes" / "ableton"],
            "data_dirs": [(tmp_path / "wine" / "d", tmp_path / "prefixes" / "ableton" / "d")],
            "registry_keys": [
                (tmp_path / "prefixes" / "ableton", "Software\\Arturia\\X", "installdir", "C:\\data"),
            ],
            "dry_run": False,
        },
    )()
    monkeypatch.setattr(
        "syntropia.cli.link_vendor_data",
        lambda vendor, source, target_prefixes=None, dry_run=False: link_result,
    )
    result = _run("plugins", "link", "--data", "Arturia")
    assert result.exit_code == 0, result.output
    assert "✅ Linked Arturia: 1 data dir(s), 1 registry value(s)" in result.output


def test_plugins_link_missing_vendor_data(tmp_path: Path, monkeypatch):
    from syntropia.plugins import PluginsError

    def boom(vendor, source, target_prefixes=None, dry_run=False):
        raise PluginsError(f"no '{vendor}' data or registry keys found in {source}")
    monkeypatch.setattr("syntropia.cli.link_vendor_data", boom)
    result = _run("plugins", "link", "--data", "GhostVendor")
    assert result.exit_code != 0
    assert "no 'GhostVendor' data" in result.output


def test_plugins_link_requires_data_flag():
    result = _run("plugins", "link")
    assert result.exit_code != 0
    assert "--data" in result.output
