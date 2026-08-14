#!/usr/bin/env python3
"""Regenerate the Syntropia Plymouth boot animation (triangle particle swarm).

Produces an 88-frame ``two-step`` Plymouth animation matching the structure of
CachyOS's ``cachyos-bootanimation`` theme: the triangle holds full for a moment,
its pixels disperse into a scatter and fade out, the frame goes empty, then the
particles fly back and re-form the triangle. Frames are 300x300 RGBA with a
transparent background (Plymouth composites them over the theme's black
background).

It generates the full-screen particle swarm that CachyOS ships as
``cachyos-bootanimation`` — the theme our ``plymouth/`` asset now mirrors.

Usage:
    python3 phase1/tools/generate_bootanimation.py [--logo PATH] [--out DIR]

Defaults write the frames straight into Branding/syntropia/plymouth/.
"""
import argparse
import math
import random
from pathlib import Path

from PIL import Image

SIZE = 300
FRAMES = 88
# Two-tone: the logo is a white triangle with black inner cutouts. Particles
# keep their source tone so the inner triangles survive the swarm (previously
# every particle was rendered white, which filled the cutouts in).
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)

# Phase boundaries (mirror cachyos-bootanimation's hold/disperse/empty/reform):
HOLD_END = 1     # frames 0..1 hold the logo full
DISP_END = 41    # frames 2..41 disperse
EMPTY_END = 49   # frames 42..49 empty
# frames 50..87 re-form


def ease_in_out(u: float) -> float:
    u = max(0.0, min(1.0, u))
    return u * u * (3.0 - 2.0 * u)


def frame_curve(t: int) -> float:
    """Dispersion progress 0..1 (0 = logo formed, 1 = fully scattered)."""
    if t <= HOLD_END:
        return 0.0
    if t <= DISP_END:
        return ease_in_out((t - HOLD_END - 1) / float(DISP_END - HOLD_END - 1))
    if t <= EMPTY_END:
        return 1.0
    return 1.0 - ease_in_out((t - EMPTY_END - 1) / float(FRAMES - 1 - EMPTY_END - 1))


def sample_particles(logo: Image.Image) -> list[tuple[int, int, int, int, int, int]]:
    """Sample the logo's opaque pixels as (x, y, r, g, b, a) particle targets.

    RGB is quantised to two tones (white triangle / black inner triangles) so
    the interior detail survives instead of being flattened to all-white.
    """
    particles = []
    px = logo.load()
    for y in range(logo.height):
        for x in range(logo.width):
            r, g, b, a = px[x, y]
            if a > 0:
                tone = WHITE if (r + g + b) / 3 >= 128 else BLACK
                particles.append((x, y, tone[0], tone[1], tone[2], a))
    return particles


def generate(logo_path: Path, out_dir: Path) -> None:
    src = Image.open(logo_path).convert("RGBA")
    # Fit the logo to a reasonable footprint inside the 300x300 canvas.
    target_w = 168
    ratio = target_w / src.width
    logo = src.resize((target_w, max(1, int(src.height * ratio))), Image.LANCZOS)
    ox = (SIZE - logo.width) // 2
    oy = (SIZE - logo.height) // 2

    particles = [(ox + x, oy + y, r, g, b, a)
                  for x, y, r, g, b, a in sample_particles(logo)]

    rng = random.Random(20260814)  # deterministic output
    rng.shuffle(particles)
    scatter = []
    for _ in particles:
        ang = rng.uniform(0.0, 2.0 * math.pi)
        mag = rng.uniform(40.0, 150.0)
        scatter.append((math.cos(ang) * mag, math.sin(ang) * mag))

    out_dir.mkdir(parents=True, exist_ok=True)
    for t in range(FRAMES):
        c = frame_curve(t)
        if c >= 1.0:
            # Fully dispersed -> empty frame (matches cachyos-bootanimation).
            Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0)).save(
                out_dir / f"animation-{t:02d}.png"
            )
            continue
        # Fade particles as they scatter: full alpha when formed, ~12% when
        # scattered so they read as a dim star field before vanishing.
        fade = 1.0 - 0.88 * c
        # Black inner cutouts don't scatter over the black background (they'd be
        # invisible mid-flight) — they dissolve in place instead: gone by the
        # first third of the disperse, back in the final third of the re-form.
        black_fade = max(0.0, 1.0 - 3.0 * c)
        alpha_buf = bytearray(SIZE * SIZE)
        color_buf = [None] * (SIZE * SIZE)
        for (px, py, pr, pg, pb, a), (dx, dy) in zip(particles, scatter):
            if (pr, pg, pb) == BLACK:
                x, y = px, py
                alpha = int(a * black_fade)
            else:
                x = int(px + dx * c)
                y = int(py + dy * c)
                alpha = int(a * fade)
            if 0 <= x < SIZE and 0 <= y < SIZE:
                idx = y * SIZE + x
                if alpha > alpha_buf[idx]:
                    alpha_buf[idx] = alpha
                    color_buf[idx] = (pr, pg, pb)
        img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        pxm = img.load()
        for y in range(SIZE):
            row = y * SIZE
            for x in range(SIZE):
                a = alpha_buf[row + x]
                if a:
                    r, g, b = color_buf[row + x]
                    pxm[x, y] = (r, g, b, a)
        img.save(out_dir / f"animation-{t:02d}.png")

    print(f"generated {FRAMES} frames -> {out_dir} ({len(particles)} particles)")


def main() -> None:
    repo = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logo", type=Path,
                        default=repo / "Branding" / "syntropia" / "256mage8.png")
    parser.add_argument("--out", type=Path,
                        default=repo / "Branding" / "syntropia" / "plymouth")
    args = parser.parse_args()
    generate(args.logo, args.out)


if __name__ == "__main__":
    main()
