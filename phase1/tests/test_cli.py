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
