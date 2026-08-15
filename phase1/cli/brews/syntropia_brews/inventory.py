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
import re
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
class WindowsProgram:
    """One program installed *inside* a Wine prefix.

    Read from the prefix registry's Add/Remove Programs entries, so it
    reflects what the Windows installer actually registered — not just
    the prefix directory name.
    """

    name: str
    prefix_path: Path
    # The Uninstall subkey name (usually a GUID) — what ``wine uninstaller
    # --remove`` accepts to run that program's own uninstaller.
    registry_key: str = ""
    version: str = ""
    publisher: str = ""
    # Windows InstallLocation path, e.g. ``C:\\Program Files\\Arturia``.
    location: str = ""
    uninstall_string: str = ""
    # The brew manifest's [wine] version for this prefix ("" = system wine),
    # so a custom build (ableton-wine) can be resolved when uninstalling.
    wine_version: str = ""


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
    windows_programs: list[WindowsProgram] = field(default_factory=list)
    windows_plugins: list[WindowsPlugin] = field(default_factory=list)
    linux_plugins: list[LinuxPlugin] = field(default_factory=list)
    registry_brews: list[RegistryBrew] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {
            "apps": len(self.installed_apps),
            "windows_programs": len(self.windows_programs),
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


# ── Windows program discovery (prefix registry) ----------------------------

# Top-level Add/Remove Programs keys, per hive. Keys are written with each
# backslash doubled (Wine's text registry escapes '\'); we match the unescaped
# path so both the 64-bit and WOW6432Node hives resolve to the same check.
_HKLM_UNINSTALL = (
    r"Software\Microsoft\Windows\CurrentVersion\Uninstall",
    r"Software\Wow6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
)

# Entries whose ReleaseType marks them as a patch/update, not an app — the
# same filter Windows' own Add/Remove Programs applies.
_SKIP_RELEASE_TYPES = {"update", "hotfix", "security update", "service pack"}

# Noise every Wine prefix ships: Wine's own Mono/Gecko support components and
# MSVC redistributables. Neither is a user-facing app, so hiding them keeps
# the list focused on what was actually installed on top.
_SKIP_PUBLISHERS = {"the wine project"}
_SKIP_NAME_PREFIXES = ("microsoft visual c++",)

_VALUE_RE = re.compile(r'^"([^"]+)"=(.*)$')


def _section_key(line: str) -> str | None:
    """Return the unescaped registry key path for a section-header line.

    ``[Software\\Microsoft\\...]`` -> ``Software\\Microsoft\\...``. Returns
    ``None`` when the line is not a section header.
    """
    line = line.strip()
    if not line.startswith("[") or "]" not in line:
        return None
    return line[1 : line.index("]")].replace("\\\\", "\\")


def _parse_value(line: str) -> tuple[str, str]:
    """Parse one ``"Name"="value"`` (or typed) registry line -> (name, value).

    Non-string values (dword/hex) return an empty value — the Uninstall
    fields we surface are all strings.
    """
    m = _VALUE_RE.match(line)
    if not m:
        return "", ""
    name = m.group(1)
    raw = m.group(2).strip()
    if raw.startswith('"'):
        body = raw[1:]
        if body.endswith('"'):
            body = body[:-1]
        return name, body.replace('\\"', '"').replace("\\\\", "\\")
    if ":" in raw:
        payload = raw.partition(":")[2].strip()
        if payload.startswith('"') and payload.endswith('"'):
            return name, payload[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    return name, ""


def _collect_uninstall(
    programs: list[WindowsProgram],
    lines: list[str],
    prefix: Path,
    wine_version: str,
    seen: set[str],
) -> None:
    """Extract Add/Remove Programs entries from one registry file's lines."""
    current_key = ""
    current: dict[str, str] = {}
    is_system_component = False

    def flush() -> None:
        nonlocal current, is_system_component
        name = current.get("DisplayName", "")
        if (
            name
            and not is_system_component
            and "ParentKeyName" not in current
            and current.get("ReleaseType", "").lower() not in _SKIP_RELEASE_TYPES
            and current.get("Publisher", "").strip().lower() not in _SKIP_PUBLISHERS
            and not any(name.lower().startswith(p) for p in _SKIP_NAME_PREFIXES)
            and name not in seen
        ):
            seen.add(name)
            programs.append(
                WindowsProgram(
                    name=name,
                    prefix_path=prefix,
                    registry_key=current_key,
                    version=current.get("DisplayVersion", ""),
                    publisher=current.get("Publisher", ""),
                    location=current.get("InstallLocation", ""),
                    uninstall_string=current.get("UninstallString", ""),
                    wine_version=wine_version,
                )
            )
        current = {}
        is_system_component = False

    for line in lines:
        if line.startswith("["):
            flush()
            key = _section_key(line)
            current_key = ""
            if key is not None:
                for base in _HKLM_UNINSTALL:
                    if key.startswith(base + "\\"):
                        name = key[len(base) + 1 :]
                        # A subkey (e.g. {GUID}\variables) still has a
                        # backslash in its name — only the entry key itself
                        # is a plain component.
                        if name and "\\" not in name:
                            current_key = name
                        break
            continue
        if not current_key:
            continue
        if line.startswith('"SystemComponent"=dword:'):
            is_system_component = True
            continue
        name, value = _parse_value(line)
        if name:
            current[name] = value
    flush()


def scan_windows_programs(
    prefix_dir: str | Path = DEFAULT_PREFIX_DIR,
    wine_versions: dict[str, str] | None = None,
) -> list[WindowsProgram]:
    """List the programs installed inside each Wine prefix.

    Reads each provisioned prefix's ``system.reg`` and ``user.reg`` and
    collects the top-level Add/Remove Programs entries (64-bit and
    WOW6432Node hives). System components, patches, and child update keys
    are skipped, mirroring Windows' own Add/Remove Programs filter.
    """
    root = _expand(prefix_dir)
    versions = wine_versions or {}
    programs: list[WindowsProgram] = []

    if not root.is_dir():
        return programs

    for prefix in sorted(root.iterdir()):
        if not prefix.is_dir() or not (prefix / "drive_c").is_dir():
            continue
        seen: set[str] = set()  # dedupe across hives and registry files
        wine_version = versions.get(str(prefix), "")
        for reg_file in (prefix / "system.reg", prefix / "user.reg"):
            if not reg_file.is_file():
                continue
            try:
                lines = reg_file.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            _collect_uninstall(programs, lines, prefix, wine_version, seen)
    return programs


def windows_location_to_host(prefix: Path, location: str) -> Path | None:
    """Map a Windows install path to its host filesystem location.

    ``C:\\Program Files\\Arturia`` -> ``<prefix>/drive_c/Program Files/Arturia``.
    Returns ``None`` when *location* is not a rooted drive path.
    """
    norm = location.strip().replace("\\", "/")
    m = re.match(r"^([A-Za-z]):/?(.*)$", norm)
    if not m:
        return None
    return prefix / f"drive_{m.group(1).lower()}" / m.group(2)


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
    apps = scan_installed_apps(prefix_dir, registry, with_sizes=with_sizes)
    # Carry each prefix's wine version (from its brew manifest) into the
    # program scan, so the GUI can resolve a custom build (ableton-wine)
    # when it runs a program's uninstaller.
    wine_versions: dict[str, str] = {}
    for app in apps:
        if app.brew is None:
            continue
        try:
            wine_versions[str(app.prefix_path)] = load_brew(app.brew).wine_version
        except BrewError:
            continue
    return Inventory(
        installed_apps=apps,
        windows_programs=scan_windows_programs(prefix_dir, wine_versions),
        windows_plugins=scan_windows_plugins(drop_dir, linux_vst3_dir),
        linux_plugins=scan_linux_plugins(linux_vst3_dir),
        registry_brews=scan_registry(registry),
    )
