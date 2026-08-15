"""Brew subcommands for the Syntropia CLI — registered into the core group."""

from __future__ import annotations

import os
from pathlib import Path

import click

from syntropia.process import run_command
from syntropia.progress import StepProgress
from .brew import BrewError, brew_filename, find_brews, lint_brew, load_brew, registry_brew_is_stale, resolve_brew, save_brew
from .plugins import PluginsError, drop_folder, ensure_drop_folder, stub_for, sync_plugins
from .vendor import VendorError, link_vendor_data
from .registry import RegistryError, submit_brew
from .uninstall import uninstall_brew
from .wine_helper import STEP_LABELS, WineHelperError, WineInstaller

DEFAULT_REGISTRY = "~/.config/syntropia/brews"


def _registry_path(registry: str) -> str:
    return os.path.expanduser(registry)


@click.group(name="syntropia-brews")
def cli() -> None:
    """Install Windows DAWs and VSTs via Wine + yabridge."""


@cli.command("brews-gui")
def brews_gui() -> None:
    """Open the Textual GUI — inventory, locations, install/uninstall."""
    try:
        from .gui import run
    except ImportError as exc:
        raise click.ClickException(
            "the brew GUI needs the 'textual' package — "
            "install python-textual (Arch: pacman -S python-textual)"
        ) from exc
    run()


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

    removed = uninstall_brew(brew, echo=click.echo)
    if removed:
        click.echo(
            click.style(
                f"Uninstalled {brew.name} -- {len(removed)} items removed", fg="green"
            )
        )
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
def registry() -> None:
    """Manage the local brew registry (a git clone of the shared repo)."""


@registry.command("sync")
@click.option("--registry", default=DEFAULT_REGISTRY, show_default=True, help="Registry directory to sync.")
def registry_sync(registry: str) -> None:
    """Pull the latest brew manifests from the shared GitHub registry.

    The local registry is a git clone of the shared syntropia-brews repo;
    this fast-forwards it to origin/main. Read-only — never runs a recipe
    or touches Wine. Safe to run from a systemd oneshot/timer.
    """
    path = Path(_registry_path(registry))
    if not (path / ".git").is_dir():
        click.echo(f"brew registry not cloned yet at {path} — nothing to sync")
        return
    proc = run_command(["git", "-C", str(path), "pull", "--quiet", "--ff-only", "origin", "main"])
    if proc.returncode != 0:
        raise click.ClickException(f"git pull failed in {path}: {proc.stderr.strip()}")
    if proc.stdout.strip():
        click.echo(click.style(f"✅ registry synced: {proc.stdout.strip()}", fg="green"))
    else:
        click.echo("✅ registry already up to date")


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


def register(group: click.Group) -> None:
    """Add every brew command into the core ``syntropia`` group."""
    for name, command in cli.commands.items():
        group.add_command(command, name=name)
