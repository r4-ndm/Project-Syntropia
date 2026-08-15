"""Uninstall a brew: remove its Wine prefix and every file it left behind.

A Wine install scatters artifacts far beyond the prefix directory —
desktop files, kill scripts, extracted icon frames, ``winemenubuilder``
entries, a MIME protocol handler, and Cinnamon taskbar/menu pins. This
module sweeps them all so ``syntropia uninstall`` leaves nothing behind.

Each step is a small, independently testable function; :func:`uninstall_brew`
is the orchestrator that runs them in order and collects the removed items
for the final summary.
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import signal
from pathlib import Path

from syntropia.process import scan_processes

from .brew import Brew, slugify_name


def kill_prefix_holders(prefix: Path) -> int:
    """Kill every process whose WINEPREFIX or cmdline references *prefix*.

    ``wineserver -k`` alone leaves orphaned children (winedevice.exe etc.)
    that keep a zombie launcher on the taskbar's window list, so scan
    ``/proc`` directly and SIGKILL anything bound to the prefix.
    """
    prefix_str = str(prefix)
    killed = 0
    for pid, environ, cmdline in scan_processes():
        if f"WINEPREFIX={prefix_str}" in environ or prefix_str in cmdline:
            try:
                os.kill(pid, signal.SIGKILL)
                killed += 1
            except (ProcessLookupError, PermissionError):
                pass
    return killed


def remove_prefix(prefix: Path) -> list[str]:
    """Delete the Wine prefix directory, if present."""
    if prefix.exists():
        shutil.rmtree(prefix, ignore_errors=True)
        return [str(prefix)]
    return []


def remove_desktop_files(home: Path, slug: str) -> list[str]:
    """Remove the brew's launcher desktop file."""
    cand = home / ".local/share/applications" / f"{slug}.desktop"
    if cand.exists():
        cand.unlink()
        return [str(cand)]
    return []


def remove_kill_scripts(home: Path, slug: str) -> list[str]:
    """Remove the brew's helper kill script."""
    cand = home / ".local/bin" / f"{slug}-kill"
    if cand.exists():
        cand.unlink()
        return [str(cand)]
    return []


def remove_launcher(home: Path, slug: str) -> list[str]:
    """Remove the brew's launcher script (``~/.local/bin/<slug>``)."""
    cand = home / ".local/bin" / slug
    if cand.exists():
        cand.unlink()
        return [str(cand)]
    return []


def remove_icons(home: Path, slug: str) -> list[str]:
    """Remove the brew's icons, including straggler frames from ICO extraction."""
    icon_dir = home / ".local/share/icons/hicolor/256x256/apps"
    removed: list[str] = []
    for pattern in (f"{slug}.png", f"{slug}-*.png"):
        for icon in sorted(glob.glob(str(icon_dir / pattern))):
            Path(icon).unlink()
            removed.append(icon)
    return removed


def remove_wine_menu_entries(home: Path, prefix: Path, slug: str) -> list[str]:
    """Remove winemenubuilder entries that reference this brew's prefix.

    ``winemenubuilder.exe`` drops ``.desktop`` entries under
    ``applications/wine/`` whose ``Exec=``/``Path=`` point inside the prefix.
    Also deletes the hashed icons those entries referenced and prunes
    now-empty directories.
    """
    wine_apps = home / ".local/share/applications/wine"
    if not wine_apps.exists():
        return []
    icons_root = home / ".local/share/icons/hicolor"
    removed: list[str] = []

    for cand in sorted(wine_apps.rglob("*.desktop")):
        try:
            text = cand.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if str(prefix) not in text and f"{slug}.desktop" not in text:
            continue
        cand.unlink(missing_ok=True)
        removed.append(str(cand))
        for line in text.splitlines():
            if line.startswith("Icon=") and line.strip() != "Icon=":
                icon_name = line[5:].strip().rstrip("\r")
                for icon_hit in glob.glob(
                    str(icons_root / "*" / "apps" / f"{icon_name}.png")
                ):
                    Path(icon_hit).unlink(missing_ok=True)
                    removed.append(icon_hit)

    # Prune empty dirs left behind by the sweep, deepest first.
    for empty in sorted(
        (d for d in wine_apps.rglob("*") if d.is_dir() and not any(d.iterdir())),
        key=lambda p: -len(p.parts),
    ):
        empty.rmdir()

    return removed


def remove_wine_protocol(home: Path, slug: str) -> list[str]:
    """Remove the brew's ``wine-protocol-<name>.desktop`` MIME handler."""
    protocol_file = home / ".local/share/applications" / f"wine-protocol-{slug}.desktop"
    if protocol_file.exists():
        protocol_file.unlink()
        return [str(protocol_file)]
    return []


def clean_cinnamon_configs(home: Path, slug: str, brew_name: str) -> list[str]:
    """Strip the brew from Cinnamon taskbar/menu JSON configs.

    The panel's grouped-window-list pins launchers and Cinnamenu keeps a
    recent-apps list — both store ``.desktop`` names in JSON, so dead entries
    survive file deletion and keep an icon pinned. Rewrites any config that
    references the brew's slug or name.
    """
    spices_dir = home / ".config/cinnamon/spices"
    if not spices_dir.exists():
        return []
    cleaned: list[str] = []

    for cfg in sorted(spices_dir.rglob("*.json")):
        try:
            raw = cfg.read_text(encoding="utf-8", errors="replace")
            data = json.loads(raw)
        except (OSError, ValueError):
            continue
        changed = False

        def _strip_app(refs: list) -> list:
            nonlocal changed
            kept = []
            for ref in refs:
                ref_s = str(ref)
                if (
                    ref_s == f"{slug}.desktop"
                    or f"wine-Programs-{slug}" in ref_s.replace(" ", "-").lower()
                    or any(x in ref_s.lower() for x in (slug, brew_name.lower()))
                ):
                    changed = True
                    continue
                kept.append(ref)
            return kept

        def _walk(node) -> None:
            if isinstance(node, dict):
                for key, value in node.items():
                    if isinstance(value, list):
                        node[key] = _strip_app(value)
                    else:
                        _walk(value)
            elif isinstance(node, list):
                for item in node:
                    _walk(item)

        _walk(data)
        if changed:
            cfg.write_text(json.dumps(data, indent=4), encoding="utf-8")
            cleaned.append(str(cfg))

    return cleaned


def uninstall_brew(
    brew: Brew,
    *,
    home: Path | None = None,
    echo=print,
) -> list[str]:
    """Remove *brew*'s Wine prefix and every file it left behind.

    *echo* is the output callable (``click.echo`` from the CLI layer, or
    ``print`` for standalone use). Returns the list of removed items for the
    caller's final summary.
    """
    if home is None:
        home = Path.home()
    slug = slugify_name(brew.name)
    prefix = Path(brew.wine_prefix).expanduser()
    removed: list[str] = []

    killed = kill_prefix_holders(prefix)
    echo(f"  killed {killed} wine process(es) for {prefix}")

    if prefix.exists():
        removed.extend(remove_prefix(prefix))
        echo(f"  removed prefix {prefix}")
    else:
        echo(f"  prefix already absent: {prefix}")

    for cand in remove_desktop_files(home, slug):
        removed.append(cand)
        echo(f"  removed {cand}")

    for cand in remove_kill_scripts(home, slug):
        removed.append(cand)
        echo(f"  removed {cand}")

    for cand in remove_launcher(home, slug):
        removed.append(cand)
        echo(f"  removed {cand}")

    for icon in remove_icons(home, slug):
        removed.append(icon)
        echo(f"  removed icon {icon}")

    for cand in remove_wine_menu_entries(home, prefix, slug):
        removed.append(cand)
        echo(f"  removed wine menu entry {cand}")

    for cand in remove_wine_protocol(home, slug):
        removed.append(cand)
        echo(f"  removed {cand}")

    cinnamon = clean_cinnamon_configs(home, slug, brew.name)
    for cfg in cinnamon:
        echo(f"  removed {brew.name} from {cfg}")
    if cinnamon:
        removed.append(f"{len(cinnamon)} cinnamon config(s)")

    return removed
