"""Syntropia .brew manifest parser, validator, and local-registry manager.

A .brew file is a TOML document describing how to install a Windows DAW
or VST under Wine via the Syntropia toolchain. The schema is defined in
``phase1/plan.md`` ('.brew' Specification Schema).

This module parses, validates, and manages the local registry
(``~/.config/syntropia/brews``) — it never executes install commands.
The install engine lives in the wine-helper layer.

Requires Python 3.11+ (stdlib ``tomllib``).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BREW_EXTENSION = ".brew"

VALID_WINE_ARCHS = ("win32", "win64")
DEFAULT_SOURCE_LOOK_IN = ["~/Downloads"]

# Known wine builds: brew [wine] version → bin directory to prepend to PATH.
# Adding a wine build is one row here — the install engine and the vendor
# linker both derive their binaries from this table.
WINE_BUILD_BIN_DIRS: dict[str, str] = {
    "syntropia-wine": "/opt/syntropia-wine/bin",
    "ableton-wine": "/opt/ableton-wine/bin",
}

@dataclass(frozen=True)
class FieldSpec:
    """One field in a brew section: name, kind, and whether it's required.

    ``kind`` is one of ``"str"``, ``"str_list"``, ``"str_dict"``, or
    ``"bool"``. ``default`` is used when the field is absent (required
    fields have no default).
    """

    name: str
    kind: str
    required: bool = False
    default: object = None


@dataclass(frozen=True)
class SectionSpec:
    """Schema for one brew section: its fields and section-level rules.

    ``fields``   — the section's FieldSpecs (empty for free-form sections).
    ``required`` — the manifest must declare this section.
    ``free_form``— accepts any string→string pairs (no per-field rules;
                   e.g. [environment]).
    ``skip_empty``— only validated when the section is non-empty
                   (historical [source] leniency).
    """

    fields: tuple[FieldSpec, ...] = ()
    required: bool = False
    free_form: bool = False
    skip_empty: bool = False


# Section schema: section name → its spec, in declaration order.
# This is the single source of truth — the section set (KNOWN_SECTIONS),
# the required sections (REQUIRED_SECTIONS), and every validation rule in
# parse_brew are derived from it. Adding a section is one row here plus
# wiring its extracted values into the Brew constructor.
_SECTION_FIELDS: dict[str, SectionSpec] = {
    "brew": SectionSpec(
        fields=(
            FieldSpec("name", "str", required=True),
            FieldSpec("version", "str", required=True),
            FieldSpec("category", "str", required=True),
            FieldSpec("maintainer", "str", required=True),
        ),
        required=True,
    ),
    "wine": SectionSpec(
        fields=(
            FieldSpec("version", "str", required=True),
            FieldSpec("prefix", "str", required=True),
            FieldSpec("arch", "str", required=True),
            FieldSpec("overrides", "str_dict", default={}),
        ),
        required=True,
    ),
    "winetricks": SectionSpec(fields=(FieldSpec("packages", "str_list", default=[]),)),
    "yabridge": SectionSpec(
        fields=(
            FieldSpec("enabled", "bool", default=False),
            FieldSpec("plugin_dirs", "str_list", default=[]),
        ),
    ),
    "install": SectionSpec(fields=(FieldSpec("commands", "str_list", required=True),), required=True),
    "source": SectionSpec(
        fields=(
            FieldSpec("filename", "str", required=True),
            FieldSpec("url", "str"),
            FieldSpec("look_in", "str_list", default=[]),
        ),
        skip_empty=True,
    ),
    "environment": SectionSpec(free_form=True),
    "vendor_data": SectionSpec(
        fields=(
            FieldSpec("source", "str"),
            FieldSpec("vendors", "str_list", default=[]),
        ),
    ),
}

# Every top-level section a .brew may declare — derived from the schema so
# the parser and the doc never disagree about what exists. plan.md
# documents the same set (a test keeps the two in sync).
KNOWN_SECTIONS = frozenset(_SECTION_FIELDS)

# Sections a manifest must declare — derived so a section added without
# ``required=True`` can't silently become mandatory (or vice versa).
REQUIRED_SECTIONS: tuple[str, ...] = tuple(
    name for name, spec in _SECTION_FIELDS.items() if spec.required
)


class BrewError(Exception):
    """Raised when a .brew manifest is malformed."""

    def __init__(self, path: Path | str, message: str) -> None:
        self.path = str(path)
        self.message = message
        super().__init__(f"{self.path}: {message}")


@dataclass
class Brew:
    """A parsed, validated .brew manifest."""

    name: str
    version: str
    category: str
    maintainer: str
    wine_version: str
    wine_prefix: str
    wine_arch: str
    wine_overrides: dict[str, str]
    winetricks_packages: list[str]
    yabridge_enabled: bool
    plugin_dirs: list[str]
    environment: dict[str, str]
    install_commands: list[str]
    source: Path
    source_filename: str | None = None
    source_url: str | None = None
    source_look_in: list[str] | None = None
    vendor_source: str | None = None
    vendor_names: list[str] | None = None


def _fail(path: Path, message: str) -> None:
    raise BrewError(path, message)


def _require_table(data: dict[str, Any], path: Path, section: str) -> dict[str, Any]:
    if section not in data:
        _fail(path, f"missing required section [{section}]")
    value = data[section]
    if not isinstance(value, dict):
        _fail(path, f"section [{section}] must be a table, got {type(value).__name__}")
    return value


def _extract_fields(
    table: dict[str, Any], path: Path, section: str, specs: tuple[FieldSpec, ...]
) -> dict[str, Any]:
    """Extract and validate *specs* from *table*, failing on the first problem.

    Error messages are stable and precise (field + section named) so
    manifests are easy to fix from the CLI output.
    """
    unknown = set(table) - {spec.name for spec in specs}
    if unknown:
        _fail(path, f"unknown field(s) in [{section}]: {', '.join(sorted(unknown))}")
    out: dict[str, Any] = {}
    for spec in specs:
        if spec.name not in table:
            if spec.required:
                _fail(path, f"missing required field '{spec.name}' in section [{section}]")
            out[spec.name] = spec.default
            continue
        value = table[spec.name]
        if spec.kind == "str":
            if not isinstance(value, str) or not value.strip():
                _fail(path, f"field '{spec.name}' in section [{section}] must be a non-empty string, got {type(value).__name__}")
            out[spec.name] = value
        elif spec.kind == "str_list":
            if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
                _fail(path, f"field '{spec.name}' in section [{section}] must be a list of strings")
            out[spec.name] = list(value)
        elif spec.kind == "str_dict":
            if not isinstance(value, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in value.items()
            ):
                _fail(path, f"field '{spec.name}' in section [{section}] must be a table of string -> string")
            out[spec.name] = dict(value)
        elif spec.kind == "bool":
            if not isinstance(value, bool):
                _fail(path, f"field '{spec.name}' in [{section}] must be a boolean")
            out[spec.name] = value
    return out


def parse_brew(data: dict[str, Any], path: Path | str = "<string>") -> Brew:
    """Parse and validate a loaded .brew TOML document.

    Raises BrewError with a precise message on the first problem found.
    The section schema lives in ``_SECTION_FIELDS``; adding a section is a
    row there plus wiring its extracted values into the Brew constructor.
    """
    path = Path(path)
    if not isinstance(data, dict):
        _fail(path, "brew manifest must be a TOML table")

    unknown = set(data) - KNOWN_SECTIONS
    if unknown:
        _fail(path, f"unknown section(s): {', '.join(sorted(unknown))}")

    # Required sections must be present and be tables.
    required: dict[str, dict[str, Any]] = {}
    for name in REQUIRED_SECTIONS:
        required[name] = _require_table(data, path, name)
    brew_table = required["brew"]
    wine = required["wine"]
    install = required["install"]

    # Optional sections: validate type + shape straight from the schema.
    # Free-form sections (environment) get the combined table/string→string
    # message; everything else just must be a table. [source] keeps its
    # historical leniency via skip_empty: only checked when non-empty.
    for name, spec in _SECTION_FIELDS.items():
        if spec.required:
            continue
        value = data.get(name)
        if value is None or (spec.skip_empty and not value):
            continue
        if spec.free_form:
            if not isinstance(value, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in value.items()
            ):
                _fail(path, f"section [{name}] must be a table of string -> string")
        elif not isinstance(value, dict):
            _fail(path, f"section [{name}] must be a table")

    # Extract fields per section from the schema.
    brew_fields = _extract_fields(brew_table, path, "brew", _SECTION_FIELDS["brew"].fields)
    wine_fields = _extract_fields(wine, path, "wine", _SECTION_FIELDS["wine"].fields)
    winetricks = _extract_fields(data.get("winetricks", {}), path, "winetricks", _SECTION_FIELDS["winetricks"].fields)
    yabridge = _extract_fields(data.get("yabridge", {}), path, "yabridge", _SECTION_FIELDS["yabridge"].fields)
    vendor_data = _extract_fields(data.get("vendor_data", {}), path, "vendor_data", _SECTION_FIELDS["vendor_data"].fields)
    install_fields = _extract_fields(install, path, "install", _SECTION_FIELDS["install"].fields)

    environment = data.get("environment", {})  # validated by the loop above

    # [source] only parses when the section is non-empty (historical
    # behavior: an empty [source] leaves all source fields None).
    source_table = data.get("source", {})
    source_filename: str | None = None
    source_url: str | None = None
    source_look_in: list[str] | None = None
    if source_table:
        source_fields = _extract_fields(source_table, path, "source", _SECTION_FIELDS["source"].fields)
        source_filename = source_fields["filename"]
        source_url = source_fields["url"]
        source_look_in = source_fields["look_in"] or DEFAULT_SOURCE_LOOK_IN

    wine_arch = wine_fields["arch"]
    if wine_arch not in VALID_WINE_ARCHS:
        _fail(path, f"field 'arch' in [wine] must be one of {', '.join(VALID_WINE_ARCHS)}, got '{wine_arch}'")

    return Brew(
        name=brew_fields["name"],
        version=brew_fields["version"],
        category=brew_fields["category"],
        maintainer=brew_fields["maintainer"],
        wine_version=wine_fields["version"],
        wine_prefix=wine_fields["prefix"],
        wine_arch=wine_arch,
        wine_overrides=wine_fields["overrides"],
        winetricks_packages=winetricks["packages"],
        yabridge_enabled=yabridge["enabled"],
        plugin_dirs=yabridge["plugin_dirs"],
        environment=environment,
        install_commands=install_fields["commands"],
        source=path,
        source_filename=source_filename,
        source_url=source_url,
        source_look_in=source_look_in,
        vendor_source=vendor_data["source"],
        vendor_names=vendor_data["vendors"],
    )


def lint_brew(path: Path | str) -> list[str]:
    """Lint a .brew file for style problems; returns a list of messages.

    An empty list means the file is clean. Unlike ``load_brew`` (which
    validates semantics), this checks *formatting* conventions that the
    parser tolerates but humans shouldn't ship — e.g. two install commands
    jammed onto one line (``"cmd one", "cmd two",``).

    The jam signature is an unescaped ``", "`` inside the commands block:
    TOML requires internal quotes to be escaped as ``\"``, so an unescaped
    string-close followed by comma and the next string-open can only mean
    two string literals sharing a line.
    """
    path = Path(path).expanduser()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [f"cannot read file: {exc}"]

    problems: list[str] = []
    in_commands = False
    for lineno, line in enumerate(lines, start=1):
        stripped = line.strip()
        if "commands = [" in stripped:
            in_commands = True
            continue
        if in_commands and stripped == "]":
            break
        if not in_commands or not stripped or stripped.startswith("#"):
            continue
        if '", "' in line:
            problems.append(
                f"line {lineno}: multiple install commands on one line — "
                "split them so each command is on its own line"
            )
    return problems


def load_brew(path: Path | str) -> Brew:
    """Read a .brew file from disk, parse, and validate it."""
    path = Path(path).expanduser()
    try:
        with path.open("rb") as fh:
            data = tomllib.load(fh)
    except FileNotFoundError:
        _fail(path, "file not found")
    except tomllib.TOMLDecodeError as exc:
        _fail(path, f"invalid TOML: {exc}")
    except OSError as exc:
        _fail(path, f"cannot read file: {exc}")
    return parse_brew(data, path)


def find_brews(directory: Path | str) -> list[Path]:
    """Return all ``*.brew`` files in a registry directory (sorted)."""
    directory = Path(directory).expanduser()
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.glob(f"*{BREW_EXTENSION}") if p.is_file())


# --- registry write ops (AUR-style local tree) --------------------------


def slugify_name(name: str) -> str:
    """Derive a registry filename slug from a brew name, AUR-style.

    ``"Ableton Live 12"`` -> ``"ableton-live-12"``. Keeps ``[a-z0-9]``,
    collapses any other run to a single hyphen.
    """
    slug = "".join(ch if ch.isalnum() else "-" for ch in name.strip().lower())
    slug = "-".join(part for part in slug.split("-") if part)
    return slug or "brew"


def brew_filename(brew: Brew) -> str:
    """Registry filename for a brew, e.g. ``ableton-live-12.brew``."""
    return f"{slugify_name(brew.name)}{BREW_EXTENSION}"


def find_repo_brew(filename: str, start: Path | None = None) -> Path | None:
    """Locate *filename* in a repo checkout's ``brews/`` directory.

    The installed CLI may be running from a git checkout (editable
    install) or from site-packages. Walks up from this module's directory
    to find a sibling ``brews/`` dir — the repo's ``phase1/brews`` in the
    editable case. Returns ``None`` when no checkout is present.
    """
    here = start if start is not None else Path(__file__).resolve().parent
    for ancestor in (here, *here.parents):
        candidate = ancestor / "brews" / filename
        if candidate.is_file():
            return candidate
    return None


def registry_brew_is_stale(registry_file: Path) -> Path | None:
    """Return the repo's fresher copy of *registry_file*, or ``None``.

    The registry (``~/.config/syntropia/brews``) holds verbatim copies of
    manifests made by ``syntropia save``. When the repo's ``phase1/brews``
    version is edited after the last save, the registry copy silently goes
    stale and ``syntropia install`` would run the old manifest. Returns the
    repo path when the two differ, so callers can hint ``syntropia save``.
    """
    if not registry_file.is_file():
        return None
    repo = find_repo_brew(registry_file.name)
    if repo is None:
        return None
    try:
        if registry_file.read_bytes() == repo.read_bytes():
            return None
    except OSError:
        return None
    return repo


def save_brew(brew: Brew, registry: Path | str) -> Path:
    """Copy a validated brew's manifest into the registry directory.

    The manifest's raw source bytes are preserved verbatim (comments and
    formatting included) — like copying a PKGBUILD into a local AUR tree.
    Overwrites an existing entry of the same name; the caller decides
    whether that was an add or an update.
    """
    registry = Path(registry).expanduser()
    registry.mkdir(parents=True, exist_ok=True)
    target = registry / brew_filename(brew)
    source = Path(brew.source).expanduser()
    try:
        data = source.read_bytes()
    except OSError as exc:
        raise BrewError(source, f"cannot read manifest for saving: {exc}") from exc
    try:
        target.write_bytes(data)
    except OSError as exc:
        raise BrewError(target, f"cannot write to registry: {exc}") from exc
    return target


def resolve_brew(name_or_path: str | Path, registry: Path | str) -> Path | None:
    """Resolve a CLI argument to a .brew file.

    * an existing file path is used as-is;
    * a bare name matches ``<name>.brew`` or a slugified variant in the
      registry (AUR-style filename lookup);
    * finally, brews are scanned and matched by their ``[brew] name`` slug
      (so ``"Surge XT"`` and ``"surge xt"`` both resolve ``surge-xt.brew``).
    Returns ``None`` when nothing matches.
    """
    candidate = Path(name_or_path).expanduser()
    if candidate.is_file():
        return candidate
    registry = Path(registry).expanduser()
    raw = str(name_or_path)
    needle = slugify_name(raw)
    # Only treat the raw argument as a filename when it is a plain name
    # (no path separators) — otherwise it could escape the registry dir.
    candidates: list[str] = []
    if "/" not in raw and "\\" not in raw:
        candidates.append(raw if raw.endswith(BREW_EXTENSION) else f"{raw}{BREW_EXTENSION}")
    candidates.append(f"{needle}{BREW_EXTENSION}")
    for filename in candidates:
        hit = registry / filename
        if hit.is_file():
            return hit
    for brew_path in find_brews(registry):
        try:
            brew_name = load_brew(brew_path).name
        except BrewError:
            continue
        if slugify_name(brew_name) == needle:
            return brew_path
    return None
