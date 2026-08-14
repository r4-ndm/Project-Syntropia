"""syntropia plugins — the drop-folder VST3 workflow.

The user-friendly way to use Windows VST3 plugins in Linux DAWs:

1. Drop any Windows VST3 (or VST2/CLAP) plugin file into ``~/VST3``.
   Flat ``.vst3`` DLLs work fine — yabridge handles the bundle layout.
2. Run ``syntropia plugins sync``.
3. yabridge writes Linux stubs into ``~/.vst3/yabridge/``, which Bitwig,
   Reaper, and most other Linux DAWs scan by default — no extra config.

This module only ever *adds*: it registers the drop folder with
yabridgectl and runs ``yabridgectl sync``. It never removes or modifies
plugins, so no ``--yes`` gate is required (unlike the Wine installers).
``--check`` still offers a dry-run for the safety-minded.

Vendor data linking (``plugins link --data <Vendor>`` — Arturia-class
plugins that need ``ProgramData`` + an ``installdir`` registry key wired
into wine DAW prefixes) lives in :mod:`syntropia.vendor`.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from syntropia.process import expand_path, run_command

# The friendly, discoverable drop folder (uppercase so it never collides
# with the hidden native-Linux ``~/.vst3`` directory).
DEFAULT_PLUGIN_DIR = "~/VST3"

# File types yabridge can bridge from a directory of Windows plugins.
PLUGIN_SUFFIXES = (".vst3", ".dll", ".clap")

# Where yabridge writes the Linux stubs (Bitwig/Reaper scan this by default).
BRIDGE_OUTPUT_DIR = "~/.vst3/yabridge"

_FINISHED_RE = re.compile(r"Finished setting up (\d+) plugins")


class PluginsError(Exception):
    """The plugin drop-folder workflow failed."""


@dataclass
class SyncResult:
    """What ``plugins sync`` did."""

    drop_dir: Path
    plugins_found: list[Path] = field(default_factory=list)
    bridged_count: int = 0
    stub_dir: Path | None = None
    dry_run: bool = False


def drop_folder(home: Path | None = None) -> Path:
    """Resolve the drop folder path (expanding ``~``)."""
    if home is None:
        home = Path(os.path.expanduser("~"))
    return expand_path(DEFAULT_PLUGIN_DIR, home)


def ensure_drop_folder(path: Path) -> Path:
    """Create the drop folder if it does not exist yet."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def find_plugins(path: Path) -> list[Path]:
    """Return the plugin files in *path* (top level only).

    VST3 bundles are directories named ``*.vst3`` — a bare ``*.vst3`` DLL
    is also valid (yabridge treats it as a legacy single-file plugin).
    """
    found: list[Path] = []
    for entry in sorted(path.iterdir()):
        if entry.is_file() and entry.suffix.lower() in PLUGIN_SUFFIXES:
            found.append(entry)
        elif entry.is_dir() and entry.name.lower().endswith(".vst3"):
            found.append(entry)
    return found


def yabridgectl_present() -> bool:
    """True if yabridgectl is on PATH."""
    return shutil.which("yabridgectl") is not None


def register_drop_folder(path: Path) -> None:
    """Register the drop folder with yabridgectl (idempotent)."""
    result = run_command(["yabridgectl", "add", str(path)])
    if result.returncode != 0:
        raise PluginsError(
            f"yabridgectl add {path} failed: "
            f"{result.stdout.strip() or result.stderr.strip()}"
        )


def run_sync() -> tuple[int, str]:
    """Run ``yabridgectl sync``; return (bridged_count, raw output)."""
    result = run_command(["yabridgectl", "sync"])
    output = (result.stdout or "") + (result.stderr or "")
    if result.returncode != 0:
        raise PluginsError(f"yabridgectl sync failed: {output.strip()}")
    match = _FINISHED_RE.search(output)
    count = int(match.group(1)) if match else 0
    return count, output


def sync_plugins(
    drop_dir: Path | None = None,
    home: Path | None = None,
    dry_run: bool = False,
) -> SyncResult:
    """Bridge every Windows plugin in the drop folder.

    Registers the folder with yabridgectl (creating it if needed) and
    syncs, so each dropped plugin gets a Linux stub under ``~/.vst3/``.
    """
    if home is None:
        home = Path(os.path.expanduser("~"))
    if drop_dir is None:
        drop_dir = expand_path(DEFAULT_PLUGIN_DIR, home)
    drop_dir = ensure_drop_folder(drop_dir)
    plugins = find_plugins(drop_dir)

    if not yabridgectl_present():
        raise PluginsError(
            "yabridgectl is not installed — run 'sudo syntropia transform' "
            "to install the audio stack first"
        )

    result = SyncResult(
        drop_dir=drop_dir,
        plugins_found=plugins,
        stub_dir=expand_path(BRIDGE_OUTPUT_DIR, home),
        dry_run=dry_run,
    )

    if dry_run:
        return result

    register_drop_folder(drop_dir)
    bridged, _output = run_sync()
    result.bridged_count = bridged
    return result


def stub_for(plugin: Path, stub_root: Path) -> Path | None:
    """Return the expected Linux stub path for *plugin*, or None.

    Flat ``.vst3``/bundle plugins stub into ``~/.vst3/yabridge/<name>/``;
    VST2 ``.dll`` stubs land in ``~/.vst/yabridge/<stem>.so`` (not
    tracked here — we only report VST3-style stubs).
    """
    if plugin.suffix.lower() in (".vst3", ".clap"):
        return stub_root / plugin.name
    return None
