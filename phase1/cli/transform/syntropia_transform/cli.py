"""Transform + update subcommands — registered into the core Syntropia group."""

from __future__ import annotations

import click

from .transform import TransformError, run_transform
from .update import UpdateError, run_update

DEFAULT_BRANDING_DIR = "/usr/share/syntropia/branding"


@click.group(name="syntropia-transform")
def cli() -> None:
    """Rebrand CachyOS as Syntropia."""


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
    help="Directory with amended assets (plymouth/, wallpaper.png, menu-icon.png, splash/).",
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


def register(group: click.Group) -> None:
    """Add the transform + update commands into the core ``syntropia`` group."""
    for name, command in cli.commands.items():
        group.add_command(command, name=name)
