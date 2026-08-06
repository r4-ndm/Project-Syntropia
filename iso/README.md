# Syntropia ISO Build Pipeline

Reproducibly builds a CachyOS installer ISO with Syntropia-branded Calamares slides.

## Quick start

```bash
# From repo root:
sudo iso/build.sh
```

That's it. ~15 min first run (downloads ~990 packages), ~5 min subsequent runs.

Output: `iso/out/syntropia-YYYY.MM.DD-x86_64.iso`

## How it works

### Phase 1: mkarchiso (standard ISO)

1. Clones/pulls [CachyOS/CachyOS-Live-ISO](https://github.com/CachyOS/CachyOS-Live-ISO)
2. Applies two minimal patches:
   - Symlinks `packages.x86_64` → `packages_desktop.x86_64` (mkarchiso naming convention)
   - Adds `NoExtract` in `pacman.conf` to prevent slide conflicts
3. Runs `mkarchiso` — the official Arch ISO builder — which:
   - Bootstraps a fresh pacman root
   - Installs 991 packages (CachyOS kernels, KDE Plasma, Calamares, etc.)
   - Builds the squashfs rootfs with correct ownership/capabilities
   - Assembles the bootable hybrid ISO (BIOS + UEFI)

Output: `iso/out/syntropia-YYYY.MM.DD-x86_64-stock.iso`

### Phase 2: Slide injection (remaster)

The CachyOS branding slides come from the `cachyos-calamares-next` package. We can't overlay our slides via mkarchiso's airootfs/ because that creates file conflicts during package installation. Instead we remaster post-build:

1. Extract the ISO with `bsdtar`
2. Unsquashfs the root filesystem
3. Copy our 6 amended slide JXLs into `/usr/share/calamares/branding/cachyos/`
4. Repack squashfs with matching xz compression options
5. Rebuild the ISO with `xorriso` (BIOS + UEFI hybrid)

Output: `iso/out/syntropia-YYYY.MM.DD-x86_64.iso`

## Branding slides

Source: `Branding/syntropia/calamares/usr/share/calamares/branding/cachyos/slide{1-6}.jxl`

To update the slides:
1. Edit the PNGs in `Branding/syntropia/calamares/slides/`
2. Run the export pipeline to produce JXLs (see `Branding/NEXT.md`)
3. Re-run `sudo iso/build.sh`

## Requirements

| Tool | Package |
|------|---------|
| `mkarchiso` | `archiso` |
| `mksquashfs` | `squashfs-tools` |
| `xorriso` | `libisoburn` |
| `bsdtar` | `libarchive` |
| `unsquashfs` | `squashfs-tools` |
| `git` | `git` |

All available in Arch/CachyOS repos.

## Disk space

- Work directory: ~10 GB
- Package cache: ~10 GB (first run, shared with system pacman cache)
- Output ISO: ~3 GB

## Phases separately

```bash
# Just the mkarchiso build (skip slide injection)
sudo iso/build.sh --phase1

# Just inject slides into an existing stock ISO
sudo iso/build.sh --phase2
```

## Technical notes

- **Why not put slides in airootfs/ directly?** mkarchiso copies airootfs BEFORE installing packages. The `cachyos-calamares-next` package contains its own slide files, creating a conflict. `NoExtract` in pacman.conf is a partial workaround but not always reliable.
- **Why the two-phase approach?** Phase 1 uses the official, well-tested mkarchiso pipeline. Phase 2 does a surgical file swap in the already-correctly-built squashfs. This way we get correct ownership, capabilities, and initcpios from mkarchiso, and our slides from a simple file copy.
- **Volume label**: `SYNTROPIA` (vs stock `COS_YYYYMM`)

## CI/CD

The `build.sh` script is designed to be CI-friendly:
- `WORK_DIR` and `OUT_DIR` can be overridden via environment variables
- `SOURCE_DATE_EPOCH` controls the ISO date for reproducible builds
- Exit codes: 0 on success, 1 on error (suitable for CI pipelines)
