"""Syntropia CLI — entry point for the living computer's package manager."""

from __future__ import annotations

import os

import click

from .brew import BrewError, find_brews, load_brew
from .transform import TransformError, run_transform
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
@click.argument("brew_file", type=click.Path(exists=True, dir_okay=False))
@click.option("--check", is_flag=True, help="Dry-run: print the install plan, change nothing.")
@click.option("--yes", is_flag=True, help="Confirm: actually run the install.")
def install(brew_file: str, check: bool, yes: bool) -> None:
    """Install a Windows DAW/VST from a .brew manifest (Wine + yabridge).

    Test systems only — see agent-rules/transform-safety.md. Run --check
    first, then confirm with --yes.
    """
    try:
        brew = load_brew(brew_file)
    except BrewError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(click.style(f"✅ Validated: {brew.name} {brew.version}", fg="green"))
    click.echo(f"   category:   {brew.category}")
    click.echo(f"   wine:       {brew.wine_version} ({brew.wine_arch})")
    click.echo(f"   prefix:     {brew.wine_prefix}")
    if brew.winetricks_packages:
        click.echo(f"   winetricks: {', '.join(brew.winetricks_packages)}")
    if brew.yabridge_enabled:
        click.echo(f"   yabridge:   enabled -> {', '.join(brew.plugin_dirs)}")
    if not check and not yes:
        raise click.ClickException(
            "install provisions Wine prefixes — pass --yes to confirm "
            "(read agent-rules/transform-safety.md first)"
        )
    try:
        WineInstaller(brew, dry_run=check).run_all()
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
@click.argument("brew_file", type=click.Path(exists=True, dir_okay=False))
def info(brew_file: str) -> None:
    """Show full details of a .brew manifest."""
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


def main() -> None:
    """Console-script entry point."""
    cli()


if __name__ == "__main__":
    main()
