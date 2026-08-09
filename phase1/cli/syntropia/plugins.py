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

``plugins link --data <Vendor>`` additionally wires a vendor's data
(Arturia-class plugins that split installs across ``ProgramData`` + an
``installdir`` registry key) into each wine DAW prefix, so plugins that
load in Bitwig (via yabridge, which runs them in their home prefix) also
initialize in wine-hosted DAWs like Ableton.
"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .wine_helper import run_command

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
    return _expand(DEFAULT_PLUGIN_DIR, home)


def _expand(value: str, home: Path) -> Path:
    if value.startswith("~"):
        value = str(home) + value[1:] if value != "~" else str(home)
    path = Path(value)
    if not path.is_absolute():
        path = home / path
    return path


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
        drop_dir = _expand(DEFAULT_PLUGIN_DIR, home)
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
        stub_dir=_expand(BRIDGE_OUTPUT_DIR, home),
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


# ----------------------------------------------------------------------
# vendor data linking (Arturia-class plugins)
#
# Some Windows plugin vendors (Arturia, Native Instruments, …) split an
# install across a data directory (``C:\ProgramData\<Vendor>``) and an
# ``installdir`` registry key. Bitwig works without extra wiring because
# yabridge runs the plugin inside its *home* prefix, where the data
# lives. A wine-hosted DAW like Ableton runs the plugin in *its own*
# prefix, so the data dir and registry keys must be linked in.
# ----------------------------------------------------------------------

# Wine binaries to try, in order, when writing to a wine prefix.
WINE_CANDIDATES = (
    "/opt/syntropia-wine/bin/wine",
    "/opt/ableton-wine/bin/wine",
    "wine",
)

# Relative (to drive_c) locations where a vendor's data may live.
VENDOR_DATA_RELS = (
    "ProgramData/{vendor}",
    "ProgramData/{vendor}SC",
    "Program Files/{vendor}",
    "Program Files/Common Files/{vendor}",
)

# Registry subtrees (relative to the hive root) to scan for vendor keys.
VENDOR_REG_SUBTREES = (
    "Software\\{vendor}",
    "Software\\WOW6432Node\\{vendor}",
)


@dataclass
class LinkResult:
    """What ``plugins link`` did."""

    vendor: str
    source_prefix: Path
    target_prefixes: list[Path]
    data_dirs: list[tuple[Path, Path]] = field(default_factory=list)  # (src, target)
    registry_keys: list[tuple[Path, str, str, str]] = field(default_factory=list)  # (prefix, key, name, value)
    dry_run: bool = False


def syntropia_prefixes(home: Path | None = None) -> list[Path]:
    """Every wine prefix under ~/.local/share/syntropia/prefixes."""
    if home is None:
        home = Path(os.path.expanduser("~"))
    root = home / ".local" / "share" / "syntropia" / "prefixes"
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if (p / "drive_c").is_dir())


def resolve_wine(prefix: Path) -> str | None:
    """Return a wine binary that can talk to *prefix*, or None.

    Prefers the custom syntropia/ableton wine builds (the prefixes are
    provisioned with them); falls back to system wine. Each candidate
    is probed against the prefix so a running mismatched wineserver
    (the classic "version mismatch 956/848" error) is avoided.
    """
    env = {"WINEPREFIX": str(prefix)}
    for cand in WINE_CANDIDATES:
        if not shutil.which(cand) and not Path(cand).exists():
            continue
        probe = run_command([cand, "cmd", "/c", "ver"], env=env)
        output = (probe.stdout or "") + (probe.stderr or "")
        if probe.returncode == 0 and "version mismatch" not in output.lower():
            return cand
    return None


def find_vendor_data(prefix: Path, vendor: str) -> list[Path]:
    """Data directories for *vendor* inside *prefix*'s drive_c."""
    drive_c = prefix / "drive_c"
    found: list[Path] = []
    for rel in VENDOR_DATA_RELS:
        path = drive_c / rel.format(vendor=vendor)
        if path.exists():
            found.append(path)
    return found


def parse_vendor_registry(prefix: Path, vendor: str) -> dict[str, dict[str, str]]:
    """Parse *prefix*'s system.reg for ``Software\\<Vendor>`` keys.

    Returns ``{full_key: {name: value}}`` with Windows-style (single
    backslash) key paths and unescaped values, e.g.
    ``{"Software\\Arturia\\Bus EXCITER-104": {"installdir": "C:\\ProgramData\\..."}}``.
    """
    system_reg = prefix / "system.reg"
    if not system_reg.is_file():
        return {}
    vendor_l = vendor.lower()
    result: dict[str, dict[str, str]] = {}
    current_key: str | None = None
    for line in system_reg.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith("[") and "]" in line:
            # Lines look like: [Software\\Vendor] 1753983202
            # (a trailing registry timestamp follows the closing bracket).
            raw = line[1 : line.index("]")]
            # system.reg stores keys with escaped backslashes: Software\\Vendor
            key = raw.replace("\\\\", "\\")
            if _is_vendor_key(key, vendor_l):
                current_key = key
                result.setdefault(key, {})
            else:
                current_key = None
        elif current_key is not None and line.startswith('"') and "=" in line:
            name, _, value = line[1:].partition('"="')
            if name and value.endswith('"'):
                value = value[:-1].replace("\\\\", "\\")
                result[current_key][name] = value
    return result


def _is_vendor_key(key: str, vendor_l: str) -> bool:
    """True if *key* is ``Software\\<vendor>`` or a subkey thereof."""
    key_l = key.lower()
    for base in (f"software\\{vendor_l}", f"software\\wow6432node\\{vendor_l}"):
        if key_l == base or key_l.startswith(base + "\\"):
            return True
    return False


def _read_hklm(prefix: Path) -> dict[str, dict[str, str]]:
    """Parse the prefix's whole system.reg into ``{key: {name: value}}``.

    Reading the text file directly is far faster than a ``wine reg query``
    per key (no wine startup per call) and is how the existence check
    avoids clobbering an already-configured prefix.
    """
    system_reg = prefix / "system.reg"
    if not system_reg.is_file():
        return {}
    result: dict[str, dict[str, str]] = {}
    current_key: str | None = None
    for line in system_reg.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith("[") and "]" in line:
            current_key = line[1 : line.index("]")].replace("\\\\", "\\")
            result.setdefault(current_key, {})
        elif current_key is not None and line.startswith('"') and "=" in line:
            name, _, value = line[1:].partition('"="')
            if name and value.endswith('"'):
                result[current_key][name] = value[:-1].replace("\\\\", "\\")
    return result


def _reg_add(
    prefix: Path,
    key: str,
    name: str,
    value: str,
    existing: dict[str, dict[str, str]] | None = None,
) -> None:
    """Add a REG_SZ value under HKLM in *prefix* using its own wine.

    Only *adds*: if the value already exists it is left untouched, so a
    previously-configured prefix (or a prefix whose source registry has
    odd values) is never clobbered. *existing* is the parsed system.reg
    (pass it in to avoid re-reading per key); if absent it is read once.
    """
    if existing is None:
        existing = _read_hklm(prefix)
    if name in existing.get(key, {}):
        return
    wine = resolve_wine(prefix)
    if wine is None:
        raise PluginsError(
            f"no compatible wine found for prefix {prefix} — "
            "install wine or the syntropia wine builds first"
        )
    result = run_command(
        [wine, "reg", "add", f"HKLM\\{key}", "/v", name, "/d", value, "/f"],
        env={"WINEPREFIX": str(prefix)},
    )
    if result.returncode != 0:
        raise PluginsError(
            f"wine reg add {key}\\{name} in {prefix} failed: "
            f"{result.stdout.strip() or result.stderr.strip()}"
        )


def link_vendor_data(
    vendor: str,
    source_prefix: Path,
    target_prefixes: list[Path] | None = None,
    home: Path | None = None,
    dry_run: bool = False,
) -> LinkResult:
    """Wire *vendor*'s data + registry from *source_prefix* into DAW prefixes.

    For each target prefix: symlink the vendor's data directories (no
    copy — Arturia's is 5.8 GB) and add the vendor's ``installdir``
    registry keys under HKLM using that prefix's own wine.
    """
    vendor = vendor.strip()
    if not vendor:
        raise PluginsError("vendor name must not be empty")
    if target_prefixes is None:
        target_prefixes = syntropia_prefixes(home)

    data_dirs = find_vendor_data(source_prefix, vendor)
    registry = parse_vendor_registry(source_prefix, vendor)
    if not data_dirs and not registry:
        raise PluginsError(
            f"no '{vendor}' data or registry keys found in {source_prefix}"
        )

    result = LinkResult(
        vendor=vendor,
        source_prefix=source_prefix,
        target_prefixes=target_prefixes,
        dry_run=dry_run,
    )

    for target in target_prefixes:
        drive_c = target / "drive_c"
        if not drive_c.is_dir():
            continue
        # Read the target's registry once (fast; avoids a wine start per key).
        existing = _read_hklm(target) if not dry_run else None
        # Symlink data dirs.
        for src in data_dirs:
            rel = src.relative_to(source_prefix / "drive_c")
            dest = drive_c / rel
            if dest.is_symlink() and dest.resolve() == src.resolve():
                continue  # already linked
            result.data_dirs.append((src, dest))
            if not dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                if dest.exists() or dest.is_symlink():
                    dest.unlink()
                dest.symlink_to(src, target_is_directory=src.is_dir())
        # Add registry keys (only the missing ones).
        for key, values in registry.items():
            for name, value in values.items():
                if existing is not None and name in existing.get(key, {}):
                    continue  # already present — don't clobber
                result.registry_keys.append((target, key, name, value))
                if not dry_run:
                    _reg_add(target, key, name, value, existing=existing)

    return result
