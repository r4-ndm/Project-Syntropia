"""Syntropia CLI — entry point and feature-plugin discovery."""

from __future__ import annotations

import importlib
import importlib.metadata
import re
from pathlib import Path

import click

# Entry-point group feature packages register into. Each entry point names
# the package's ``register`` function (e.g.
# ``brews = "syntropia_brews.cli:register"``), which adds that package's
# commands into the core group. This is what lets a user install
# ``syntropia-brews`` without ``syntropia`` (the rebrand) and still get
# only the brew commands.
PLUGIN_GROUP = "syntropia.plugins"

# Fallback for a bare checkout (pytest / ``python -m syntropia.cli``): no
# distribution metadata exists there, so the known plugin modules are
# imported by path instead.
_FALLBACK_MODULES = ("syntropia_brews.cli", "syntropia_transform.cli")


def _cli_version() -> str:
    """Resolve the package version in any install context.

    A PEP 660 editable install loads ``syntropia`` through a finder that
    does not execute ``__init__.py``, so ``from . import __version__``
    fails there (the root module has no attributes). Read the source file
    instead — the same mechanism the PKGBUILD's ``pkgver()`` uses — which
    works for editable installs, site-packages, and bare checkouts alike.
    """
    try:
        text = Path(__file__).resolve().with_name("__init__.py").read_text(encoding="utf-8")
    except OSError:
        return "0.0.0"
    match = re.search(r'^__version__ = "([^"]+)"', text, re.MULTILINE)
    return match.group(1) if match else "0.0.0"


@click.group()
@click.version_option(version=_cli_version(), prog_name="syntropia")
def cli() -> None:
    """Syntropia — the living computer's CLI.

    Feature packages (brews, transform) register their subcommands into
    this group at startup.
    """


_registered: set[str] = set()


def register_plugins(group: click.Group) -> None:
    """Load every installed feature package and let it register its commands.

    Installed packages are discovered through the ``syntropia.plugins``
    entry-point group; in a bare checkout (no distribution metadata) the
    known plugin modules are imported by path instead. Idempotent — each
    plugin registers at most once per process.
    """
    for entry_point in importlib.metadata.entry_points().select(group=PLUGIN_GROUP):
        key = entry_point.name
        if key in _registered:
            continue
        try:
            register = entry_point.load()
        except (ImportError, AttributeError):
            continue
        if register is not None:
            register(group)
            _registered.add(key)

    # Bare checkout: no dist metadata → no entry points, so fall back to
    # importing the known plugin modules by path.
    if not _registered:
        for modname in _FALLBACK_MODULES:
            if modname in _registered:
                continue
            try:
                mod = importlib.import_module(modname)
            except ImportError:
                continue
            register = getattr(mod, "register", None)
            if register is not None:
                register(group)
                _registered.add(modname)


def main() -> None:
    """Console-script entry point."""
    register_plugins(cli)
    cli()


if __name__ == "__main__":
    main()
