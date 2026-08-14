# Syntropia Branding Asset Drop

This is the **single** home for all Syntropia visual branding — the amended
assets *and* the reference set, merged from the CachyOS official extraction
(`cachyos-desktop-linux-260628.iso` + installed system).

Two roles in one folder:

1. **`syntropia transform --branding-dir Branding/syntropia`** consumes the
   asset-drop layout (plymouth/, wallpaper.png, logo.txt).
2. **The ISO builder** (Week 4) consumes the calamares pieces for the install
   image.

## Expected layout

```
syntropia/
├── logo.txt                   # terminal/fastfetch ASCII logo (shipped ✓)
│                              #   made from a PNG via tools/png_to_ascii.py
├── fastfetch-color.json       # color map for logo.txt ($N -> #RRGGBB) — kept
│                              #   for when color placeholders return
├── plymouth/                  # whole boot-splash theme (copied as-is)
│   ├── syntropia.plymouth    # theme descriptor (Name=Syntropia)
│   ├── animation-00..87.png  # 88-frame triangle particle swarm — regenerable
│   │                         #   via phase1/tools/generate_bootanimation.py
│   └── throbber-00..40.png   # 41 boot-progress frames
├── calamares/                # installer branding (for the ISO builder)
│   ├── slides/               # SINGLE source of truth for slides (amended ✓)
│   │   └── slide1-6.png + .jxl  # the show.qml slideshow uses 6 slides
│   └── usr/share/calamares/branding/cachyos/
│       ├── branding.desc     # installer branding config
│       ├── show.qml / calamares-sidebar.qml / stylesheet.qss
│       └── icon.png / logo.png / welcome.png   # installer icons (unamended)
│                             # NOTE: no slide copies here — build.sh reads
│                             #   slides/ directly (single source of truth)
└── wallpaper.png             # 1920x1080 desktop wallpaper (amended ✓)
```

## How the transform consumes it
| File | Becomes | Idempotency marker |
|---|---|---|
| `logo.txt` | `/usr/share/syntropia/logo.txt` (fallback: built-in art) | rewrite (idempotent) |
| `fastfetch-color.json` | merged into fastfetch config `logo.color` | rewrite (idempotent) |
| `plymouth/` | `/usr/share/plymouth/themes/syntropia/` | `.syntropia-branded` in theme dir |
| `calamares/slides/slide*.png` + `.jxl` | ISO installer slideshow — build.sh reads these directly (single source of truth) | n/a |
| `calamares/usr/.../icon.png, logo.png, welcome.png` | Installer logo / window icon / welcome banner | n/a |
| `wallpaper.png` | `~/.local/share/backgrounds/syntropia/wallpaper.png` | target exists |

## Amended-vs-pending status
| Piece | Status |
|---|---|
| `calamares/slides/slide1-6.png` + `.jxl` | ✅ amended |
| `calamares/.../icon.png`, `logo.png`, `welcome.png` | ⏳ still CachyOS originals |
| `plymouth/` boot animation (triangle swarm) | ✅ generated + shipped |
| `wallpaper.png` | ✅ amended |

## Shortcuts
- **Terminal logo from a PNG**: design a mark in GIMP, then convert it to the
  ASCII logo the transform ships:
  ```bash
  python3 phase1/tools/png_to_ascii.py --input mark.png --width 60 --blocks --out Branding/syntropia/logo.txt
  ```
  Tweak with `--invert` (dark-on-light art), `--bg white` (transparent logos
  meant for light backgrounds), or `--contrast`. See the tool's `--help`.
- **Keep the colours**: fastfetch resolves `$N` placeholders in the art via the
  `logo.color` config map, so convert with a palette and ship both files:
  ```bash
  python3 phase1/tools/png_to_ascii.py --input mark.png --width 60 --color --colors 8 \
      --contrast --out Branding/syntropia/logo.txt \
      --color-map Branding/syntropia/fastfetch-color.json
  ```
  `--colors` is the palette size (max 9 — fastfetch's placeholder limit);
  `--threshold` lifts dark pixels to spaces. The transform merges the map
  into the fastfetch config automatically.
- **Boot animation frames**: don't hand-edit — regenerate the 88-frame triangle
  swarm with
  `python3 phase1/tools/generate_bootanimation.py --logo Branding/syntropia/menu-icon.png`
  (defaults write straight into `plymouth/`).
- **JXL slides**: GIMP can't open JXL — edit the PNG in `calamares/slides/`,
  then regenerate with the canonical libjxl encoder (better fidelity than
  ImageMagick — measured ~6x lower error on these slides). The JXL lives in
  `calamares/slides/` alongside the PNG — build.sh reads it from there, so
  there is nothing else to copy:
  ```bash
  for i in 1 2 3 4 5 6; do
    cjxl --effort 7 -q 90 slides/slide$i.png slides/slide$i.jxl
  done
  ```
- Dry-run first, always: `syntropia transform --check --branding-dir Branding/syntropia`
