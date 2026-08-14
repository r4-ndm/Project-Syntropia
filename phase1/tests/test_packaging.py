"""Packaging lockstep: the three Syntropia packages must share one version.

The single source of truth is ``phase1/cli/syntropia/__init__.py``; the
brews and transform pyprojects hardcode a copy for their wheel builds.
Pin them together so bumping the version in one place can't silently
drift the others (the AUR PKGBUILDs all read __init__.py in pkgver()).
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

PHASE1 = Path(__file__).resolve().parents[1]
CORE_INIT = PHASE1 / "cli" / "syntropia" / "__init__.py"
BREWS_PYPROJECT = PHASE1 / "cli" / "brews" / "pyproject.toml"
TRANSFORM_PYPROJECT = PHASE1 / "cli" / "transform" / "pyproject.toml"


def _core_version() -> str:
    text = CORE_INIT.read_text(encoding="utf-8")
    match = re.search(r'^__version__ = "([^"]+)"', text, re.MULTILINE)
    assert match, "core __version__ not found in syntropia/__init__.py"
    return match.group(1)


def _pyproject_version(path: Path) -> str:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return data["project"]["version"]


def test_three_packages_share_version():
    """syntropia-cli, syntropia-brews, and syntropia must report the same version."""
    core = _core_version()
    assert _pyproject_version(BREWS_PYPROJECT) == core, (
        "syntropia-brews pyproject version drifted from syntropia/__init__.py — "
        "bump them together"
    )
    assert _pyproject_version(TRANSFORM_PYPROJECT) == core, (
        "syntropia (rebrand) pyproject version drifted from syntropia/__init__.py — "
        "bump them together"
    )
