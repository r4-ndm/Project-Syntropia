"""Pytest bootstrap: make the syntropia package importable from phase1/cli."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli"))
