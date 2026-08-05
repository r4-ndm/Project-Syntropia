"""Pytest bootstrap: make the syntropia package and tools importable."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli"))
sys.path.insert(0, str(ROOT / "tools"))
