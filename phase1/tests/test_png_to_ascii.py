"""Tests for tools/png_to_ascii.py — the PNG → ASCII logo converter."""

import shutil
import subprocess
from pathlib import Path

import pytest

import png_to_ascii as P


# --- pure mapping -------------------------------------------------------


def test_ramp_lookup_bright_is_ramp_end():
    assert P.ramp_lookup(255, " .:-=+*#%@", invert=False) == "@"
    assert P.ramp_lookup(0, " .:-=+*#%@", invert=False) == " "


def test_ramp_lookup_invert_swaps_polarity():
    assert P.ramp_lookup(255, " .:-=+*#%@", invert=True) == " "
    assert P.ramp_lookup(0, " .:-=+*#%@", invert=True) == "@"


def test_ramp_lookup_mid_values():
    ramp = " .:-=+*#%@"  # 10 chars, index = value * 9 // 255
    assert P.ramp_lookup(127, ramp, invert=False) == ramp[127 * 9 // 255]
    assert P.ramp_lookup(128, ramp, invert=False) == ramp[128 * 9 // 255]


def test_ramp_lookup_block_ramp():
    assert P.ramp_lookup(255, " ░▒▓█", invert=False) == "█"
    assert P.ramp_lookup(0, " ░▒▓█", invert=False) == " "


# --- end-to-end (requires ImageMagick) ---------------------------------


@pytest.mark.skipif(shutil.which("magick") is None, reason="ImageMagick not installed")
def test_convert_renders_expected_grid(tmp_path: Path):
    # 2x1 image: black pixel left, white pixel right (1x1 canvases so no
    # -size leakage or averaging between cells).
    png = tmp_path / "half.png"
    subprocess.run(
        ["magick", "-size", "1x1", "xc:black", "xc:white", "+append", str(png)],
        check=True,
    )
    art = P.convert(png, width=2)
    lines = art.splitlines()
    assert len(lines) == 1
    assert lines[0][0] == " "  # black -> darkest
    assert lines[0][1] == "@"  # white -> brightest


@pytest.mark.skipif(shutil.which("magick") is None, reason="ImageMagick not installed")
def test_convert_width_controls_columns(tmp_path: Path):
    png = tmp_path / "white.png"
    subprocess.run(["magick", "-size", "4x2", "xc:white", str(png)], check=True)
    art = P.convert(png, width=4)
    lines = art.splitlines()
    # rows = cols * (h/w) * 0.5 = 4 * (2/4) * 0.5 = 1
    assert len(lines) == 1
    assert len(lines[0]) == 4
    assert lines[0] == "@@@@"


@pytest.mark.skipif(shutil.which("magick") is None, reason="ImageMagick not installed")
def test_convert_invert_swaps_output(tmp_path: Path):
    png = tmp_path / "white.png"
    subprocess.run(["magick", "-size", "2x1", "xc:white", str(png)], check=True)
    normal = P.convert(png, width=2, invert=False)
    inverted = P.convert(png, width=2, invert=True)
    assert normal.strip() == "@@"
    assert inverted.strip() == ""


# --- color mode ---------------------------------------------------------


@pytest.mark.skipif(shutil.which("magick") is None, reason="ImageMagick not installed")
def test_convert_color_emits_placeholders_and_map(tmp_path: Path):
    # Left pixel red, right pixel cyan — two bright, distinct palette entries
    # (1x1 canvases so -size can't leak across xc: images). Width 2 keeps
    # one output cell per pixel (width 1 would average them into one cell).
    png = tmp_path / "two-tone.png"
    subprocess.run(
        ["magick", "-size", "1x1", "xc:red", "xc:cyan", "+append", str(png)],
        check=True,
    )
    art, color_map = P.convert_color(png, width=2)
    assert art.count("█") == 2  # both pixels are bright blocks
    assert "$1" in art and "$2" in art
    assert len(color_map) == 2
    assert all(v.startswith("#") and len(v) == 7 for v in color_map.values())


@pytest.mark.skipif(shutil.which("magick") is None, reason="ImageMagick not installed")
def test_convert_color_threshold_makes_dark_pixels_spaces(tmp_path: Path):
    # Left pixel black, right pixel white.
    png = tmp_path / "dark-light.png"
    subprocess.run(
        ["magick", "-size", "1x1", "xc:black", "xc:white", "+append", str(png)],
        check=True,
    )
    art, color_map = P.convert_color(png, width=2, threshold=100)
    lines = art.splitlines()
    assert len(lines) == 1
    # The black pixel is below the luminance threshold -> space; white -> block.
    assert lines[0][0] == " "
    assert lines[0][-1] == "█"


@pytest.mark.skipif(shutil.which("magick") is None, reason="ImageMagick not installed")
def test_convert_color_max_palette_capped(tmp_path: Path):
    png = tmp_path / "white.png"
    subprocess.run(["magick", "-size", "1x1", "xc:white", str(png)], check=True)
    art, color_map = P.convert_color(png, width=1, colors=99)  # cap to 9
    assert len(color_map) <= P.MAX_FASTFETCH_COLORS
    assert art.count("█") == 1


# --- half-block mode ----------------------------------------------------


@pytest.mark.skipif(shutil.which("magick") is None, reason="ImageMagick not installed")
def test_convert_color_half_doubles_vertical_detail(tmp_path: Path):
    # 1x2 image: top pixel red, bottom pixel cyan. At width 2 the half
    # sampler reads 4 pixel rows -> 2 lines, each a two-color cell pair.
    png = tmp_path / "two-row.png"
    subprocess.run(
        ["magick", "-size", "1x1", "xc:red", "xc:cyan", "-append", str(png)],
        check=True,
    )
    art, color_map = P.convert_color(png, width=2, half=True)
    lines = art.splitlines()
    assert len(lines) == 2
    # A bright-top / bright-bottom boundary renders as a half block.
    assert any("▀" in line or "▄" in line for line in lines)
    assert len(color_map) <= P.MAX_FASTFETCH_COLORS


@pytest.mark.skipif(shutil.which("magick") is None, reason="ImageMagick not installed")
def test_convert_color_half_all_specs_have_background(tmp_path: Path):
    """Half mode must never emit fg-only specs (background leakage bug)."""
    png = tmp_path / "white.png"
    subprocess.run(["magick", "-size", "1x1", "xc:white", str(png)], check=True)
    art, color_map = P.convert_color(png, width=2, half=True)
    assert all("48;2;" in v for v in color_map.values())
    assert all(v.startswith("38;2;") for v in color_map.values())


@pytest.mark.skipif(shutil.which("magick") is None, reason="ImageMagick not installed")
def test_convert_color_half_dark_cells_are_spaces(tmp_path: Path):
    png = tmp_path / "dark.png"
    subprocess.run(["magick", "-size", "1x1", "xc:black", str(png)], check=True)
    art, color_map = P.convert_color(png, width=2, half=True, threshold=100)
    assert art.strip() == ""
