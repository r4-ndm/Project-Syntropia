"""Tests for `syntropia uninstall` straggler sweeps.

These tests monkeypatch HOME to a temp dir so the sweeps (prefix removal,
wine menu entries, icon frames, Cinnamon taskbar/menu configs) run against
fake files only — never the real user's config.
"""

import json
import os
from pathlib import Path

from click.testing import CliRunner

from syntropia.cli import cli, register_plugins

register_plugins(cli)

ABLETON_BREW = """\
# minimal manifest
[brew]
name = "Ableton Live 12"
version = "12.2"
category = "daw"
maintainer = "Syntropia Team <x@y.io>"

[wine]
version = "ableton-wine"
prefix = "~/.local/share/syntropia/prefixes/ableton"
arch = "win64"

[install]
commands = ["echo hi"]
"""


def _run(*args: str):
    return CliRunner().invoke(cli, list(args))


def _set_up_stragglers(home: Path) -> dict:
    """Create the fake leftovers an Ableton install leaves behind."""
    prefix = home / ".local/share/syntropia/prefixes/ableton"
    (prefix / "drive_c").mkdir(parents=True, exist_ok=True)

    # Our own desktop file
    desktop = home / ".local/share/applications/ableton-live-12.desktop"
    desktop.parent.mkdir(parents=True, exist_ok=True)
    desktop.write_text("[Desktop Entry]\nName=Ableton Live 12\n", encoding="utf-8")

    # Our kill script
    kill = home / ".local/bin/ableton-kill"
    kill.parent.mkdir(parents=True, exist_ok=True)
    kill.write_text("#!/bin/sh\n", encoding="utf-8")

    # Icon + straggler frames
    icons = home / ".local/share/icons/hicolor/256x256/apps"
    icons.mkdir(parents=True, exist_ok=True)
    (icons / "ableton-live-12.png").write_bytes(b"x")
    (icons / "ableton-live-12-3.png").write_bytes(b"x")

    # winemenubuilder entries pointing at the prefix
    wine_menu = home / ".local/share/applications/wine/Programs"
    wine_menu.mkdir(parents=True, exist_ok=True)
    (wine_menu / "Ableton Live 12 Trial.desktop").write_text(
        "Exec=env WINEPREFIX=%s wine x\nIcon=7B87_Ableton Live 12 Trial.0\n"
        % prefix,
        encoding="utf-8",
    )
    # hashed wine icon referenced by the menu entry
    (icons / "7B87_Ableton Live 12 Trial.0.png").write_bytes(b"x")

    # wine-protocol MIME handler
    proto = home / ".local/share/applications/wine-protocol-ableton-live-12.desktop"
    proto.write_text("[Desktop Entry]\nType=Application\n", encoding="utf-8")

    # Cinnamon window list pinned apps
    wl_cfg = (
        home
        / ".config/cinnamon/spices/grouped-window-list@cinnamon.org"
        / "2.json"
    )
    wl_cfg.parent.mkdir(parents=True, exist_ok=True)
    wl_cfg.write_text(
        json.dumps(
            {
                "pinned-apps": {
                    "type": "generic",
                    "default": [],
                    "value": [
                        "ableton-live-12.desktop",
                        "wine-Programs-Ableton Live 12 Trial.desktop",
                        "agent-brave.desktop",
                    ],
                }
            }
        ),
        encoding="utf-8",
    )

    # Cinnamenu recent apps
    menu_cfg = home / ".config/cinnamon/spices/Cinnamenu@json" / "15.json"
    menu_cfg.parent.mkdir(parents=True, exist_ok=True)
    menu_cfg.write_text(
        json.dumps(
            {
                "recent-apps": {
                    "type": "generic",
                    "default": [],
                    "value": [
                        "wine-Programs-Ableton Live 12 Trial.desktop",
                        "ableton-live-12.desktop",
                        "terminal.desktop",
                    ],
                }
            }
        ),
        encoding="utf-8",
    )
    return {"prefix": prefix, "icons": icons}


def test_uninstall_sweeps_all_stragglers(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    home = Path(os.environ["HOME"])
    dirs = _set_up_stragglers(home)

    brew_file = tmp_path / "ableton.brew"
    brew_file.write_text(ABLETON_BREW, encoding="utf-8")
    registry = tmp_path / "registry"
    registry.mkdir()

    result = _run("uninstall", str(brew_file), "--registry", str(registry), "--yes")
    assert result.exit_code == 0, result.output

    # Everything must be gone
    assert not dirs["prefix"].exists()
    assert not (home / ".local/share/applications/ableton-live-12.desktop").exists()
    assert not (home / ".local/bin/ableton-kill").exists()
    assert not (dirs["icons"] / "ableton-live-12.png").exists()
    assert not (dirs["icons"] / "ableton-live-12-3.png").exists()
    assert not (
        home / ".local/share/applications/wine/Programs/Ableton Live 12 Trial.desktop"
    ).exists()
    assert not (dirs["icons"] / "7B87_Ableton Live 12 Trial.0.png").exists()
    assert not (
        home / ".local/share/applications/wine-protocol-ableton-live-12.desktop"
    ).exists()

    # Cinnamon configs cleaned but real apps preserved
    wl = json.loads(
        (
            home
            / ".config/cinnamon/spices/grouped-window-list@cinnamon.org"
            / "2.json"
        ).read_text()
    )
    pinned = wl["pinned-apps"]["value"]
    assert pinned == ["agent-brave.desktop"], pinned

    menu = json.loads(
        (home / ".config/cinnamon/spices/Cinnamenu@json" / "15.json").read_text()
    )
    recent = menu["recent-apps"]["value"]
    assert recent == ["terminal.desktop"], recent


def test_uninstall_no_yes_aborts(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    home = Path(os.environ["HOME"])
    _set_up_stragglers(home)

    brew_file = tmp_path / "ableton.brew"
    brew_file.write_text(ABLETON_BREW, encoding="utf-8")
    registry = tmp_path / "registry"
    registry.mkdir()

    result = _run("uninstall", str(brew_file), "--registry", str(registry))
    assert result.exit_code != 0
    assert "--yes" in result.output

    # Nothing removed without --yes
    assert (home / ".local/share/syntropia/prefixes/ableton").exists()
    assert (home / ".local/share/applications/ableton-live-12.desktop").exists()
