"""Syntropia CLI — entry point for the living computer's package manager."""

from __future__ import annotations

import os
import re
from pathlib import Path

import click

from .brew import BrewError, brew_filename, find_brews, lint_brew, load_brew, registry_brew_is_stale, resolve_brew, save_brew
from .plugins import PluginsError, drop_folder, ensure_drop_folder, stub_for, sync_plugins
from .vendor import VendorError, link_vendor_data
from .progress import StepProgress
from .registry import RegistryError, submit_brew
from .transform import TransformError, run_transform
from .update import UpdateError, run_update
from .wine_helper import STEP_LABELS, WineHelperError, WineInstaller

DEFAULT_REGISTRY = "~/.config/syntropia/brews"

DEFAULT_BRANDING_DIR = "/usr/share/syntropia/branding"


def _registry_path(registry: str) -> str:
    return os.path.expanduser(registry)


def _cli_version() -> str:
    """Resolve the package version in any install context.

    A PEP 660 editable install loads ``syntropia`` through a finder that
    does not execute ``__init__.py``, so ``from . import __version__``
    fails there (the root module has no attributes). Read the source file
    instead — the same mechanism the PKGBUILD's ``pkgver()`` uses — which
    works for editable installs, site-packages, and bare checkouts alike.
    """
    try:
        text = Path(__file__).resolve().with_name("__init__.py").read_text(encoding="utf-8")
    except OSError:
        return "0.0.0"
    match = re.search(r'^__version__ = "([^"]+)"', text, re.MULTILINE)
    return match.group(1) if match else "0.0.0"


@click.group()
@click.version_option(version=_cli_version(), prog_name="syntropia")
def cli() -> None:
    """Syntropia — install Windows DAWs and VSTs on CachyOS via Wine and yabridge."""


@cli.command()
@click.argument("brew", metavar="NAME_OR_FILE")
@click.option("--registry", default=DEFAULT_REGISTRY, show_default=True, help="Registry directory to resolve brew names against.")
@click.option("--check", is_flag=True, help="Dry-run: print the install plan, change nothing.")
@click.option("--yes", is_flag=True, help="Confirm: actually run the install.")
def install(brew: str, registry: str, check: bool, yes: bool) -> None:
    """Install a Windows DAW/VST from a .brew manifest (Wine + yabridge).

    NAME_OR_FILE is a .brew file path, or a brew name resolved from the
    registry (AUR-style: ``syntropia install surge``).

    Test systems only — see agent-rules/transform-safety.md. Run --check
    first, then confirm with --yes.
    """
    brew_file = resolve_brew(brew, registry)
    if brew_file is None:
        raise click.ClickException(
            f"no brew named '{brew}' in {_registry_path(registry)} — "
            f"run 'syntropia save <file>.brew' to add it, or 'syntropia list-brews'"
        )
    try:
        brew = load_brew(brew_file)
    except BrewError as exc:
        raise click.ClickException(str(exc)) from exc

    # Hint when the registry copy has drifted from the repo's phase1/brews:
    # the manifest being run is stale until `syntropia save` refreshes it.
    registry_dir = Path(registry).expanduser().resolve()
    if brew_file.resolve().parent == registry_dir:
        stale = registry_brew_is_stale(brew_file)
        if stale is not None:
            click.echo(
                click.style(
                    f"⚠️  registry copy of {brew_file.name} differs from {stale} — "
                    f"refresh it with 'syntropia save {stale}'",
                    fg="yellow",
                )
            )

    # Fail fast on formatting problems before touching wine / the prefix.
    problems = lint_brew(brew_file)
    if problems:
        raise click.ClickException(
            f"brew {brew_file} fails lint:\n  " + "\n  ".join(problems)
        )

    if not check and not yes:
        raise click.ClickException(
            "install provisions Wine prefixes — pass --yes to confirm "
            "(read agent-rules/transform-safety.md first)"
        )

    steps: list[tuple[str, str]] = STEP_LABELS

    title = f"😈 Installing {brew.name} {brew.version}"

    try:
        installer = WineInstaller(brew, dry_run=check)
        with StepProgress(title, steps) as prog:
            installer.run_all(progress=prog)
    except WineHelperError as exc:
        raise click.ClickException(str(exc)) from exc


@cli.command()
@click.option("--check", is_flag=True, help="Dry-run: report what would change, change nothing.")
@click.option("--yes", is_flag=True, help="Confirm: actually apply the transform to this system.")
@click.option("--snapshot", "snapshot_desc", metavar="DESC", help="Create a snapper snapshot before applying.")
@click.option(
    "--branding-dir",
    "branding_dir",
    default=DEFAULT_BRANDING_DIR,
    show_default=True,
    metavar="DIR",
    help="Directory with amended assets (plymouth/, grub/, wallpaper.png).",
)
def transform(check: bool, yes: bool, snapshot_desc: str | None, branding_dir: str) -> None:
    """Turn this CachyOS system into Syntropia OS.

    Test systems only — see agent-rules/transform-safety.md. Run --check
    first, snapshot, then apply with --yes.
    """
    try:
        run_transform(
            check=check,
            yes=yes,
            snapshot_desc=snapshot_desc,
            branding_dir=branding_dir,
        )
    except TransformError as exc:
        raise click.ClickException(str(exc)) from exc


@cli.command("list-brews")
@click.option("--registry", default=DEFAULT_REGISTRY, show_default=True, help="Registry directory to scan.")
def list_brews(registry: str) -> None:
    """List available .brew manifests in the registry."""
    path = _registry_path(registry)
    brews = find_brews(path)
    if not brews:
        click.echo(f"No brews found in {path}")
        return
    click.echo(f"Brews in {path}:")
    for brew_path in brews:
        click.echo(f"  {brew_path.name}")


@cli.command()
@click.argument("term")
@click.option("--registry", default=DEFAULT_REGISTRY, show_default=True)
def search(term: str, registry: str) -> None:
    """Search brews by name, category, or maintainer."""
    path = _registry_path(registry)
    needle = term.lower()
    hits = 0
    for brew_path in find_brews(path):
        try:
            brew = load_brew(brew_path)
        except BrewError:
            continue
        haystack = " ".join([brew.name, brew.category, brew.maintainer]).lower()
        if needle in haystack:
            click.echo(f"  {brew_path.name}  —  {brew.name} ({brew.category})")
            hits += 1
    if not hits:
        click.echo(f"No brews matching '{term}' in {path}")


@cli.command()
@click.argument("brew", metavar="NAME_OR_FILE")
@click.option("--registry", default=DEFAULT_REGISTRY, show_default=True, help="Registry directory to resolve brew names against.")
def info(brew: str, registry: str) -> None:
    """Show full details of a .brew manifest (file path or registry name)."""
    brew_file = resolve_brew(brew, registry)
    if brew_file is None:
        raise click.ClickException(
            f"no brew named '{brew}' in {_registry_path(registry)} — run 'syntropia save <file>.brew' to add it"
        )
    try:
        brew = load_brew(brew_file)
    except BrewError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(click.style(f"{brew.name} {brew.version}", bold=True))
    click.echo(f"  category:    {brew.category}")
    click.echo(f"  maintainer:  {brew.maintainer}")
    click.echo(f"  wine:        {brew.wine_version} ({brew.wine_arch})")
    click.echo(f"  prefix:      {brew.wine_prefix}")
    if brew.wine_overrides:
        click.echo("  overrides:")
        for key, value in brew.wine_overrides.items():
            click.echo(f"    {key} = {value}")
    if brew.winetricks_packages:
        click.echo(f"  winetricks:  {', '.join(brew.winetricks_packages)}")
    click.echo(f"  yabridge:    {'enabled' if brew.yabridge_enabled else 'disabled'}")
    for plugin_dir in brew.plugin_dirs:
        click.echo(f"    plugin dir: {plugin_dir}")
    if brew.environment:
        click.echo("  environment:")
        for key, value in brew.environment.items():
            click.echo(f"    {key} = {value}")
    click.echo("  install steps:")
    for command in brew.install_commands:
        click.echo(f"    $ {command}")


@cli.command()
@click.argument("brew_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--registry", default=DEFAULT_REGISTRY, show_default=True, help="Registry directory to save into.")
def save(brew_file: str, registry: str) -> None:
    """Validate a .brew and save it into the registry (AUR-style local tree).

    Anyone can then install it by name from the registry; the shared,
    GitHub-hosted registry is the upstream for this local copy.
    """
    path = _registry_path(registry)
    try:
        brew = load_brew(brew_file)
        existed = (Path(path).expanduser() / brew_filename(brew)).exists()
        target = save_brew(brew, path)
    except BrewError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(
        click.style(f"✅ {'updated' if existed else 'saved'} {target.name} {brew.version}", fg="green")
    )
    click.echo(f"   {target}")
    click.echo(f"   share it: syntropia submit {target.stem}")


@cli.command()
@click.argument("name")
@click.option("--registry", default=DEFAULT_REGISTRY, show_default=True, help="Registry directory to resolve brew names against.")
@click.option("--yes", is_flag=True, help="Confirm: actually delete the prefix and files.")
def uninstall(name: str, registry: str, yes: bool) -> None:
    """Uninstall a brew: kill wineserver, remove prefix, desktop file, icon,
    and any straggler frames/leftovers from a previous install."""
    brew_file = resolve_brew(name, registry)
    if brew_file is None:
        raise click.ClickException(f"no brew named '{name}' in {_registry_path(registry)}")
    try:
        brew = load_brew(brew_file)
    except BrewError as exc:
        raise click.ClickException(str(exc)) from exc
    if not yes:
        raise click.ClickException(
            f"this will DELETE the Wine prefix at {brew.wine_prefix} "
            f"and all associated files -- pass --yes to confirm"
        )

    import glob as _glob
    import shutil
    import subprocess

    from .brew import slugify_name

    slug = slugify_name(brew.name)
    prefix = Path(brew.wine_prefix).expanduser()
    removed: list[str] = []

    # --- Kill ALL wine processes using this prefix ---
    # `wineserver -k` alone leaves orphaned children (winedevice.exe etc.) that
    # keep a zombie launcher on the taskbar's window list. Scan /proc for any
    # process whose WINEPREFIX or cmdline references the prefix and kill it.
    import os
    import signal as _signal

    prefix_str = str(prefix)
    killed = 0
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open(f"/proc/{pid}/environ", "rb") as fh:
                env_text = fh.read().decode("utf-8", errors="replace")
            with open(f"/proc/{pid}/cmdline", "rb") as fh:
                cmd_text = fh.read().decode("utf-8", errors="replace").replace("\0", " ")
        except OSError:
            continue
        if f"WINEPREFIX={prefix_str}" in env_text or prefix_str in cmd_text:
            try:
                os.kill(int(pid), _signal.SIGKILL)
                killed += 1
            except ProcessLookupError:
                pass
            except PermissionError:
                pass
    click.echo(f"  killed {killed} wine process(es) for {prefix}")

    # --- Remove prefix ---
    if prefix.exists():
        shutil.rmtree(prefix, ignore_errors=True)
        removed.append(str(prefix))
        click.echo(f"  removed prefix {prefix}")
    else:
        click.echo(f"  prefix already absent: {prefix}")

    # --- Remove desktop file ---
    desktop_dir = Path.home() / ".local/share/applications"
    for cand in (
        desktop_dir / f"{slug}.desktop",
        desktop_dir / "ableton-live-12.desktop",  # legacy hard-coded name
    ):
        if cand.exists():
            cand.unlink()
            removed.append(str(cand))
            click.echo(f"  removed {cand}")

    # --- Remove kill script ---
    for cand in (
        Path.home() / ".local/bin" / f"{slug}-kill",
        Path.home() / ".local/bin" / "ableton-kill",  # legacy
    ):
        if cand.exists():
            cand.unlink()
            removed.append(str(cand))
            click.echo(f"  removed {cand}")

    # --- Remove icons (base + straggler frames from ICO extraction) ---
    icon_dir = Path.home() / ".local/share/icons/hicolor/256x256/apps"
    for pattern in (f"{slug}.png", f"{slug}-*.png"):
        for icon in sorted(_glob.glob(str(icon_dir / pattern))):
            Path(icon).unlink()
            removed.append(icon)
            click.echo(f"  removed icon straggler {icon}")

    # --- Legacy icon sweep (pre-slugify era) ---
    for legacy_pattern in ("ableton-live-12.png", "ableton-live-12-*.png"):
        for icon in sorted(_glob.glob(str(icon_dir / legacy_pattern))):
            Path(icon).unlink()
            removed.append(icon)
            click.echo(f"  removed legacy icon {icon}")

    # --- Wine menu stragglers (winemenubuilder entries) ---
    # winemenubuilder.exe drops .desktop entries under applications/wine/ that
    # reference the brew's prefix directly (Exec=/Path= point inside it) plus a
    # wine-protocol-<name>.desktop and hashed icons under hicolor. Sweep any
    # desktop file whose contents mention the prefix, then remove the icons it
    # referenced and prune now-empty directories.
    wine_apps = Path.home() / ".local/share/applications/wine"
    removed_desktops: list[Path] = []
    if wine_apps.exists():
        for cand in sorted(wine_apps.rglob("*.desktop")):
            try:
                text = cand.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if str(prefix) in text or f"{slug}.desktop" in text:
                cand.unlink(missing_ok=True)
                removed.append(str(cand))
                removed_desktops.append(cand)
                click.echo(f"  removed wine menu entry {cand}")
                # Remove icons referenced by this entry (hashed wine icon names)
                for line in text.splitlines():
                    if line.startswith("Icon=") and line.strip() != "Icon=":
                        icon_name = line[5:].strip().rstrip("\r")
                        for icon_hit in _glob.glob(
                            str(Path.home() / ".local/share/icons/hicolor" / "*" / "apps" / f"{icon_name}.png")
                        ):
                            Path(icon_hit).unlink(missing_ok=True)
                            removed.append(icon_hit)
                            click.echo(f"  removed wine icon {icon_hit}")
        # Prune empty dirs left behind by the sweep
        for empty in sorted(
            (d for d in wine_apps.rglob("*") if d.is_dir() and not any(d.iterdir())),
            key=lambda p: -len(p.parts),
        ):
            empty.rmdir()

    # --- wine-protocol-<name>.desktop (MIME handler) ---
    protocol_file = Path.home() / ".local/share/applications" / f"wine-protocol-{slug}.desktop"
    if protocol_file.exists():
        protocol_file.unlink()
        removed.append(str(protocol_file))
        click.echo(f"  removed {protocol_file}")

    # --- Cinnamon taskbar/menu stragglers ---
    # The panel's window list (grouped-window-list) pins launchers and the
    # Cinnamenu applet keeps a recent-apps list — both store .desktop names in
    # JSON. Dead entries there survive file deletion and keep an icon pinned.
    import json as _json

    _cinnamon_swept = 0
    spices_dir = Path.home() / ".config/cinnamon/spices"
    if spices_dir.exists():
        for cfg in sorted(spices_dir.rglob("*.json")):
            try:
                raw = cfg.read_text(encoding="utf-8", errors="replace")
                data = _json.loads(raw)
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
                        or any(x in ref_s.lower() for x in (slug, brew.name.lower()))
                    ):
                        changed = True
                        continue
                    kept.append(ref)
                return kept

            def _walk(node) -> None:
                if isinstance(node, dict):
                    for k, v in node.items():
                        if isinstance(v, list):
                            node[k] = _strip_app(v)
                        else:
                            _walk(v)
                elif isinstance(node, list):
                    for item in node:
                        _walk(item)

            _walk(data)
            if changed:
                cfg.write_text(_json.dumps(data, indent=4), encoding="utf-8")
                _cinnamon_swept += 1
                click.echo(f"  removed {brew.name} from {cfg}")
    if _cinnamon_swept:
        removed.append(f"{_cinnamon_swept} cinnamon config(s)")

    if removed:
        click.echo(click.style(f"Uninstalled {brew.name} -- {len(removed)} items removed", fg="green"))
    else:
        click.echo("Nothing to remove -- already clean.")


@cli.command()
@click.argument("name")
@click.option("--registry", default=DEFAULT_REGISTRY, show_default=True, help="Registry directory to remove from.")
def remove(name: str, registry: str) -> None:
    """Remove a brew from the local registry by name."""
    path = _registry_path(registry)
    target = resolve_brew(name, path)
    if target is None:
        raise click.ClickException(f"no brew named '{name}' in {path}")
    # Safety: only ever delete inside the registry directory.
    root = Path(path).expanduser().resolve()
    resolved = target.resolve()
    if root not in resolved.parents or resolved.suffix != ".brew":
        raise click.ClickException(f"refusing to remove {resolved} — outside the registry")
    try:
        resolved.unlink()
    except OSError as exc:
        raise click.ClickException(f"cannot remove {resolved}: {exc}") from exc
    click.echo(click.style(f"🗑️ removed {resolved.name} from {root}", fg="yellow"))


@cli.command()
@click.argument("name")
@click.option("--registry", default=DEFAULT_REGISTRY, show_default=True, help="Registry directory to submit from.")
@click.option("--base", default="main", show_default=True, help="Base branch for the pull request.")
def submit(name: str, registry: str, base: str) -> None:
    """Open a PR for a brew against the shared GitHub registry (AUR-style).

    The local registry must be a clone of the shared syntropia-brews repo,
    and the GitHub CLI (gh) must be installed and authenticated.
    """
    path = _registry_path(registry)
    brew_file = resolve_brew(name, path)
    if brew_file is None:
        raise click.ClickException(
            f"no brew named '{name}' in {path} — run 'syntropia save' first"
        )
    try:
        url = submit_brew(Path(brew_file), Path(path), base=base)
    except RegistryError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(click.style("🚀 PR opened:", fg="green"))
    click.echo(f"   {url}")


@cli.group()
def plugins() -> None:
    """Drop-folder VST3 workflow — drop Windows VST3s into ~/VST3 and bridge them.

    Windows VST3 files (flat DLLs or bundles) go into the drop folder;
    ``syntropia plugins sync`` registers it with yabridge and writes
    Linux stubs under ~/.vst3/yabridge, which Bitwig and other Linux
    DAWs scan by default.
    """


@plugins.command("folder")
@click.option("--create", "create", is_flag=True, help="Create the folder if it does not exist.")
def plugins_folder(create: bool) -> None:
    """Show the VST3 drop folder (optionally create it)."""
    path = drop_folder()
    if create:
        path = ensure_drop_folder(path)
        click.echo(click.style(f"✅ {path}", fg="green"))
        click.echo("Drop Windows VST3 files here, then run 'syntropia plugins sync'.")
    else:
        click.echo(f"{path}")
        if not path.exists():
            click.echo("(does not exist yet — re-run with --create to make it)")


@plugins.command("link")
@click.option("--data", "vendor", required=True, metavar="VENDOR", help="Vendor name to link (e.g. Arturia).")
@click.option("--source", "source", default="~/.wine", show_default=True, help="Wine prefix that already has the vendor's data + registry.")
@click.option("--prefix", "prefixes", multiple=True, help="Target wine prefix to link into (repeatable; default: all syntropia prefixes).")
@click.option("--check", is_flag=True, help="Dry-run: show what would be linked, change nothing.")
def plugins_link(vendor: str, source: str, prefixes: tuple[str, ...], check: bool) -> None:
    """Wire a vendor's data + registry into wine DAW prefixes.

    Vendors like Arturia split installs across a data dir
    (``C:\\ProgramData\\<Vendor>``) and an ``installdir`` registry key. Bitwig
    works via yabridge (runs plugins in their home prefix); a wine-hosted
    DAW like Ableton needs the data symlinked + keys added to its own
    prefix. This command does that from a source prefix (default ~/.wine)
    into every syntropia-managed prefix.
    """
    source_path = Path(os.path.expanduser(source))
    target_prefixes: list[Path] | None = None
    if prefixes:
        target_prefixes = [Path(os.path.expanduser(p)) for p in prefixes]
    try:
        result = link_vendor_data(
            vendor,
            source_path,
            target_prefixes=target_prefixes,
            dry_run=check,
        )
    except VendorError as exc:
        raise click.ClickException(str(exc)) from exc

    click.echo(f"Linking {result.vendor} data from {result.source_prefix}:")
    for src, dest in result.data_dirs:
        click.echo(f"  ↪ {dest}  →  {src}")
    for prefix, key, name, value in result.registry_keys:
        click.echo(f"  reg: {prefix}  HKLM\\{key}  {name} = {value}")

    if check:
        click.echo("Dry-run: nothing changed.")
        return
    if not result.data_dirs and not result.registry_keys:
        click.echo("Nothing to do — already linked.")
        return
    click.echo(click.style(
        f"✅ Linked {result.vendor}: {len(result.data_dirs)} data dir(s), "
        f"{len(result.registry_keys)} registry value(s) across {len(result.target_prefixes)} prefix(es)",
        fg="green",
    ))


@plugins.command("sync")
@click.option("--check", is_flag=True, help="Dry-run: show what would be bridged, change nothing.")
def plugins_sync(check: bool) -> None:
    """Make yabridge aware of every plugin in the drop folder.

    Registers the drop folder with yabridgectl and syncs, so each
    dropped Windows VST3 gets a Linux stub under ~/.vst3/yabridge.
    """
    try:
        result = sync_plugins(dry_run=check)
    except PluginsError as exc:
        raise click.ClickException(str(exc)) from exc

    drop = result.drop_dir
    click.echo(f"Drop folder: {drop}")

    if not result.plugins_found:
        click.echo("No Windows VST3/VST2/CLAP plugins found yet.")
        click.echo(f"Drop plugin files into {drop} and run 'syntropia plugins sync' again.")
        return

    for plugin in result.plugins_found:
        click.echo(f"  found: {plugin.name}")

    if check:
        click.echo(
            "Dry-run: would register the folder with yabridgectl and sync "
            f"({len(result.plugins_found)} plugin(s)). Nothing changed."
        )
        return

    click.echo(click.style(f"✅ Bridged {result.bridged_count} plugin(s)", fg="green"))
    stub_root = result.stub_dir
    if stub_root is not None:
        click.echo(f"Linux stubs written to {stub_root}")
        for plugin in result.plugins_found:
            stub = stub_for(plugin, stub_root)
            if stub is not None:
                click.echo(f"  → {stub}")
        click.echo("Your DAW should already scan this folder — if not, add it in its plugin settings.")


@cli.command()
@click.option("--check", is_flag=True, help="Dry-run: show what would update, change nothing.")
def update(check: bool) -> None:
    """Update Syntropia CLI, brew registry, and re-apply branding.

    Detects how syntropia was installed (AUR, git clone, or pip) and
    pulls the latest from the appropriate source — pacman-tracked
    installs run ``paru -Syu``. Also pulls the shared brew registry and
    re-runs the transform to apply any updated assets.

    ``paru -Syu`` plus the Syntropia layer (brews + branding).
    """
    try:
        run_update(check=check)
    except UpdateError as exc:
        raise click.ClickException(str(exc)) from exc


def main() -> None:
    """Console-script entry point."""
    cli()


if __name__ == "__main__":
    main()
