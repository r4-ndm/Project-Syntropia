"""Syntropia brew inventory — what's installed on this machine, and where.

A pure, testable module that scans the known Syntropia locations and
returns structured inventory data for the GUI (and any future consumer):

* installed Windows apps  — Wine prefixes under ~/.local/share/syntropia/prefixes/
* Windows VST3 plugins    — the drop folder (~/VST3) and their yabridge stubs
* native Linux VST3s      — ~/.vst3 (excluding the yabridge stub dir)
* registry brews          — the installable manifests in the local registry

Every function takes explicit paths (defaulting to the real locations) so
tests can point them at scratch directories. No function here executes
install/uninstall or mutates anything — the GUI calls the existing CLI
engine for those.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .brew import BrewError, find_brews, load_brew

DEFAULT_PREFIX_DIR = "~/.local/share/syntropia/prefixes"
DEFAULT_DROP_DIR = "~/VST3"
DEFAULT_LINUX_VST3_DIR = "~/.vst3"
DEFAULT_REGISTRY = "~/.config/syntropia/brews"


def _expand(path: str | Path) -> Path:
    return Path(os.path.expanduser(str(path)))


# ── Dataclasses ------------------------------------------------------------

@dataclass
class InstalledApp:
    """One installed Windows app: a Wine prefix under the prefixes dir."""

    name: str
    prefix_path: Path
    # Resolved .brew manifest in the registry, if one matches this app.
    brew: Path | None = None
    # Approximate on-disk size of the prefix in bytes (0 if unknown).
    size_bytes: int = 0

    @property
    def location(self) -> str:
        return str(self.prefix_path)


@dataclass
class WindowsPlugin:
    """One Windows VST in the drop folder, with its bridge state."""

    name: str
    path: Path
    # True when yabridge has produced a Linux stub for it.
    bridged: bool = False
    stub_path: Path | None = None

    @property
    def location(self) -> str:
        return str(self.path)


@dataclass
class LinuxPlugin:
    """One native Linux VST3 under ~/.vst3 (yabridge stubs excluded)."""

    name: str
    path: Path

    @property
    def location(self) -> str:
        return str(self.path)


@dataclass
class RegistryBrew:
    """One installable brew manifest in the local registry."""

    name: str
    path: Path
    category: str = ""
    version: str = ""
    description: str = ""

    @property
    def location(self) -> str:
        return str(self.path)


@dataclass
class Inventory:
    """The full picture, as the GUI shows it."""

    installed_apps: list[InstalledApp] = field(default_factory=list)
    windows_plugins: list[WindowsPlugin] = field(default_factory=list)
    linux_plugins: list[LinuxPlugin] = field(default_factory=list)
    registry_brews: list[RegistryBrew] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {
            "apps": len(self.installed_apps),
            "windows_vsts": len(self.windows_plugins),
            "linux_vsts": len(self.linux_plugins),
            "brews": len(self.registry_brews),
        }


# ── Scanners ---------------------------------------------------------------

def _dir_size(path: Path) -> int:
    """Best-effort recursive size of *path* in bytes (0 on any failure)."""
    total = 0
    try:
        for root, dirs, files in os.walk(path):
            for name in files:
                try:
                    total += (Path(root) / name).stat().st_size
                except OSError:
                    pass
    except OSError:
        return 0
    return total


def scan_installed_apps(
    prefix_dir: str | Path = DEFAULT_PREFIX_DIR,
    registry: str | Path = DEFAULT_REGISTRY,
    *,
    with_sizes: bool = False,
) -> list[InstalledApp]:
    """Scan Wine prefixes (one directory each = one installed Windows app).

    A prefix dir is counted as an app when it contains a ``drive_c`` (a
    provisioned Wine prefix). The matching registry brew (by slug) is
    attached when present, so the GUI can offer reinstall/uninstall.
    """
    root = _expand(prefix_dir)
    reg = _expand(registry)
    apps: list[InstalledApp] = []

    if not root.is_dir():
        return apps

    # Match manifests by their own [wine] prefix path — the authoritative
    # link (the manifest declares exactly where its prefix lives, e.g.
    # "~/.local/share/syntropia/prefixes/ableton"). Name heuristics would
    # guess at dir-name vs manifest-name differences.
    brew_for_prefix: dict[Path, Path] = {}
    for brew_file in find_brews(reg):
        try:
            brew = load_brew(brew_file)
        except BrewError:
            continue
        declared = _expand(brew.wine_prefix)
        if declared.is_absolute():
            brew_for_prefix[declared] = brew_file
        else:
            brew_for_prefix[root / declared] = brew_file

    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        # A provisioned Wine prefix has drive_c; skip stray dirs.
        if not (entry / "drive_c").is_dir():
            continue
        name = entry.name
        brew_path = brew_for_prefix.get(entry.resolve())
        size = _dir_size(entry) if with_sizes else 0
        apps.append(InstalledApp(name=name, prefix_path=entry, brew=brew_path, size_bytes=size))
    return apps


def scan_windows_plugins(
    drop_dir: str | Path = DEFAULT_DROP_DIR,
    linux_vst3_dir: str | Path = DEFAULT_LINUX_VST3_DIR,
) -> list[WindowsPlugin]:
    """Scan the Windows VST drop folder and report bridge state.

    The stub dir is ``~/.vst3/yabridge``; a plugin is bridged when its
    stub exists there. yabridge names stubs after the plugin (bundles get
    a directory of the same name), so we compare by name.
    """
    drop = _expand(drop_dir)
    stub_root = _expand(linux_vst3_dir) / "yabridge"
    plugins: list[WindowsPlugin] = []

    if not drop.is_dir():
        return plugins

    suffixes = (".vst3", ".dll", ".clap")
    for entry in sorted(drop.iterdir()):
        is_plugin = (
            entry.is_file() and entry.suffix.lower() in suffixes
        ) or (
            entry.is_dir() and entry.name.lower().endswith(".vst3")
        )
        if not is_plugin:
            continue
        stub = stub_root / entry.name
        plugins.append(
            WindowsPlugin(
                name=entry.name,
                path=entry,
                bridged=stub.exists(),
                stub_path=stub if stub.exists() else None,
            )
        )
    return plugins


def scan_linux_plugins(
    linux_vst3_dir: str | Path = DEFAULT_LINUX_VST3_DIR,
) -> list[LinuxPlugin]:
    """Scan native Linux VST3s under ~/.vst3, excluding the yabridge stubs."""
    root = _expand(linux_vst3_dir)
    plugins: list[LinuxPlugin] = []

    if not root.is_dir():
        return plugins

    for entry in sorted(root.iterdir()):
        if entry.name == "yabridge":  # bridge stubs, not native plugins
            continue
        if entry.is_dir() and entry.name.lower().endswith(".vst3"):
            plugins.append(LinuxPlugin(name=entry.name, path=entry))
    return plugins


def scan_registry(
    registry: str | Path = DEFAULT_REGISTRY,
) -> list[RegistryBrew]:
    """Scan the local registry for installable brew manifests."""
    reg = _expand(registry)
    brews: list[RegistryBrew] = []

    for brew_file in find_brews(reg):
        try:
            brew = load_brew(brew_file)
        except BrewError:
            # A manifest that fails to parse is still listed (the GUI can
            # show it as broken); never crash the whole inventory on it.
            brews.append(
                RegistryBrew(
                    name=brew_file.stem,
                    path=brew_file,
                    description="(manifest fails to parse)",
                )
            )
            continue
        brews.append(
            RegistryBrew(
                name=brew.name,
                path=brew_file,
                category=brew.category,
                version=brew.version,
            )
        )
    return sorted(brews, key=lambda b: b.name.lower())


def scan_all(
    prefix_dir: str | Path = DEFAULT_PREFIX_DIR,
    drop_dir: str | Path = DEFAULT_DROP_DIR,
    linux_vst3_dir: str | Path = DEFAULT_LINUX_VST3_DIR,
    registry: str | Path = DEFAULT_REGISTRY,
    *,
    with_sizes: bool = False,
) -> Inventory:
    """Scan everything at once — one call the GUI uses at startup."""
    return Inventory(
        installed_apps=scan_installed_apps(prefix_dir, registry, with_sizes=with_sizes),
        windows_plugins=scan_windows_plugins(drop_dir, linux_vst3_dir),
        linux_plugins=scan_linux_plugins(linux_vst3_dir),
        registry_brews=scan_registry(registry),
    )
