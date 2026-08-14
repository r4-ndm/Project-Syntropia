"""syntropia vendor data linking — Arturia-class plugin support.

Some Windows plugin vendors (Arturia, Native Instruments, …) split an
install across a data directory (``C:\\ProgramData\\<Vendor>``) and an
``installdir`` registry key. Bitwig works without extra wiring because
yabridge runs the plugin inside its *home* prefix, where the data
lives. A wine-hosted DAW like Ableton runs the plugin in *its own*
prefix, so the data dir and registry keys must be linked in —
exactly what ``syntropia plugins link --data <Vendor>`` does.

Only ever *adds*: data dirs are symlinked (never copied) and missing
``installdir`` registry values are added with the prefix's own wine.
Existing values are never clobbered, so re-running is safe.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .brew import WINE_BUILD_BIN_DIRS
from syntropia.process import run_command


class VendorError(Exception):
    """Vendor data linking failed."""


# Wine binaries to try, in order, when writing to a wine prefix.
# Derived from brew.WINE_BUILD_BIN_DIRS so a new wine build is one row
# in that table (plus system wine as the final fallback).
WINE_CANDIDATES = tuple(f"{directory}/wine" for directory in WINE_BUILD_BIN_DIRS.values()) + ("wine",)

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
        raise VendorError(
            f"no compatible wine found for prefix {prefix} — "
            "install wine or the syntropia wine builds first"
        )
    result = run_command(
        [wine, "reg", "add", f"HKLM\\{key}", "/v", name, "/d", value, "/f"],
        env={"WINEPREFIX": str(prefix)},
    )
    if result.returncode != 0:
        raise VendorError(
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
        raise VendorError("vendor name must not be empty")
    if target_prefixes is None:
        target_prefixes = syntropia_prefixes(home)

    data_dirs = find_vendor_data(source_prefix, vendor)
    registry = parse_vendor_registry(source_prefix, vendor)
    if not data_dirs and not registry:
        raise VendorError(
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
