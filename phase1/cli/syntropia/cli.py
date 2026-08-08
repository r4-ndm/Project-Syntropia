"""Syntropia CLI — entry point for the living computer's package manager."""

from __future__ import annotations

import os
from pathlib import Path

import click

from .brew import BrewError, brew_filename, find_brews, load_brew, resolve_brew, save_brew
from .progress import StepProgress
from .registry import RegistryError, submit_brew
from .transform import TransformError, run_transform
from .update import UpdateError, run_update
from .wine_helper import WineHelperError, WineInstaller

DEFAULT_REGISTRY = "~/.config/syntropia/brews"

DEFAULT_BRANDING_DIR = "/usr/share/syntropia/branding"


def _registry_path(registry: str) -> str:
    return os.path.expanduser(registry)


@click.group()
@click.version_option(version="0.1.0", prog_name="syntropia")
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

    if not check and not yes:
        raise click.ClickException(
            "install provisions Wine prefixes — pass --yes to confirm "
            "(read agent-rules/transform-safety.md first)"
        )

    steps: list[tuple[str, str]] = [
        ("Toolchain",  "Checking wine, winetricks, yabridge"),
        ("Prefix",     "Provisioning Wine prefix"),
        ("Overrides",  "Applying DLL overrides"),
        ("Winetricks", "Installing winetricks packages"),
        ("Yabridge",   "Registering plugin directories"),
        ("Source",     "Finding installer file"),
        ("Install",    "Running install commands"),
        ("Sync",       "Syncing yabridge plugins"),
    ]

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


@cli.command()
@click.option("--check", is_flag=True, help="Dry-run: show what would update, change nothing.")
def update(check: bool) -> None:
    """Update Syntropia CLI, brew registry, and re-apply branding.

    Detects how syntropia was installed (AUR, git clone, or pip) and
    pulls the latest from the appropriate source. Also pulls the shared
    brew registry and re-runs the transform to apply any updated assets.

    The ``yay -Syu`` equivalent for the Syntropia layer.
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
