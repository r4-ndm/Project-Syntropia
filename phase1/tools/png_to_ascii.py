#!/usr/bin/env python3
"""Convert a PNG into ASCII art — the fastfetch / terminal logo pipeline.

Design a logo in GIMP, drop the PNG here, and get ASCII out. The result is
exactly what ``syntropia transform`` ships as ``/usr/share/syntropia/logo.txt``
(see ``Branding/syntropia/logo.txt`` — the asset-drop slot for this output).

Two output modes:

* **Grayscale** (default) — brightness mapped to a character ramp.
* **Color** (``--color``) — the image is quantized to a small palette and
  rendered as ``$N`` fastfetch color placeholders plus block glyphs. Fastfetch
  does not parse raw ANSI codes in logo files; it resolves ``$1``..``$9`` via
  the ``logo.color`` config map (or ``--logo-color-N`` flags). Use
  ``--color-map FILE`` to write the matching map JSON.

Uses ImageMagick (``magick``) for resizing/quantization, like
``generate_spinner.py`` — no Python dependencies beyond the stdlib.

Usage:
    python3 png_to_ascii.py --input Branding/syntropia/mark.png --width 60
    python3 png_to_ascii.py --input logo.png --blocks --invert --out logo.txt
    python3 png_to_ascii.py --input logo.png --color --colors 8 \\
        --out logo.txt --color-map fastfetch-color.json

Options at a glance:
    --width N     columns of output (default 60)
    --invert      swap light/dark (for dark-on-light logos)
    --blocks      use Unicode block glyphs (█▓▒░) instead of ASCII
    --bg COLOR    composite transparency onto white|black (default black)
    --contrast    stretch levels before mapping (helps flat logos)
    --ramp STR    custom brightness ramp (dark..bright order)
    --color       color mode: $N placeholders + █ blocks
    --colors N    palette size for --color (default 8, max 9 — fastfetch limit)
    --threshold N luminance below which pixels become spaces (default 24)
    --half        half-block rendering (▀▄█): doubles vertical resolution
                  and renders fg+bg colors per cell (with --color)
    --color-map FILE  write the fastfetch color map JSON (with --color)
    --out FILE    write to file instead of stdout
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Terminal glyphs are roughly twice as tall as they are wide, so a
# rectangular image must be squashed by ~0.5 vertically to render square.
CHAR_ASPECT = 0.5

DEFAULT_RAMP = " .:-=+*#%@"
BLOCK_RAMP = " ░▒▓█"

MAX_FASTFETCH_COLORS = 9  # placeholders are $1..$9


def run(cmd: list[str], *, binary: bool = False) -> subprocess.CompletedProcess:
    result = subprocess.run(cmd, capture_output=True, text=not binary)
    if result.returncode != 0:
        sys.exit(f"command failed: {' '.join(cmd)}\n{result.stderr.strip()}")
    return result


def image_dims(image: Path) -> tuple[int, int]:
    """Return (width, height) of the source image."""
    result = run(["magick", "identify", "-format", "%w %h", str(image)])
    w, h = result.stdout.strip().split()
    return int(w), int(h)


def _pipeline_prefix(
    image: Path, cols: int, rows: int, bg: str, contrast: bool, colors: int | None
) -> list[str]:
    """Shared magick pipeline: flatten transparency, resize, quantize."""
    cmd = [
        "magick", str(image),
        "-background", bg,
        "-alpha", "remove", "-alpha", "off",
        "-resize", f"{cols}x{rows}!",
    ]
    if contrast:
        cmd += ["-normalize"]
    if colors is not None:
        # +dither: quantize with a fixed palette (median cut), no error
        # diffusion — each output cell maps to one clean palette color.
        cmd += ["+dither", "-colors", str(colors)]
    cmd += ["-depth", "8"]
    return cmd


def ramp_lookup(value: int, ramp: str, invert: bool) -> str:
    """Map a 0-255 brightness to a ramp character (dark..bright order)."""
    idx = value * (len(ramp) - 1) // 255
    if invert:
        idx = len(ramp) - 1 - idx
    return ramp[idx]


def convert(
    image: Path,
    *,
    width: int,
    invert: bool = False,
    blocks: bool = False,
    bg: str = "black",
    contrast: bool = False,
    ramp: str | None = None,
) -> str:
    """Convert ``image`` to a grayscale ASCII art string."""
    if not image.is_file():
        sys.exit(f"image not found: {image}")
    if shutil.which("magick") is None:
        sys.exit("ImageMagick 'magick' not found on PATH")

    ramp = ramp or (BLOCK_RAMP if blocks else DEFAULT_RAMP)
    w, h = image_dims(image)
    cols = max(1, width)
    rows = max(1, round(cols * (h / w) * CHAR_ASPECT))

    cmd = _pipeline_prefix(image, cols, rows, bg, contrast, None)
    cmd += ["-colorspace", "Gray", "gray:-"]
    data = run(cmd, binary=True).stdout
    if len(data) != cols * rows:
        sys.exit(
            f"unexpected pixel data: got {len(data)} bytes for {cols}x{rows} "
            f"({cols * rows} expected)"
        )

    lines = []
    for y in range(rows):
        row = data[y * cols:(y + 1) * cols]
        lines.append("".join(ramp_lookup(b, ramp, invert) for b in row))
    return "\n".join(lines) + "\n"


# --- color mode ---------------------------------------------------------


def _extract_palette(
    prefix: list[str], image: Path, cols: int, rows: int
) -> list[str]:
    """Quantize and return the resulting palette as hex strings, in order."""
    result = run(
        prefix + ["-format", "%c", "histogram:info:-"],
        binary=False,
    )
    hexes = re.findall(r"#([0-9A-Fa-f]{6})", result.stdout)
    ordered = list(dict.fromkeys(hexes))
    return [f"#{c.upper()}" for c in ordered]


def _nearest_index(r: int, g: int, b: int, palette_rgb: list[tuple[int, int, int]]) -> int:
    """Index of the closest palette color (squared Euclidean distance)."""
    best, best_i = 1 << 30, 0
    for i, (pr, pg, pb) in enumerate(palette_rgb):
        d = (r - pr) ** 2 + (g - pg) ** 2 + (b - pb) ** 2
        if d < best:
            best, best_i = d, i
    return best_i


def convert_color(
    image: Path,
    *,
    width: int,
    colors: int = 8,
    bg: str = "black",
    contrast: bool = False,
    threshold: int = 24,
    half: bool = False,
) -> tuple[str, dict[str, str]]:
    """Convert ``image`` to fastfetch placeholder art + a color map.

    Returns ``(art, color_map)`` where ``art`` uses ``$1``..``$9`` placeholders
    and ``color_map`` maps placeholder number -> color spec (``#RRGGBB``, or a
    full ``38;2;r;g;b;48;2;r;g;b`` SGR when ``half`` needs fg+bg per cell).

    With ``half=True`` the image is sampled at full vertical resolution and
    rendered with half-block glyphs (\u2580 top / \u2584 bottom / \u2588 full):
    two pixel rows per terminal line, doubling the visible detail.
    """
    if not image.is_file():
        sys.exit(f"image not found: {image}")
    if shutil.which("magick") is None:
        sys.exit("ImageMagick 'magick' not found on PATH")

    colors = min(max(1, colors), MAX_FASTFETCH_COLORS)
    w, h = image_dims(image)
    cols = max(1, width)
    if half:
        # Half blocks need no vertical squish: each line holds two pixel rows.
        pixel_rows = round(cols * h / w)
        pixel_rows += pixel_rows % 2  # keep cell pairs aligned
        rows = pixel_rows // 2
    else:
        pixel_rows = rows = max(1, round(cols * (h / w) * CHAR_ASPECT))

    prefix = _pipeline_prefix(image, cols, pixel_rows, bg, contrast, colors)
    palette_hex = _extract_palette(prefix, image, cols, pixel_rows)
    palette_rgb = [
        (int(p[1:3], 16), int(p[3:5], 16), int(p[5:7], 16)) for p in palette_hex
    ]

    data = run(prefix + ["rgb:-"], binary=True).stdout
    if len(data) != cols * pixel_rows * 3:
        sys.exit(
            f"unexpected pixel data: got {len(data)} bytes for {cols}x{pixel_rows} "
            f"({cols * pixel_rows * 3} expected)"
        )

    def pixel(y: int, x: int) -> tuple[int, int, int, float, int]:
        i = (y * cols + x) * 3
        r, g, b = data[i], data[i + 1], data[i + 2]
        lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
        return r, g, b, lum, _nearest_index(r, g, b, palette_rgb)

    # Darkest palette color: the universal background for half-block cells
    # whose other half is dark. Using a real palette color (not terminal bg)
    # keeps every half-mode spec a full fg+bg SGR — no background leakage.
    dark_idx = len(palette_hex) - 1  # palette is sorted by histogram order

    # spec registry: key -> placeholder "N". Key is (fg,) in plain mode,
    # (fg, bg) in half mode (bg always present so no background leaks).
    specs: dict[tuple, str] = {}
    spec_color: dict[str, str] = {}

    def spec_sgr(fg_hex: str, bg_hex: str) -> str:
        return (
            f"38;2;{int(fg_hex[1:3],16)};{int(fg_hex[3:5],16)};{int(fg_hex[5:7],16)}"
            f";48;2;{int(bg_hex[1:3],16)};{int(bg_hex[3:5],16)};{int(bg_hex[5:7],16)}"
        )

    def placeholder_for(fg: int, bg: int | None) -> str:
        key = (fg,) if bg is None else (fg, bg)
        while key not in specs:
            if len(specs) >= MAX_FASTFETCH_COLORS:
                # Budget exhausted: degrade toward (fg, dark_idx), then the
                # plain fg spec, then the first spec. Never exceed 9.
                if len(key) == 2 and key[1] != dark_idx:
                    key = (fg, dark_idx)
                    continue
                if len(key) == 2:
                    key = (fg,)
                    continue
                return next(iter(specs.values()))
            n = str(len(specs) + 1)
            specs[key] = n
            fg_hex = palette_hex[fg]
            if bg is None:
                spec_color[n] = fg_hex
            else:
                spec_color[n] = spec_sgr(fg_hex, palette_hex[bg])
        return specs[key]

    lines = []
    for y in range(rows):
        line: list[str] = []
        current = -1
        for x in range(cols):
            if not half:
                _, _, _, lum, idx = pixel(y, x)
                if lum < threshold:
                    line.append(" ")
                    continue
                ph = placeholder_for(idx, None)
                if ph != current:
                    line.append(f"${ph}")
                    current = ph
                line.append("█")
                continue

            _, _, _, top_lum, top_idx = pixel(2 * y, x)
            _, _, _, bot_lum, bot_idx = pixel(2 * y + 1, x)
            top_bright = top_lum >= threshold
            bot_bright = bot_lum >= threshold
            if not top_bright and not bot_bright:
                line.append(" ")
                continue
            if top_bright and bot_bright:
                if top_idx == bot_idx:
                    glyph, fg, bg = "█", top_idx, dark_idx
                else:
                    glyph, fg, bg = "▀", top_idx, bot_idx
            elif top_bright:
                glyph, fg, bg = "▀", top_idx, dark_idx
            else:
                glyph, fg, bg = "▄", bot_idx, dark_idx
            ph = placeholder_for(fg, bg)
            if ph != current:
                line.append(f"${ph}")
                current = ph
            line.append(glyph)
        lines.append("".join(line))

    return "\n".join(lines) + "\n", dict(
        sorted(spec_color.items(), key=lambda kv: int(kv[0]))
    )


def spec_to_rgb(spec: str, prefix: str = "38;2") -> tuple[int, int, int] | None:
    """Pull the r;g;b triplet out of an SGR spec fragment."""
    match = re.search(rf"{re.escape(prefix)};(\d+);(\d+);(\d+)", spec)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="source PNG")
    parser.add_argument("--width", type=int, default=60, help="output columns")
    parser.add_argument("--invert", action="store_true", help="swap light/dark")
    parser.add_argument("--blocks", action="store_true", help="use Unicode block glyphs")
    parser.add_argument("--bg", default="black", choices=["black", "white"],
                        help="composite background for transparency")
    parser.add_argument("--contrast", action="store_true", help="stretch levels")
    parser.add_argument("--ramp", default=None, help="custom brightness ramp (dark..bright)")
    parser.add_argument("--color", action="store_true",
                        help="color mode: $N placeholders + block glyphs")
    parser.add_argument("--colors", type=int, default=8,
                        help="palette size for --color (max 9)")
    parser.add_argument("--threshold", type=int, default=24,
                        help="luminance cutoff for spaces (with --color)")
    parser.add_argument("--half", action="store_true",
                        help="half-block rendering (▀▄█) with --color")
    parser.add_argument("--color-map", default=None,
                        help="write fastfetch color map JSON (with --color)")
    parser.add_argument("--out", default=None, help="output file (default stdout)")
    args = parser.parse_args()

    image = Path(args.input)
    if args.color:
        art, color_map = convert_color(
            image,
            width=args.width,
            colors=args.colors,
            bg=args.bg,
            contrast=args.contrast,
            threshold=args.threshold,
            half=args.half,
        )
        if args.color_map:
            Path(args.color_map).write_text(
                json.dumps(color_map, indent=2) + "\n", encoding="utf-8"
            )
            print(f"wrote color map {args.color_map} "
                  f"({len(color_map)} color(s))")
    else:
        art = convert(
            image,
            width=args.width,
            invert=args.invert,
            blocks=args.blocks,
            bg=args.bg,
            contrast=args.contrast,
            ramp=args.ramp,
        )
    if args.out:
        Path(args.out).write_text(art, encoding="utf-8")
        print(f"wrote {args.out} ({len(art.splitlines())} lines)")
    else:
        sys.stdout.write(art)


if __name__ == "__main__":
    main()
