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


def scan_processes(proc_root: Path = Path("/proc")) -> list[tuple[int, str, str]]:
    """Scan ``/proc`` and return ``(pid, environ, cmdline)`` per process.

    ``environ`` is best-effort (``""`` when unreadable — kernel threads, or
    test fixtures that only create ``cmdline``); ``cmdline`` is required and
    unreadable entries are skipped. Both are decoded lossily
    (``errors="replace"``) — good enough for matching a prefix path or
    binary name, never for exact byte round-trips.
    """
    results: list[tuple[int, str, str]] = []
    try:
        entries = sorted(proc_root.iterdir(), key=lambda p: p.name)
    except OSError:
        return results
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            cmdline = (entry / "cmdline").read_bytes().decode("utf-8", "replace")
        except OSError:
            continue
        try:
            environ = (entry / "environ").read_bytes().decode("utf-8", "replace")
        except OSError:
            environ = ""
        results.append((int(entry.name), environ, cmdline))
    return results
