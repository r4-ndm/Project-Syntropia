#!/usr/bin/env python3
"""Regenerate the Syntropia Plymouth boot animation (Cosmic Vortex 3D Particle Swarm).

Produces an 88-frame full-screen (1920x1080) ``two-step`` Plymouth animation:
- Cosmic Vortex spiral physics: particles curve and swirl in an organic 3D vortex.
- Depth of Field & Glow: Foreground particles cast soft sub-pixel glow, midground
  particles remain razor-crisp, and background stars float in deep perspective.
- Seamless loop: Disperses immediately on boot, scatters across the screen, and
  spirals smoothly back to re-assemble the Syntropia triangle mark.

Usage:
    python3 phase1/tools/generate_bootanimation.py [--logo PATH] [--out DIR]
"""
import argparse
import concurrent.futures
import math
import os
import random
from pathlib import Path
from PIL import Image

WIDTH = 1920
HEIGHT = 1080
CX = WIDTH // 2
CY = HEIGHT // 2
FRAMES = 88

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)

# Phase boundaries:
DISP_END = 41    # frames 0..41 spiral outward immediately (no static hold)
EMPTY_END = 49   # frames 42..49 maximum dispersion / empty frame
# frames 50..87 spiral back and re-assemble


def ease_in_out(u: float) -> float:
    u = max(0.0, min(1.0, u))
    return u * u * (3.0 - 2.0 * u)


def frame_curve(t: int) -> float:
    """Dispersion progress 0..1 (0 = logo formed, 1 = fully scattered)."""
    if t <= DISP_END:
        return ease_in_out(t / float(DISP_END))
    if t <= EMPTY_END:
        return 1.0
    return 1.0 - ease_in_out((t - EMPTY_END) / float(FRAMES - EMPTY_END))


def sample_cosmic_particles(logo: Image.Image, ox: int, oy: int) -> list:
    """Sample logo pixels into 3D vortex particles with depth & swirl parameters."""
    particles = []
    px = logo.load()
    rng = random.Random(20260814)  # deterministic seed

    for y in range(logo.height):
        for x in range(logo.width):
            r, g, b, a = px[x, y]
            if a > 0:
                tone = WHITE if (r + g + b) / 3 >= 128 else BLACK
                gx = ox + x
                gy = oy + y
                dx = gx - CX
                dy = gy - CY
                r_init = math.hypot(dx, dy)
                theta_init = math.atan2(dy, dx)

                # 3D perspective & swirl characteristics
                z = rng.uniform(-1.0, 1.0)
                # Swirling vortex speed and angle
                swirl_speed = rng.uniform(1.4, 3.0) * (1.0 if rng.random() > 0.12 else -0.6)
                r_target = r_init + rng.uniform(220.0, 1150.0)

                # Particle size class (0=distant star, 1=sharp midground, 2=foreground glow)
                if z > 0.45:
                    size_class = 2
                elif z > -0.35:
                    size_class = 1
                else:
                    size_class = 0

                particles.append((gx, gy, r_init, theta_init, r_target, swirl_speed, z, size_class, tone, a))

    return particles


def render_single_frame(args: tuple) -> None:
    t, particles, out_dir = args
    c = frame_curve(t)

    if c >= 1.0:
        # Fully dispersed -> empty transparent frame
        Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0)).save(
            out_dir / f"animation-{t:02d}.png"
        )
        return

    fade = 1.0 - 0.85 * c
    black_fade = max(0.0, 1.0 - 3.0 * c)

    alpha_buf = bytearray(WIDTH * HEIGHT)
    color_buf = [None] * (WIDTH * HEIGHT)

    for (gx, gy, r_init, theta_init, r_target, swirl_speed, z, size_class, tone, a) in particles:
        if tone == BLACK:
            x_cur = gx
            y_cur = gy
            p_alpha = int(a * black_fade)
        else:
            # 3D Cosmic Vortex spiral equations
            r_cur = r_init + (r_target - r_init) * c
            theta_cur = theta_init + swirl_speed * c

            # Perspective expansion & depth scaling
            depth_scale = 1.0 + (z * 0.35 * c)
            x_cur = int(CX + (r_cur * math.cos(theta_cur)) * depth_scale)
            y_cur = int(CY + (r_cur * math.sin(theta_cur)) * depth_scale)

            depth_alpha_mod = 1.2 if z > 0 else (0.75 if z < -0.4 else 1.0)
            p_alpha = int(min(255, a * fade * depth_alpha_mod))

        if 1 <= x_cur < WIDTH - 1 and 1 <= y_cur < HEIGHT - 1:
            idx = y_cur * WIDTH + x_cur
            if p_alpha > alpha_buf[idx]:
                alpha_buf[idx] = p_alpha
                color_buf[idx] = tone

            # Soft Depth-of-Field glow for foreground particles
            if size_class == 2 and tone == WHITE and p_alpha > 35:
                halo_a = p_alpha >> 1
                for nx, ny in ((x_cur + 1, y_cur), (x_cur - 1, y_cur), (x_cur, y_cur + 1), (x_cur, y_cur - 1)):
                    nidx = ny * WIDTH + nx
                    if halo_a > alpha_buf[nidx]:
                        alpha_buf[nidx] = halo_a
                        color_buf[nidx] = tone

    img = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    pxm = img.load()
    for y in range(HEIGHT):
        row = y * WIDTH
        for x in range(WIDTH):
            a_val = alpha_buf[row + x]
            if a_val:
                r, g, b = color_buf[row + x]
                pxm[x, y] = (r, g, b, a_val)

    img.save(out_dir / f"animation-{t:02d}.png")


def generate(logo_path: Path, out_dir: Path) -> None:
    src = Image.open(logo_path).convert("RGBA")
    target_w = 168
    ratio = target_w / src.width
    logo = src.resize((target_w, max(1, int(src.height * ratio))), Image.LANCZOS)
    ox = (WIDTH - logo.width) // 2
    oy = (HEIGHT - logo.height) // 2

    particles = sample_cosmic_particles(logo, ox, oy)
    out_dir.mkdir(parents=True, exist_ok=True)

    max_workers = min(os.cpu_count() or 4, 8)
    tasks = [(t, particles, out_dir) for t in range(FRAMES)]

    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as pool:
        list(pool.map(render_single_frame, tasks))

    print(f"generated {FRAMES} Cosmic Vortex HD frames (1920x1080) -> {out_dir} ({len(particles)} particles)")


def main() -> None:
    repo = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--logo", type=Path,
                        default=repo / "Branding" / "syntropia" / "splash" / "images" / "logo.png")
    parser.add_argument("--out", type=Path,
                        default=repo / "Branding" / "syntropia" / "plymouth")
    args = parser.parse_args()
    generate(args.logo, args.out)


if __name__ == "__main__":
    main()
