"""Syntropia .brew manifest parser and validator.

A .brew file is a TOML document describing how to install a Windows DAW
or VST under Wine via the Syntropia toolchain. The schema is defined in
``phase1/plan.md`` ('.brew' Specification Schema).

This module only parses and validates — it never executes anything.
The install engine lives in the CLI and wine-helper layers.

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
