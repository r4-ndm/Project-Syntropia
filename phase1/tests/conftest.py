"""Pytest bootstrap: make the syntropia package and tools importable."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Three Python distributions live under phase1/cli/: the core (cli/syntropia),
# the brew engine (cli/brews/syntropia_brews), and the transform
# (cli/transform/syntropia_transform). Add all three so tests import from a
# bare checkout the same way the installed packages do.
sys.path.insert(0, str(ROOT / "cli"))
sys.path.insert(0, str(ROOT / "cli" / "brews"))
sys.path.insert(0, str(ROOT / "cli" / "transform"))
sys.path.insert(0, str(ROOT / "tools"))
