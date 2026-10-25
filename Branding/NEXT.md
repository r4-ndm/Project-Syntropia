# Branding — Next Session Checklist

Working checklist for the Syntropia visual identity. The asset-drop is the
single folder: `Branding/syntropia/` (the PKGBUILDs copy it into
`/usr/share/syntropia/branding/`; the transform installs from there).

All tests green (240/240). Live system verified: the transform re-applies
branding end-to-end, and fastfetch shows the white triangle logo.

## Status recap
| Piece | Status |
|---|---|
| `logo.txt` (triangle, 21 rows, `*`/`4`, white via fastfetch color map) | ✅ shipped + live |
| `fastfetch-color.json` (all `#FFFFFF` — logo renders white) | ✅ shipped + live |
| GRUB | ✅ vanilla CachyOS — the transform leaves it untouched |
| `calamares/slides/slide1-6.png` + `.jxl` | ✅ amended (build.sh reads `slides/`) |
| `wallpaper.png` (1920×1080) | ✅ shipped + installed by transform |
| `plymouth/` boot animation (88-frame triangle swarm) | ✅ triangle particle swarm generated + shipped |
| `calamares/usr/.../icon.png, logo.png, welcome.png` | ⏳ present but not confirmed re-skinned |
| Identity (os-release/lsb-release/hostname, limine sync) | ✅ shipped in ISO (build.sh + branding hook) |

## 1. Custom Plymouth boot animation ✅ done
The boot splash is now the Syntropia **triangle particle swarm** — an 88-frame
full-screen animation mirroring CachyOS's `cachyos-bootanimation`: the triangle
holds full, disperses into a particle scatter, vanishes, then re-forms. It
ships in `Branding/syntropia/plymouth/` (88 `animation-*.png` +
`syntropia.plymouth`).

Regenerate the frames from the triangle mark:

```bash
python3 phase1/tools/generate_bootanimation.py
```

- White particles on transparent (Plymouth composites over black), 300×300.
- Deterministic (seeded RNG), so rebuilds are reproducible.
- The branding hook installs it to `/usr/share/plymouth/themes/syntropia` and
  sets `Theme=syntropia`, overriding CachyOS's `cachyos-bootanimation` (which a
  CachyOS package installs + selects at install time).

## 2. Calamares installer icons (GIMP)
The installer still shows CachyOS branding in three small PNGs:

```
Branding/syntropia/calamares/usr/share/calamares/branding/cachyos/
├── icon.png          # window/app icon
├── logo.png          # installer logo
└── welcome.png       # welcome banner
```

Edit in GIMP (normal PNGs — no format tricks). Keep the same filenames and
dimensions so they drop straight back in.

## 3. AUR
- Split into three packages — `syntropia-cli` (core command + plugin host),
  `syntropia-brews` (app helper), `syntropia` (the rebrand). Local-build
  PKGBUILDs live under `phase1/aur/<pkgname>/`, all reading pkgver from
  `phase1/cli/syntropia/__init__.py` (single source).
- Each needs a release tarball + sha256sums before AUR submission (see the
  header of each PKGBUILD).
- The pre-split `syntropia-git` VCS submission was retired — the three stable
  packages above supersede it. Regenerate a `-git` flavor from them if a
  VCS package is ever wanted.

## Verify
```bash
# sanity-check the whole suite
.venv/bin/pytest phase1/tests -q

# dry-run the full branding install plan (safe, changes nothing)
syntropia transform --check

# live: the packaged branding applies via the transform
syntropia transform --yes
fastfetch
```

## Reminders
- The Desktop copy (`~/Desktop/Syntropia-Branding/`) was deleted — everything
  lives in the repo now.
- JXL slides: GIMP can't open JXL. Edit the PNG, then regenerate with the
  canonical libjxl encoder (magick is measurably worse — ~6x higher error).
  `build.sh` reads `slides/` directly (single source of truth):
  ```bash
  cd Branding/syntropia/calamares
  for i in 1 2 3 4 5 6; do
    cjxl --effort 7 -q 90 slides/slide$i.png slides/slide$i.jxl
  done
  ```
- Loose PNGs at `Branding/` root — all swept and cleaned up.
  Assets live exclusively under `Branding/syntropia/`.
- Agent rules live in `agent-rules/` — the transform-safety rule (snapshot
  first, `--check`, never touch a non-test system) applies to any real run.
