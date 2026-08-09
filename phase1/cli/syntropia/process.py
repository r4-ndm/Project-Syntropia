"""Shared subprocess + path helpers for the syntropia CLI.

Every module that shells out goes through here: one ``run_command`` to
mock in tests, one place for env/cwd handling, and one ``expand_path``
so tilde/variable expansion behaves identically everywhere.

Kept dependency-free (imports only stdlib) so any module can use it
without creating import cycles.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def run_command(
    cmd: list[str],
    *,
    env: dict[str, str] | None = None,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess:
    """Run a command, capturing output. Wrapped for test mocking."""
    return subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=cwd)


def expand_path(value: str, home: Path) -> Path:
    """Expand ``$VAR`` and ``~`` in a path, anchoring to the given home.

    ``~`` resolves against the injected home (not the process HOME) so
    install targets stay testable and predictable.
    """
    value = os.path.expandvars(value)
    if value.startswith("~"):
        value = str(home) + value[1:] if value != "~" else str(home)
    path = Path(value)
    if not path.is_absolute():
        path = home / path
    return path
