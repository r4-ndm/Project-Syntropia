# Branding — Next Session Checklist

Continue where we left off. All tests green (78/78), nothing broken.
The asset-drop is the single folder: `Branding/syntropia/`.

## Status recap
| Piece | Status |
|---|---|
| `logo.txt` (triangle, 23 rows, `*`/`4`, clean bg) | ✅ shipped |
| `grub/splash.png` + `grub/syslinux-splash.png` | ✅ amended |
| `calamares/slides/slide1-6.png` + `.jxl` | ✅ amended (slideshow uses 6) |
| `calamares/usr/.../icon.png, logo.png, welcome.png` | ⏳ todo |
| `plymouth/` boot frames (74 files) | ⏳ todo |
| `wallpaper.png` | ⏳ todo |
| Commit the branding set | ⏳ todo |
| Validate on the CachyOS VM | ⏳ todo |

## 1. Plymouth boot frames (fastest — no GIMP needed)
Regenerate all 30 animation + 36 throbber frames from the triangle logo mark.
Use a transparent square logo PNG (e.g. `Branding/iuuu66mage8.png` or a
cropped mark):

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

## 3. Wallpaper (GIMP)
Make a 1920×1080 desktop wallpaper and save as:

```
Branding/syntropia/wallpaper.png
```

The transform currently reports `wallpaper: no wallpaper.png asset found,
skipping` — this file fixes that. The transform installs it to
`~/.local/share/backgrounds/syntropia/wallpaper.png` and auto-applies on
GNOME/KDE.

## 4. Finish + verify
```bash
# sanity-check the whole suite (host)
.venv/bin/pytest phase1/tests -q

# dry-run the full branding install plan (safe, changes nothing)
syntropia transform --check --branding-dir Branding/syntropia
# (or:) PYTHONPATH=phase1/cli .venv/bin/python -m syntropia.transform \
#      --check --branding-dir Branding/syntropia
```

Then commit the branding set (merged syntropia folder, amended assets,
README) and push.

## Reminders
- The Desktop copy (`~/Desktop/Syntropia-Branding/`) was deleted — everything
  lives in the repo now.
- JXL slides: GIMP can't open JXL. Edit the PNG, then regenerate with the
  canonical libjxl encoder (magick is measurably worse — ~6x higher error):
  ```bash
  cd Branding/syntropia/calamares
  for i in 1 2 3 4 5 6; do
    cjxl --effort 7 -q 90 slides/slide$i.png slides/slide$i.jxl
    cp slides/slide$i.jxl usr/share/calamares/branding/cachyos/slide$i.jxl
  done
  ```
- Agent rules live in `agent-rules/` — the transform-safety rule (snapshot
  first, `--check`, never touch a non-test system) applies to any real run.
