#!/usr/bin/env python3
"""Generate Plymouth animation + throbber frames from a single logo PNG.

The CachyOS Plymouth theme's boot logo is a sprite set: ``animation-0001.png``
.. ``animation-00NN.png`` (a fade/scale-in of the logo) plus
``throbber-0001.png`` .. ``throbber-00MM.png`` (a pulsing scale loop shown
while the system boots). Editing 60+ tiny 32x32 frames by hand is madness —
this tool regenerates the whole set from one logo in a second.

Requires ImageMagick (``magick``) on PATH.

Usage:
    python generate_spinner.py --logo Branding/syntropia-mark.png \\
        --out /tmp/plymouth --frames 30 --throbber 36 --size 32
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit(f"command failed: {' '.join(cmd)}\n{result.stderr.strip()}")


def render_frame(logo: Path, out: Path, size: int, scale: float, alpha: float) -> None:
    """Render one square frame: logo scaled to ``scale``, centered, opacity ``alpha``.

    Uses a transparent square canvas so non-square logos stay un-squashed
    (Plymouth sprites are square, e.g. 32x32).
    """
    dim = max(1, int(size * scale))
    cmd = [
        "magick",
        "-size", f"{size}x{size}", "xc:none",
        "(", str(logo), "-resize", f"{dim}x{dim}", ")",
        "-gravity", "center",
        "-composite",
        "-alpha", "set",
        "-channel", "A",
        "-evaluate", "multiply", f"{alpha:.4f}",
        "+channel",
        "-depth", "8",
        str(out),
    ]
    run(cmd)


def generate(logo: Path, out: Path, frames: int, throbber: int, size: int) -> None:
    if not logo.is_file():
        sys.exit(f"logo not found: {logo}")
    if shutil.which("magick") is None:
        sys.exit("ImageMagick 'magick' not found on PATH")
    out.mkdir(parents=True, exist_ok=True)

    # Animation: fade in + grow 40% -> 100%.
    print(f"rendering {frames} animation frames...")
    for i in range(1, frames + 1):
        t = (i - 1) / max(frames - 1, 1)
        scale = 0.4 + 0.6 * t
        alpha = 0.15 + 0.85 * t
        render_frame(logo, out / f"animation-{i:04d}.png", size, scale, alpha)

    # Throbber: gentle pulse 88% -> 100% -> 88%.
    print(f"rendering {throbber} throbber frames...")
    for i in range(1, throbber + 1):
        t = (i - 1) / throbber  # 0 .. ~1
        pulse = abs(2 * (t - 0.5))  # 1 -> 0 -> 1
        scale = 0.88 + 0.12 * pulse
        render_frame(logo, out / f"throbber-{i:04d}.png", size, scale, 1.0)

    print(f"done: {frames + throbber} frames written to {out}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logo", required=True, help="source logo PNG (with alpha)")
    parser.add_argument("--out", required=True, help="output directory for frames")
    parser.add_argument("--frames", type=int, default=30, help="animation frame count")
    parser.add_argument("--throbber", type=int, default=36, help="throbber frame count")
    parser.add_argument("--size", type=int, default=32, help="frame pixel size (square)")
    args = parser.parse_args()
    generate(Path(args.logo), Path(args.out), args.frames, args.throbber, args.size)


if __name__ == "__main__":
    main()
