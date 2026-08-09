"""Tests for syntropia.brew — the .brew manifest parser and validator."""

import re
from pathlib import Path

import pytest

from syntropia.brew import (
    Brew,
    BrewError,
    KNOWN_SECTIONS,
    REQUIRED_SECTIONS,
    _SECTION_FIELDS,
    brew_filename,
    find_brews,
    find_repo_brew,
    lint_brew,
    load_brew,
    parse_brew,
    registry_brew_is_stale,
    resolve_brew,
    save_brew,
    slugify_name,
)


def make_valid_brew() -> dict:
    """A minimal but valid brew document (mirrors tomllib's nested structure)."""
    return {
        "brew": {
            "name": "Test Synth",
            "version": "1.0",
            "category": "vst3_synth",
            "maintainer": "Syntropia Team <x@y.io>",
        },
        "wine": {
            "version": "cachyos-wine",
            "prefix": "~/.local/share/syntropia/prefixes/test",
            "arch": "win64",
        },
        "install": {"commands": ["echo installing"]},
    }


def make_full_brew() -> dict:
    """A brew exercising every optional section."""
    data = make_valid_brew()
    data["wine"]["overrides"] = {"d2d1": "disabled", "gdiplus": "native"}
    data["winetricks"] = {"packages": ["gdiplus", "corefonts", "vcrun2022"]}
    data["yabridge"] = {"enabled": True, "plugin_dirs": ["~/VST3"]}
    data["environment"] = {"WINEDLLOVERRIDES": "winemenubuilder.exe=d", "LANG": "en_US.UTF-8"}
    data["vendor_data"] = {"source": "~/.wine", "vendors": ["Arturia"]}
    return data


# --- parsing ------------------------------------------------------------


def test_valid_minimal_brew_parses():
    brew = parse_brew(make_valid_brew())
    assert isinstance(brew, Brew)
    assert brew.name == "Test Synth"
    assert brew.version == "1.0"
    assert brew.category == "vst3_synth"
    assert brew.maintainer == "Syntropia Team <x@y.io>"
    assert brew.wine_version == "cachyos-wine"
    assert brew.wine_arch == "win64"
    assert brew.install_commands == ["echo installing"]
    assert brew.wine_overrides == {}
    assert brew.winetricks_packages == []
    assert brew.yabridge_enabled is False
    assert brew.plugin_dirs == []
    assert brew.environment == {}


def test_full_brew_parses_everything():
    brew = parse_brew(make_full_brew())
    assert brew.wine_overrides == {"d2d1": "disabled", "gdiplus": "native"}
    assert brew.winetricks_packages == ["gdiplus", "corefonts", "vcrun2022"]
    assert brew.yabridge_enabled is True
    assert brew.plugin_dirs == ["~/VST3"]
    assert brew.environment["WINEDLLOVERRIDES"] == "winemenubuilder.exe=d"
    assert brew.vendor_source == "~/.wine"
    assert brew.vendor_names == ["Arturia"]


# --- required sections/fields ------------------------------------------


def test_missing_brew_section():
    data = make_valid_brew()
    del data["brew"]
    with pytest.raises(BrewError, match=r"missing required section \[brew\]"):
        parse_brew(data)


def test_missing_wine_section():
    data = make_valid_brew()
    del data["wine"]
    with pytest.raises(BrewError, match=r"missing required section \[wine\]"):
        parse_brew(data)


def test_missing_install_section():
    data = make_valid_brew()
    del data["install"]
    with pytest.raises(BrewError, match=r"missing required section \[install\]"):
        parse_brew(data)


def test_missing_name_field():
    data = make_valid_brew()
    del data["brew"]["name"]
    with pytest.raises(BrewError, match=r"missing required field 'name' in section \[brew\]"):
        parse_brew(data)


def test_missing_wine_prefix():
    data = make_valid_brew()
    del data["wine"]["prefix"]
    with pytest.raises(BrewError, match=r"missing required field 'prefix' in section \[wine\]"):
        parse_brew(data)


def test_missing_install_commands():
    data = make_valid_brew()
    del data["install"]["commands"]
    with pytest.raises(BrewError, match=r"missing required field 'commands' in section \[install\]"):
        parse_brew(data)


def test_empty_install_commands_allowed():
    # A template brew ships with a commented-out command block, so an empty
    # command list must parse (the install engine treats it as a no-op).
    data = make_valid_brew()
    data["install"]["commands"] = []
    brew = parse_brew(data)
    assert brew.install_commands == []


# --- type checks ---------------------------------------------------------


def test_version_must_be_string():
    data = make_valid_brew()
    data["brew"]["version"] = 1.368  # TOML float — not a string
    with pytest.raises(BrewError, match=r"field 'version' in section \[brew\] must be a non-empty string"):
        parse_brew(data)


def test_invalid_arch_rejected():
    data = make_valid_brew()
    data["wine"]["arch"] = "win128"
    with pytest.raises(BrewError, match=r"field 'arch' in \[wine\] must be one of win32, win64"):
        parse_brew(data)


def test_winetricks_packages_must_be_list():
    data = make_valid_brew()
    data["winetricks"] = {"packages": "corefonts"}  # string, not list
    with pytest.raises(BrewError, match=r"'packages' in section \[winetricks\] must be a list of strings"):
        parse_brew(data)


def test_yabridge_enabled_must_be_bool():
    data = make_valid_brew()
    data["yabridge"] = {"enabled": "yes"}
    with pytest.raises(BrewError, match=r"field 'enabled' in \[yabridge\] must be a boolean"):
        parse_brew(data)


def test_environment_must_be_str_to_str():
    data = make_valid_brew()
    data["environment"] = {"WINEDLLOVERRIDES": 42}
    with pytest.raises(BrewError, match=r"\[environment\] must be a table of string -> string"):
        parse_brew(data)


# --- strictness ---------------------------------------------------------


def test_unknown_top_level_section_rejected():
    data = make_valid_brew()
    data["bogus"] = {}
    with pytest.raises(BrewError, match=r"unknown section\(s\): bogus"):
        parse_brew(data)


def test_unknown_brew_field_rejected():
    data = make_valid_brew()
    data["brew"]["secret_field"] = "nope"
    with pytest.raises(BrewError, match=r"unknown field\(s\) in \[brew\]: secret_field"):
        parse_brew(data)


def test_unknown_wine_field_rejected():
    data = make_valid_brew()
    data["wine"]["graphics"] = "vulkan"
    with pytest.raises(BrewError, match=r"unknown field\(s\) in \[wine\]: graphics"):
        parse_brew(data)


def test_vendor_data_defaults_to_none():
    brew = parse_brew(make_valid_brew())
    assert brew.vendor_source is None
    assert brew.vendor_names == []


def test_vendor_data_section_is_optional_table():
    data = make_valid_brew()
    data["vendor_data"] = {"vendors": ["Native Instruments"]}
    brew = parse_brew(data)
    assert brew.vendor_source is None  # source falls back to ~/.wine at run time
    assert brew.vendor_names == ["Native Instruments"]


def test_vendor_data_unknown_field_rejected():
    data = make_valid_brew()
    data["vendor_data"] = {"vendor": ["Arturia"]}  # typo: singular
    with pytest.raises(BrewError, match=r"unknown field\(s\) in \[vendor_data\]: vendor"):
        parse_brew(data)


def test_vendor_data_must_be_table():
    data = make_valid_brew()
    data["vendor_data"] = "Arturia"
    with pytest.raises(BrewError, match=r"section \[vendor_data\] must be a table"):
        parse_brew(data)


# --- file loading -------------------------------------------------------


def test_load_brew_from_file(tmp_path: Path):
    path = tmp_path / "test.brew"
    path.write_text(
        """
[brew]
name = "File Synth"
version = "2.0"
category = "utility"
maintainer = "Syntropia Team <x@y.io>"

[wine]
version = "cachyos-wine"
prefix = "~/.local/share/syntropia/prefixes/file"
arch = "win32"

[install]
commands = ["echo hi"]
""",
        encoding="utf-8",
    )
    brew = load_brew(path)
    assert brew.name == "File Synth"
    assert brew.wine_arch == "win32"
    assert brew.source == path


def test_load_brew_invalid_toml(tmp_path: Path):
    path = tmp_path / "bad.brew"
    path.write_text("this is [not valid toml", encoding="utf-8")
    with pytest.raises(BrewError, match=r"invalid TOML"):
        load_brew(path)


def test_load_brew_missing_file(tmp_path: Path):
    with pytest.raises(BrewError, match=r"file not found"):
        load_brew(tmp_path / "nope.brew")


def test_section_schema_is_self_describing():
    """Section-level metadata must come from _SECTION_FIELDS, never be
    duplicated — a section added to the table without the right flags can't
    silently change what parse_brew enforces."""
    # The known/required section sets are derived from the schema itself.
    assert KNOWN_SECTIONS == frozenset(_SECTION_FIELDS)
    assert REQUIRED_SECTIONS == ("brew", "wine", "install")
    # Every section is either free-form or has field specs (never both empty
    # in a way that would make it unparseable), and free-form sections must
    # have no field rules.
    for name, spec in _SECTION_FIELDS.items():
        assert spec.free_form or spec.fields, f"{name}: no fields and not free-form"
        if spec.free_form:
            assert not spec.fields, f"{name}: free-form sections must not declare fields"
        if spec.required:
            assert not spec.free_form, f"{name}: required sections must be field-driven"


def test_plan_md_documents_all_sections():
    """plan.md's schema block and brew.KNOWN_SECTIONS must agree.

    plan.md is the public schema doc; brew.py enforces it. If one gains a
    section the other doesn't know, agents get confused (or manifests
    break silently) — fail loudly instead.
    """
    plan_md = Path(__file__).resolve().parents[1] / "plan.md"
    text = plan_md.read_text(encoding="utf-8")
    match = re.search(r"```toml\n(.*?)\n```", text, re.DOTALL)
    assert match, "plan.md must contain a ```toml schema block"
    documented = {
        # [wine.overrides] counts as [wine]; sub-sections are part of it.
        line.strip()[1:-1].split(".", 1)[0]
        for line in match.group(1).splitlines()
        if line.strip().startswith("[") and line.strip().endswith("]")
    }
    assert documented == set(KNOWN_SECTIONS), (
        f"plan.md documents {sorted(documented)} but brew.py knows "
        f"{sorted(KNOWN_SECTIONS)} — update plan.md's schema block and/or "
        f"brew.KNOWN_SECTIONS"
    )


def test_every_shipped_brew_parses():
    """Regression net: every .brew shipped in phase1/brews must load.

    A brew that stops parsing breaks `find_brews`, `resolve_brew` (name
    lookups), and any tooling that scans the registry — so a new or edited
    manifest is caught here before it ships.
    """
    brews_dir = Path(__file__).resolve().parents[1] / "brews"
    shipped = sorted(brews_dir.glob("*.brew"))
    assert shipped, f"no .brew files found under {brews_dir}"
    for path in shipped:
        brew = load_brew(path)
        assert brew.name.strip(), f"{path.name}: empty brew name"
        assert brew.wine_version, f"{path.name}: missing wine version"
        assert brew.wine_prefix, f"{path.name}: missing wine prefix"


def test_engine_smoke_brew_stays_parseable():
    """The committed smoke-test brew (phase1/tests/engine-smoke.brew) must
    keep parsing, or smoke_engine.sh silently tests a broken manifest."""
    smoke = Path(__file__).resolve().parent / "engine-smoke.brew"
    assert smoke.is_file(), f"missing {smoke}"
    brew = load_brew(smoke)
    assert brew.name == "Syntropia Engine Smoke Test"
    assert brew.wine_prefix.endswith("engine-smoke-test")
    assert brew.install_commands, "smoke brew needs at least one install command"


def test_no_jammed_install_commands():
    """Lint: no two install commands may share a single line.

    A jammed line looks like ``"cmd one", "cmd two",`` — the second
    command's opening quote appears right after the first command's closing
    quote. TOML escapes internal quotes as ``\"``, so an *unescaped*
    ``", "`` in the commands block can only be end-of-string + comma +
    next-string-start: exactly the jam signature.
    """
    brews_dir = Path(__file__).resolve().parents[1] / "brews"
    shipped = sorted(brews_dir.glob("*.brew"))
    assert shipped
    for path in shipped:
        problems = lint_brew(path)
        assert problems == [], f"{path.name}: {problems}"


def test_lint_brew_flags_jammed_line(tmp_path: Path):
    """lint_brew reports a line holding two commands, with a line number."""
    path = tmp_path / "jammed.brew"
    path.write_text(
        "[brew]\n"
        "name = \"X\"\nversion = \"1\"\ncategory = \"vst\"\nmaintainer = \"T\"\n\n"
        "[wine]\nversion = \"w\"\nprefix = \"~/p\"\narch = \"win64\"\n\n"
        "[install]\n"
        "commands = [\n"
        '  "echo one", "echo two",\n'
        "]\n",
        encoding="utf-8",
    )
    problems = lint_brew(path)
    assert len(problems) == 1
    assert "line 14" in problems[0]
    assert "multiple install commands on one line" in problems[0]


def test_lint_brew_clean_file(tmp_path: Path):
    """A one-command-per-line brew lints clean, even with quotes inside."""
    path = tmp_path / "clean.brew"
    path.write_text(
        "[brew]\n"
        "name = \"X\"\nversion = \"1\"\ncategory = \"vst\"\nmaintainer = \"T\"\n\n"
        "[wine]\nversion = \"w\"\nprefix = \"~/p\"\narch = \"win64\"\n\n"
        "[install]\n"
        "commands = [\n"
        '  "echo \\\"hi\\\" one",\n'
        '  "echo two",\n'
        "]\n",
        encoding="utf-8",
    )
    assert lint_brew(path) == []


def test_lint_brew_ignores_comments(tmp_path: Path):
    """A comment containing `", "` must not trip the lint."""
    path = tmp_path / "comment.brew"
    path.write_text(
        "[brew]\n"
        "name = \"X\"\nversion = \"1\"\ncategory = \"vst\"\nmaintainer = \"T\"\n\n"
        "[wine]\nversion = \"w\"\nprefix = \"~/p\"\narch = \"win64\"\n\n"
        "[install]\n"
        "commands = [\n"
        '  # try "a", "b" together here\n'
        '  "echo one",\n'
        "]\n",
        encoding="utf-8",
    )
    assert lint_brew(path) == []


def test_find_brews_only_matches_extension(tmp_path: Path):
    (tmp_path / "a.brew").write_text("", encoding="utf-8")
    (tmp_path / "b.brew").write_text("", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("", encoding="utf-8")
    found = find_brews(tmp_path)
    assert [p.name for p in found] == ["a.brew", "b.brew"]


def test_find_brews_missing_directory(tmp_path: Path):
    assert find_brews(tmp_path / "does-not-exist") == []


# --- registry write ops ------------------------------------------------


def test_slugify_name():
    assert slugify_name("Ableton Live 12") == "ableton-live-12"
    assert slugify_name("Serum") == "serum"
    assert slugify_name("Surge XT") == "surge-xt"
    assert slugify_name("   Vital  ") == "vital"
    assert slugify_name("FL Studio 2024 Pro") == "fl-studio-2024-pro"


def test_slugify_name_empty_falls_back():
    assert slugify_name("!!!") == "brew"


def test_find_repo_brew_walks_up_to_sibling_brews(tmp_path: Path):
    start = tmp_path / "phase1" / "cli" / "syntropia"
    (tmp_path / "phase1" / "brews").mkdir(parents=True)
    repo_brew = tmp_path / "phase1" / "brews" / "x.brew"
    repo_brew.write_text("x", encoding="utf-8")
    assert find_repo_brew("x.brew", start) == repo_brew


def test_find_repo_brew_missing_returns_none(tmp_path: Path):
    start = tmp_path / "a" / "b"
    start.mkdir(parents=True)
    assert find_repo_brew("x.brew", start) is None


def test_registry_brew_is_stale_detects_drift(tmp_path: Path, monkeypatch):
    registry_file = tmp_path / "registry" / "ableton-live-12.brew"
    registry_file.parent.mkdir(parents=True)
    registry_file.write_text("old manifest", encoding="utf-8")
    repo = tmp_path / "brews" / "ableton-live-12.brew"
    repo.parent.mkdir(parents=True)
    repo.write_text("new manifest", encoding="utf-8")
    monkeypatch.setattr(
        "syntropia.brew.find_repo_brew",
        lambda filename, start=None: repo if filename == "ableton-live-12.brew" else None,
    )
    assert registry_brew_is_stale(registry_file) == repo


def test_registry_brew_is_stale_same_bytes_returns_none(tmp_path: Path, monkeypatch):
    registry_file = tmp_path / "registry" / "x.brew"
    registry_file.parent.mkdir(parents=True)
    registry_file.write_text("same", encoding="utf-8")
    repo = tmp_path / "brews" / "x.brew"
    repo.parent.mkdir(parents=True)
    repo.write_text("same", encoding="utf-8")
    monkeypatch.setattr(
        "syntropia.brew.find_repo_brew",
        lambda filename, start=None: repo if filename == "x.brew" else None,
    )
    assert registry_brew_is_stale(registry_file) is None


def test_registry_brew_is_stale_no_repo_copy_returns_none(tmp_path: Path):
    registry_file = tmp_path / "x.brew"
    registry_file.write_text("x", encoding="utf-8")
    # the real repo's phase1/brews has no x.brew — nothing to compare against
    assert registry_brew_is_stale(registry_file) is None


def test_brew_filename_from_name(tmp_path: Path):
    path = tmp_path / "x.brew"
    path.write_text(
        "[brew]\nname = \"Surge XT\"\nversion = \"1.0\"\ncategory = \"vst\"\nmaintainer = \"T\"\n\n"
        "[wine]\nversion = \"w\"\nprefix = \"~/p\"\narch = \"win64\"\n\n"
        "[install]\ncommands = [\"echo hi\"]\n",
        encoding="utf-8",
    )
    brew = load_brew(path)
    assert brew_filename(brew) == "surge-xt.brew"


def test_save_brew_creates_registry_and_preserves_bytes(tmp_path: Path):
    source = tmp_path / "surge.brew"
    original = "# comment kept\n[brew]\nname = \"Surge XT\"\nversion = \"1.0\"\ncategory = \"vst\"\nmaintainer = \"T\"\n\n[wine]\nversion = \"w\"\nprefix = \"~/p\"\narch = \"win64\"\n\n[install]\ncommands = [\"echo hi\"]\n"
    source.write_text(original, encoding="utf-8")
    brew = load_brew(source)
    registry = tmp_path / "registry"

    target = save_brew(brew, registry)

    assert registry.is_dir()
    assert target.name == "surge-xt.brew"
    assert target.read_text(encoding="utf-8") == original  # bytes verbatim


def test_save_brew_overwrites_existing(tmp_path: Path):
    source = tmp_path / "v.brew"
    source.write_text(
        "[brew]\nname = \"Vital\"\nversion = \"2.0\"\ncategory = \"vst\"\nmaintainer = \"T\"\n\n"
        "[wine]\nversion = \"w\"\nprefix = \"~/p\"\narch = \"win64\"\n\n"
        "[install]\ncommands = [\"echo hi\"]\n",
        encoding="utf-8",
    )
    registry = tmp_path / "registry"
    save_brew(load_brew(source), registry)
    target = registry / "vital.brew"
    assert target.exists()

    # Update the manifest and save again — same slug, new bytes.
    source.write_text(
        "[brew]\nname = \"Vital\"\nversion = \"3.0\"\ncategory = \"vst\"\nmaintainer = \"T\"\n\n"
        "[wine]\nversion = \"w\"\nprefix = \"~/p\"\narch = \"win64\"\n\n"
        "[install]\ncommands = [\"echo hi\"]\n",
        encoding="utf-8",
    )
    save_brew(load_brew(source), registry)
    assert "3.0" in target.read_text(encoding="utf-8")


def test_resolve_brew_path_passthrough(tmp_path: Path):
    path = tmp_path / "direct.brew"
    path.write_text("x", encoding="utf-8")
    assert resolve_brew(path, tmp_path / "registry") == path


def test_resolve_brew_by_name_and_slug(tmp_path: Path):
    registry = tmp_path / "registry"
    registry.mkdir()
    (registry / "serum.brew").write_text("s", encoding="utf-8")
    (registry / "ableton-live-12.brew").write_text("a", encoding="utf-8")

    assert resolve_brew("serum", registry).name == "serum.brew"
    assert resolve_brew("Ableton Live 12", registry).name == "ableton-live-12.brew"


def test_resolve_brew_matches_manifest_name_slug(tmp_path: Path):
    registry = tmp_path / "registry"
    registry.mkdir()
    (registry / "odd-file.brew").write_text(
        "[brew]\nname = \"Oddly Named Synth\"\nversion = \"1\"\ncategory = \"vst\"\nmaintainer = \"T\"\n\n"
        "[wine]\nversion = \"w\"\nprefix = \"~/p\"\narch = \"win64\"\n\n"
        "[install]\ncommands = [\"echo x\"]\n",
        encoding="utf-8",
    )
    assert resolve_brew("oddly named synth", registry).name == "odd-file.brew"
    assert resolve_brew("Oddly-Named-Synth", registry).name == "odd-file.brew"


def test_resolve_brew_accepts_extension_suffix(tmp_path: Path):
    registry = tmp_path / "registry"
    registry.mkdir()
    (registry / "template.brew").write_text("t", encoding="utf-8")
    assert resolve_brew("template", registry).name == "template.brew"
    assert resolve_brew("template.brew", registry).name == "template.brew"


def test_resolve_brew_rejects_path_separators(tmp_path: Path):
    # A name containing '/' must never resolve into the registry via
    # filename joins (path-traversal guard).
    registry = tmp_path / "registry"
    registry.mkdir()
    outside = tmp_path / "secret.brew"
    outside.write_text("s", encoding="utf-8")
    assert resolve_brew("../secret", registry) is None
    assert resolve_brew("../secret.brew", registry) is None


def test_resolve_brew_missing_returns_none(tmp_path: Path):
    assert resolve_brew("nope", tmp_path / "registry") is None
