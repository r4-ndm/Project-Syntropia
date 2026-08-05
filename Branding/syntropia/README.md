# Syntropia Branding Asset Drop

This is the **input folder** for `syntropia transform --branding-dir Branding/syntropia`.
Drop your **amended** files here (edited in GIMP from the CachyOS official
assets — see `~/Desktop/Syntropia-Branding/cachyos-official/` for the originals).

Expected layout:

```
syntropia/
├── logo.txt                   # terminal/fastfetch ASCII logo (optional)
│                              #   made from a PNG via tools/png_to_ascii.py
├── fastfetch-color.json       # color map for logo.txt ($N -> #RRGGBB) —
│                              #   written by png_to_ascii.py --color --color-map
├── plymouth/                  # whole boot-splash theme (copied as-is)
│   ├── cachyos.plymouth      # theme descriptor (keep, rename Name=Syntropia)
│   ├── animation-0001.png    # 30 frames — regenerable via
│   ├── ...                   #   phase1/tools/generate_spinner.py
│   ├── throbber-0001.png     # 36 frames (same script)
│   └── watermark.png         # the boot-screen logo (256x86, transparent)
├── grub/
│   └── splash.png            # 1920x1080 boot menu background
└── wallpaper.png             # 1920x1080 desktop wallpaper
```

## How the transform consumes it
| File | Becomes | Idempotency marker |
|---|---|---|
| `logo.txt` | `/usr/share/syntropia/logo.txt` (fallback: built-in art) | rewrite (idempotent) |
| `fastfetch-color.json` | merged into fastfetch config `logo.color` | rewrite (idempotent) |
| `plymouth/` | `/usr/share/plymouth/themes/syntropia/` | `.syntropia-branded` in theme dir |
| `grub/splash.png` | `/boot/grub/splash.png` | `splash.png.syntropia-branded` |
| `wallpaper.png` | `~/.local/share/backgrounds/syntropia/wallpaper.png` | target exists |

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
  python3 phase1/tools/png_to_ascii.py --input mark.png --width 60 --color --colors 8 \\
      --contrast --out Branding/syntropia/logo.txt \\
      --color-map Branding/syntropia/fastfetch-color.json
  ```
  `--colors` is the palette size (max 9 — fastfetch's placeholder limit);
  `--threshold` lifts dark pixels to spaces. The transform merges the map
  into the fastfetch config automatically.
- **Boot spinner frames**: don't hand-edit — run
  `python3 phase1/tools/generate_spinner.py --logo Branding/syntropia/mark.png --out Branding/syntropia/plymouth --frames 30 --throbber 36`
  once you have a transparent logo mark.
- Dry-run first, always: `syntropia transform --check --branding-dir Branding/syntropia`
