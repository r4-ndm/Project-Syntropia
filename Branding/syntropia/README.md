# Syntropia Branding Asset Drop

This is the **single** home for all Syntropia visual branding — the amended
assets *and* the reference set, merged from the CachyOS official extraction
(`cachyos-desktop-linux-260628.iso` + installed system).

Two roles in one folder:

1. **`syntropia transform --branding-dir Branding/syntropia`** consumes the
   asset-drop layout (plymouth/, grub/, wallpaper.png, logo.txt).
2. **The ISO builder** (Week 4) consumes the calamares + syslinux pieces for
   the install image.

## Expected layout

```
syntropia/
├── logo.txt                   # terminal/fastfetch ASCII logo (shipped ✓)
│                              #   made from a PNG via tools/png_to_ascii.py
├── fastfetch-color.json       # color map for logo.txt ($N -> #RRGGBB) — kept
│                              #   for when color placeholders return
├── plymouth/                  # whole boot-splash theme (copied as-is)
│   ├── cachyos.plymouth      # theme descriptor (keep, rename Name=Syntropia)
│   ├── animation-0001.png    # 30 frames — regenerable via
│   ├── ...                   #   phase1/tools/generate_spinner.py
│   ├── throbber-0001.png     # 36 frames (same script)
│   └── watermark.png         # the boot-screen logo (256x86, transparent)
├── grub/
│   ├── splash.png            # 1920x1080 boot menu background (amended ✓)
│   └── syslinux-splash.png   # same art, legacy BIOS boot path
├── calamares/                # installer branding (for the ISO builder)
│   ├── slides/               # editable PNG masters (amended ✓)
│   │   └── slide1-6.png      # the show.qml slideshow uses 6 slides
│   └── usr/share/calamares/branding/cachyos/
│       ├── branding.desc     # installer branding config
│       ├── show.qml / calamares-sidebar.qml / stylesheet.qss
│       ├── icon.png / logo.png / welcome.png   # installer icons (unamended)
│       └── slide1-6.jxl      # JXL slides the installer actually loads
│                             #   (regenerate from PNGs: cjxl --effort 7 -q 90 slide1.png slide1.jxl)
└── wallpaper.png             # 1920x1080 desktop wallpaper (amended ✓)
```

## How the transform consumes it
| File | Becomes | Idempotency marker |
|---|---|---|
| `logo.txt` | `/usr/share/syntropia/logo.txt` (fallback: built-in art) | rewrite (idempotent) |
| `fastfetch-color.json` | merged into fastfetch config `logo.color` | rewrite (idempotent) |
| `plymouth/` | `/usr/share/plymouth/themes/syntropia/` | `.syntropia-branded` in theme dir |
| `grub/splash.png` | `/boot/grub/splash.png` | `splash.png.syntropia-branded` |
| `grub/syslinux-splash.png` | ISO legacy-boot splash (for ISO builder) | n/a |
| `calamares/slides/slide*.png` | ISO installer slideshow (for ISO builder) | n/a |
| `calamares/usr/.../slide*.jxl` | Same slides in JXL — the installer loads these | n/a |
| `calamares/usr/.../icon.png, logo.png, welcome.png` | Installer logo / window icon / welcome banner | n/a |
| `wallpaper.png` | `~/.local/share/backgrounds/syntropia/wallpaper.png` | target exists |

## Amended-vs-pending status
| Piece | Status |
|---|---|
| `grub/splash.png` + `syslinux-splash.png` | ✅ amended |
| `calamares/slides/slide1-6.png` + `.jxl` | ✅ amended |
| `calamares/.../icon.png`, `logo.png`, `welcome.png` | ⏳ still CachyOS originals |
| `plymouth/` frames (74 files) | ⏳ still originals — regenerate via spinner tool |
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
- **Boot spinner frames**: don't hand-edit — run
  `python3 phase1/tools/generate_spinner.py --logo Branding/syntropia/mark.png --out Branding/syntropia/plymouth --frames 30 --throbber 36`
  once you have a transparent logo mark.
- **JXL slides**: GIMP can't open JXL — edit the PNG in `calamares/slides/`,
  then regenerate with the canonical libjxl encoder (better fidelity than
  ImageMagick — measured ~6x lower error on these slides) and drop it into
  the packaged dir:
  ```bash
  for i in 1 2 3 4 5 6; do
    cjxl --effort 7 -q 90 slides/slide$i.png slides/slide$i.jxl
    cp slides/slide$i.jxl usr/share/calamares/branding/cachyos/slide$i.jxl
  done
  ```
- Dry-run first, always: `syntropia transform --check --branding-dir Branding/syntropia`
