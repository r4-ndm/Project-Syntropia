"""Tests for the Syntropia Hyprland overlay (iso/profiles/hyprland).

The 2026-10-25 laptop install could not move a single window with the mouse: not
the apps-wizard terminal, not a plain terminal. The overlay never defined the
mouse binds — stock cachyos-hypr-noctalia `config/binds.lua` does, but without
Hyprland's `{ mouse = true }` flag, so they never become bindm (movewindow /
resizewindow). These tests pin the overlay's own binds and the wizard's window
rule against that regression.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OVERLAY = REPO / "iso" / "profiles" / "hyprland" / ".config" / "hypr"
SYNTROPIA_LUA = OVERLAY / "config" / "syntropia.lua"
HYPRLAND_LUA = OVERLAY / "hyprland.lua"


def bind_lines(key: str) -> list:
    """Active hl.bind() lines that bind the given mouse key."""
    lines = []
    for raw in SYNTROPIA_LUA.read_text().splitlines():
        line = raw.strip()
        if line.startswith("hl.bind(") and f"mouse:{key}" in line:
            lines.append(line)
    return lines


def test_super_left_drag_moves_a_window() -> None:
    binds = bind_lines("272")
    assert binds, "the overlay must bind SUPER + LMB (no stock bindm without it)"
    assert any("window.drag()" in line and "mouse = true" in line for line in binds)


def test_super_right_drag_resizes_a_window() -> None:
    binds = bind_lines("273")
    assert binds, "the overlay must bind SUPER + RMB"
    assert any("window.resize()" in line and "mouse = true" in line for line in binds)


def test_overlay_binds_load_after_the_stock_binds() -> None:
    # Our binds are the ones that must win: hyprland.lua requires the stock
    # config first and the Syntropia overlay last.
    src = HYPRLAND_LUA.read_text()
    assert src.index('require("config.binds")') < src.index('pcall(require, "config.syntropia")')


def window_rule_block(needle: str) -> str:
    """The text of the hl.window_rule({...}) block containing `needle`."""
    text = SYNTROPIA_LUA.read_text()
    blocks = text.split("hl.window_rule(")[1:]
    for block in blocks:
        end = block.index("})")
        if needle in block[:end]:
            return block[:end]
    raise AssertionError(f"no window rule matches {needle!r}")


def test_wizard_window_floats_with_a_size_and_is_pinned() -> None:
    rule = window_rule_block("floating_terminal")
    assert "float = true" in rule
    assert "size = {" in rule, "a fixed size keeps the TUI usable, not clipped"
    assert "pin = true" in rule, "pinned so the wizard survives a workspace switch"


def test_wizard_rule_matches_the_launcher_class() -> None:
    # syntropia-app-wiz4rd launches its terminal with --class floating_terminal.
    launcher = (REPO / "iso" / "profiles" / "hyprland" / "bin" / "syntropia-app-wiz4rd").read_text()
    assert "--class floating_terminal" in launcher
    assert "floating_terminal" in SYNTROPIA_LUA.read_text()
