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

REQUIRED_BREW_FIELDS = ("name", "version", "category", "maintainer")
VALID_WINE_ARCHS = ("win32", "win64")
KNOWN_SECTIONS = {"brew", "wine", "winetricks", "yabridge", "environment", "install"}
KNOWN_WINE_FIELDS = {"version", "prefix", "arch", "overrides"}
KNOWN_WINETRICKS_FIELDS = {"packages"}
KNOWN_YABRIDGE_FIELDS = {"enabled", "plugin_dirs"}
KNOWN_INSTALL_FIELDS = {"commands"}


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


def _fail(path: Path, message: str) -> None:
    raise BrewError(path, message)


def _require_table(data: dict[str, Any], path: Path, section: str) -> dict[str, Any]:
    if section not in data:
        _fail(path, f"missing required section [{section}]")
    value = data[section]
    if not isinstance(value, dict):
        _fail(path, f"section [{section}] must be a table, got {type(value).__name__}")
    return value


def _require_str(
    table: dict[str, Any], path: Path, section: str, field_name: str, *, optional: bool = False
) -> str | None:
    if field_name not in table:
        if optional:
            return None
        _fail(path, f"missing required field '{field_name}' in section [{section}]")
    value = table[field_name]
    if not isinstance(value, str) or not value.strip():
        _fail(path, f"field '{field_name}' in section [{section}] must be a non-empty string, got {type(value).__name__}")
    return value


def _require_str_list(
    table: dict[str, Any], path: Path, section: str, field_name: str, *, optional: bool = False
) -> list[str]:
    if field_name not in table:
        if optional:
            return []
        _fail(path, f"missing required field '{field_name}' in section [{section}]")
    value = table[field_name]
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        _fail(path, f"field '{field_name}' in section [{section}] must be a list of strings")
    return list(value)


def _require_str_dict(
    table: dict[str, Any], path: Path, section: str, field_name: str, *, optional: bool = False
) -> dict[str, str]:
    if field_name not in table:
        if optional:
            return {}
        _fail(path, f"missing required field '{field_name}' in section [{section}]")
    value = table[field_name]
    if not isinstance(value, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in value.items()
    ):
        _fail(path, f"field '{field_name}' in section [{section}] must be a table of string -> string")
    return dict(value)


def parse_brew(data: dict[str, Any], path: Path | str = "<string>") -> Brew:
    """Parse and validate a loaded .brew TOML document.

    Raises BrewError with a precise message on the first problem found.
    """
    path = Path(path)
    if not isinstance(data, dict):
        _fail(path, "brew manifest must be a TOML table")

    unknown = set(data) - KNOWN_SECTIONS
    if unknown:
        _fail(path, f"unknown section(s): {', '.join(sorted(unknown))}")

    brew_table = _require_table(data, path, "brew")
    unknown_brew = set(brew_table) - set(REQUIRED_BREW_FIELDS)
    if unknown_brew:
        _fail(path, f"unknown field(s) in [brew]: {', '.join(sorted(unknown_brew))}")

    wine = _require_table(data, path, "wine")
    unknown_wine = set(wine) - KNOWN_WINE_FIELDS
    if unknown_wine:
        _fail(path, f"unknown field(s) in [wine]: {', '.join(sorted(unknown_wine))}")

    wine_overrides = _require_str_dict(wine, path, "wine", "overrides", optional=True)

    winetricks = data.get("winetricks", {})
    if not isinstance(winetricks, dict):
        _fail(path, "section [winetricks] must be a table")
    unknown_winetricks = set(winetricks) - KNOWN_WINETRICKS_FIELDS
    if unknown_winetricks:
        _fail(path, f"unknown field(s) in [winetricks]: {', '.join(sorted(unknown_winetricks))}")
    winetricks_packages = _require_str_list(winetricks, path, "winetricks", "packages", optional=True)

    yabridge = data.get("yabridge", {})
    if not isinstance(yabridge, dict):
        _fail(path, "section [yabridge] must be a table")
    unknown_yabridge = set(yabridge) - KNOWN_YABRIDGE_FIELDS
    if unknown_yabridge:
        _fail(path, f"unknown field(s) in [yabridge]: {', '.join(sorted(unknown_yabridge))}")
    yabridge_enabled = yabridge.get("enabled", False)
    if not isinstance(yabridge_enabled, bool):
        _fail(path, "field 'enabled' in [yabridge] must be a boolean")
    plugin_dirs = _require_str_list(yabridge, path, "yabridge", "plugin_dirs", optional=True)

    environment = data.get("environment", {})
    if not isinstance(environment, dict) or not all(
        isinstance(k, str) and isinstance(v, str) for k, v in environment.items()
    ):
        _fail(path, "section [environment] must be a table of string -> string")

    wine_version = _require_str(wine, path, "wine", "version")  # type: ignore[arg-type]
    wine_prefix = _require_str(wine, path, "wine", "prefix")  # type: ignore[arg-type]
    wine_arch = _require_str(wine, path, "wine", "arch")  # type: ignore[arg-type]
    if wine_arch not in VALID_WINE_ARCHS:
        _fail(path, f"field 'arch' in [wine] must be one of {', '.join(VALID_WINE_ARCHS)}, got '{wine_arch}'")

    install = _require_table(data, path, "install")
    unknown_install = set(install) - KNOWN_INSTALL_FIELDS
    if unknown_install:
        _fail(path, f"unknown field(s) in [install]: {', '.join(sorted(unknown_install))}")
    install_commands = _require_str_list(install, path, "install", "commands")
    if not install_commands:
        _fail(path, "field 'commands' in [install] must not be empty")

    return Brew(
        name=_require_str(brew_table, path, "brew", "name"),  # type: ignore[arg-type]
        version=_require_str(brew_table, path, "brew", "version"),  # type: ignore[arg-type]
        category=_require_str(brew_table, path, "brew", "category"),  # type: ignore[arg-type]
        maintainer=_require_str(brew_table, path, "brew", "maintainer"),  # type: ignore[arg-type]
        wine_version=wine_version,
        wine_prefix=wine_prefix,
        wine_arch=wine_arch,
        wine_overrides=wine_overrides,
        winetricks_packages=winetricks_packages,
        yabridge_enabled=yabridge_enabled,
        plugin_dirs=plugin_dirs,
        environment=environment,
        install_commands=install_commands,
        source=path,
    )


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
