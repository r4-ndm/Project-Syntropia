---
name: iso-builder
description: Builds CachyOS installer ISOs with custom Calamares branding using mkarchiso + squashfs remastering. Use when the user asks to build, rebuild, or update the Syntropia installer ISO, patch branding slides into an ISO, or troubleshoot Calamares/ISO boot issues.
---

# ISO Builder

Builds a bootable CachyOS installer ISO with Syntropia-branded Calamares slides. Uses the official `mkarchiso` pipeline (Arch Linux's ISO builder) plus a post-build remaster step for slide injection.

## When to use this skill

- User says "build the ISO", "update the installer", "bake the ISO"
- User wants to test branding slides in Calamares
- User asks about the ISO build pipeline or reproducible builds
- User encounters ISO boot issues, Calamares errors, or branding not showing

## Quick start

```bash
# From the Syntropia repo root:
sudo iso/build.sh
```

Output: `iso/out/syntropia-YYYY.MM.DD-x86_64.iso`

First run: ~15 min (downloads ~990 packages to system pacman cache). Subsequent runs: ~5 min.

## The build script

Located at `iso/build.sh` in the project repo. Two phases:

### Phase 1: mkarchiso
- Clones/pulls [CachyOS/CachyOS-Live-ISO](https://github.com/CachyOS/CachyOS-Live-ISO)
- Applies patches:
  1. Symlinks `packages.x86_64` → `packages_desktop.x86_64` (mkarchiso naming)
  2. Adds `NoExtract` for slide files in `pacman.conf` [options] section (safety net)
- Runs `mkarchiso` — bootstraps pacman root, installs 991 packages, builds initcpios, produces hybrid ISO
- Output: `iso/out/syntropia-*-stock.iso`

### Phase 2: Slide injection (remaster)
- Extracts the stock ISO with `bsdtar`
- Unsquashes the root filesystem (`unsquashfs`)
- Copies amended slides (slide1-6.jxl) into `/usr/share/calamares/branding/cachyos/`
- Repacks squashfs with matching options: `-comp xz -b 1M -Xbcj x86 -Xdict-size 1M`
- Updates checksum
- Removes unsquashed rootfs (keeps ISO size ~3GB)
- Rebuilds hybrid ISO with `xorriso` (BIOS + UEFI, volume label `SYNTROPIA`)
- Output: `iso/out/syntropia-YYYY.MM.DD-x86_64.iso`

## Why two phases?

We can't put slides in mkarchiso's `airootfs/` overlay because:
1. mkarchiso copies airootfs files BEFORE installing packages
2. The `cachyos-calamares-next` package contains its own slide files
3. This creates a file conflict that `NoExtract` doesn't reliably prevent

The two-phase approach: build a clean ISO with mkarchiso (guarantees correct ownership, capabilities, initcpios), then surgically swap slides in the finished squashfs.

## Branding slides source

```
Branding/syntropia/calamares/usr/share/calamares/branding/cachyos/slide{1-6}.jxl
```

To update slides: edit the PNGs in `Branding/syntropia/calamares/slides/`, export JXLs (see `Branding/NEXT.md`), then rebuild.

## Requirements

| Tool         | Package          |
|-------------|-----------------|
| mkarchiso   | archiso         |
| mksquashfs  | squashfs-tools  |
| xorriso     | libisoburn      |
| bsdtar      | libarchive      |
| unsquashfs  | squashfs-tools  |
| git         | git             |

All in Arch/CachyOS repos. The script checks these and exits early if missing.

## Common pitfalls and fixes

### "boost.python error in mount job" during Calamares install
**Cause**: squashfs was rebuilt without proper ownership (e.g., as non-root user with fakeroot).  
**Fix**: Always run `iso/build.sh` with `sudo`. mkarchiso and the mksquashfs remaster both need root.

### "isohdpfx.bin not found" during xorriso
**Cause**: Wrong path — it's at `boot/syslinux/isohdpfx.bin` inside the remaster dir, not at the root.  
**Fix**: Already fixed in `iso/build.sh`. Use the script, not manual xorriso.

### ISO is 10GB instead of 3GB
**Cause**: Forgot to remove the unsquashed `rootfs/` directory before running xorriso.  
**Fix**: The script now removes it automatically. Rebuild.

### File conflicts during mkarchiso ("slide1.jxl exists in filesystem")
**Cause**: Slides were placed in `airootfs/` before package installation.  
**Fix**: Don't put slides in airootfs. Use Phase 2 remastering instead.

### "packages.x86_64 does not exist"
**Cause**: CachyOS names it `packages_desktop.x86_64`.  
**Fix**: The script symlinks it automatically.

## Typical workflow

1. User updates slides → `git commit` the new PNGs/JXLs
2. Run `sudo iso/build.sh`
3. Test in VM: boot the ISO, launch Calamares, verify slides appear
4. If slides look good: done. If not: fix slides, rebuild (Phase 2 only: `sudo iso/build.sh --phase2`)

## Disk usage

- Work directory (`iso/work/`): ~10 GB (gitignored)
- Package cache: shared with system at `/var/cache/pacman/pkg/`
- Output ISOs: ~3 GB each (gitignored via `*.iso` pattern)
