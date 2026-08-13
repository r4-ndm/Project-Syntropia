# Branding — Next Session Checklist

Working checklist for the Syntropia visual identity. The asset-drop is the
single folder: `Branding/syntropia/` (the PKGBUILDs copy it into
`/usr/share/syntropia/branding/`; the transform installs from there).

All tests green (232/232). Live system verified: the transform re-applies
branding end-to-end, and fastfetch shows the white triangle logo.

## Status recap
| Piece | Status |
|---|---|
| `logo.txt` (triangle, 21 rows, `*`/`4`, white via fastfetch color map) | ✅ shipped + live |
| `fastfetch-color.json` (all `#FFFFFF` — logo renders white) | ✅ shipped + live |
| `grub/` (clean bg: no splash, GFXMODE=1920x1080, `bgrt_disable`) | ✅ shipped + applied |
| `calamares/slides/slide1-6.png` + `.jxl` | ✅ amended (build.sh reads `slides/`) |
| `wallpaper.png` (1920×1080) | ✅ shipped + installed by transform |
| `plymouth/` boot frames (36 animation + 30 throbber + misc, 74 files) | ⏳ **still stock CachyOS** — the real remaining work |
| `calamares/usr/.../icon.png, logo.png, welcome.png` | ⏳ present but not confirmed re-skinned |
| Identity (os-release/lsb-release/hostname, limine sync) | ✅ shipped in ISO (build.sh + branding hook) |

## 1. Custom Plymouth boot frames (the main open branding task)
The boot splash is still the stock CachyOS animation. Regenerate all
36 animation + 30 throbber frames from the triangle logo mark, using a
transparent square logo PNG (e.g. `Branding/iuuu66mage8.png` or a cropped
mark):

```bash
python3 phase1/tools/generate_spinner.py \
  --logo Branding/iuuu66mage8.png \
  --out Branding/syntropia/plymouth \
  --frames 30 --throbber 36 --size 32
```

- Overwrites `animation-0001..0036.png` + `throbber-0001..0030.png` in place.
- Keeps `bullet.png`, `entry.png`, `keyboard.png`, `lock.png`, `capslock.png`,
  `keymap-render.png`, `watermark.png`, `cachyos.plymouth` as-is.
- If the mark isn't square, the tool centers it on a transparent 32×32 canvas.
- Then re-run the transform (or rebuild + reinstall the package) so the new
  frames land in `/usr/share/plymouth/themes/syntropia/` — the content-hash
  refresh in `branding.py` re-applies when the shipped frames change.
- **Flag count check**: the on-disk stock layout is 36 animation + 30 throbber,
  and the tool's `--frames`/`--throbber` flags map 1:1 to that layout — so to
  regenerate the full set use `--frames 36 --throbber 30` (NOT the other way
  around; the original note had them swapped).

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
- `syntropia-git` is built and verified (final logo, white map, paru update
  code) — pending AUR submission.
- The stable `syntropia` needs a release tarball + sha256sums (see
  `phase1/aur/PKGBUILD` header).

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
- Loose PNGs at `Branding/` root — junk swept (19 deleted); the keepers
  (`iuuu66mage8.png` — used in §1, `r4ndm6688-1.png`, `syntropia.png`,
  `agent-brave-icon.png`, etc.) are source material for the art. Try to
  keep the root tidy going forward.
- Agent rules live in `agent-rules/` — the transform-safety rule (snapshot
  first, `--check`, never touch a non-test system) applies to any real run.
