---
name: iso-builder
description: Builds CachyOS installer ISOs with custom Calamares branding using mkarchiso + squashfs remastering. Use when the user asks to build, rebuild, or update the Syntropia installer ISO, patch branding slides into an ISO, or troubleshoot Calamares/ISO boot issues.
---

# ISO Builder

Builds a bootable CachyOS installer ISO with Syntropia branding — Calamares slides, the first-boot apps wizard + TUI, terminal ASCII art, and the Syntropia OS identity (os-release/lsb-release/hostname). Uses the official `mkarchiso` pipeline (Arch Linux's ISO builder) plus a post-build remaster step.

## When to use this skill

- User says "build the ISO", "update the installer", "bake the ISO"
- User wants to test branding slides in Calamares
- User asks about the ISO build pipeline or reproducible builds
- User encounters ISO boot issues, Calamares errors, or branding not showing

## Quick start

```bash
# From the Syntropia repo root:
sudo iso/build.sh            # full build (phases 1+2)
sudo iso/build.sh --phase2   # remaster only — the fast path (~10 min)
```

Output: `iso/out/syntropia-YYYY.MM.DD-x86_64.iso`

**⚠ SOURCE_DATE_EPOCH:** the ISO name is date-stamped from `SOURCE_DATE_EPOCH` (or today's date). Phase 2 needs a `*-stock.iso` matching that date; if the stock ISO is from a previous day (the usual case after the first build), pin it:

```bash
sudo env SOURCE_DATE_EPOCH=$(date -d 2026-08-12 +%s) iso/build.sh --phase2
```

## The build script

Located at `iso/build.sh`. Two phases:

### Phase 1: mkarchiso

- Clones/pulls [CachyOS/CachyOS-Live-ISO](https://github.com/CachyOS/CachyOS-Live-ISO)
- Applies patches:
  1. Symlinks `packages.x86_64` → `packages_desktop.x86_64` (mkarchiso naming)
  2. Adds `NoExtract` for slide files in `pacman.conf` [options] section (safety net)
  3. **Stale-work-dir guard**: clears the mkarchiso `build._build_buildmode_*` / `iso._build_iso_image` markers when the expected stock ISO is missing, so a previously-renamed stock ISO forces re-assembly instead of silently exiting
- Runs `mkarchiso` → `iso/out/syntropia-*-stock.iso`

### Phase 2: Remaster (injection)

1. Extract the stock ISO (`bsdtar`), unsquash the rootfs
2. **Slides**: copy `slide{1-6}.jxl` into `/usr/share/calamares/branding/cachyos/`
3. **pacman.conf NoUpgrade+NoExtract** (must stay inside `[options]`): protects the slides AND the Calamares configs we patch — `settings_online.conf`, `settings_offline.conf`, `etc/calamares/modules/pacstrap.conf`, `etc/calamares/modules/users.conf` — from the live-boot `cachyos-calamares-next` update
4. **display-manager symlink** (plasmalogin, fallback sddm) so the live desktop auto-starts
5. **Apps wizard + TUI** → `/etc/syntropia/`: `syntropia-apps-wizard.sh` (TUI-only driver), `apps.list`, and `dialog/` (source + a freshly built static TUI binary). First-boot autostart entry → `/etc/xdg/autostart/syntropia-apps.desktop`
6. **Calamares install wiring** (patched into `settings_online/offline.conf`):
   - `syntropia_wizard` shellprocess — copies the wizard + autostart entry into the installed root
   - `paru` added to pacstrap `basePackages` — every install ships paru (NoUpgrade-protected)
   - `syntropia_branding` shellprocess — copies branding + identity into the installed root
7. **Terminal ASCII art** → `/usr/share/syntropia/` (logo.txt, `branding/fastfetch-color.json`) + `/etc/skel/.config/fastfetch/config.jsonc` (generated from the repo's `build_fastfetch_conf` — same single source as `syntropia transform`)
8. **Identity**: `os-release` + `lsb-release` generated from `transform.py`'s `OS_RELEASE_CONTENT` (AST-extracted at build time — the same constant `test_transform.py::test_os_release_identity_contract` pins). Shipped to `/usr/share/syntropia/branding/`; the branding hook copies them into the installed `/etc/`
9. **Hostname default**: `users.conf` hostname template `cachyos-${cpu}` → `syntropia-${cpu}` (user can still override in Calamares)
10. Repack squashfs (`-comp xz -b 1M -Xbcj x86 -Xdict-size 1M`), update checksum, remove the unsquashed rootfs, rebuild hybrid ISO with `xorriso` (BIOS + UEFI, volume label `SYNTROPIA`)

### The install-time branding hook

The `syntropia_branding` shellprocess runs in the **live env** (not the chroot) with `${ROOT}` = the target root. It:

- copies `/usr/share/syntropia/` → `${ROOT}/usr/share/syntropia/`
- copies `os-release` + `lsb-release` → `${ROOT}/etc/` (the installed system reports Syntropia; the live ISO stays CachyOS)
- runs `hook-branding-users.sh` (→ `/etc/syntropia/`): copies fastfetch/fish config into existing user homes AND applies the limine identity sync (below)

## Why two phases?

We can't put slides in mkarchiso's `airootfs/` overlay because:
1. mkarchiso copies airootfs files BEFORE installing packages
2. The `cachyos-calamares-next` package contains its own slide files
3. This creates a file conflict that `NoExtract` doesn't reliably prevent

The two-phase approach: build a clean ISO with mkarchiso (guarantees correct ownership, capabilities, initcpios), then surgically swap everything in the finished squashfs.

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

### Phase 2 fails: "Stock ISO not found"
**Cause**: the ISO is date-stamped from `SOURCE_DATE_EPOCH`/today, but the stock ISO (`syntropia-*-stock.iso`) is from a previous day.
**Fix**: `sudo env SOURCE_DATE_EPOCH=$(date -d <stock-iso-date> +%s) iso/build.sh --phase2`.

### Phase 1 silently produces no ISO (stale work dir)
**Cause**: mkarchiso's completed-step markers exist but the stock ISO was renamed away, so mkarchiso concludes the build is done and exits without an ISO.
**Fix**: handled automatically by the stale-work-dir guard in `build.sh` (clears the ISO-assembly markers). If you hit it, delete `iso/work/mkarchiso-work/build._build_buildmode_*` and `iso._build_iso_image` and rebuild.

### limine-snapper: "Target OS name 'syntropia OS' not found in /boot/limine.conf"
**Cause**: the bootloader (limine.conf) is generated at install time with the CachyOS name, but os-release is renamed to Syntropia at the END of install. `limine-snapper-sync` reads the OS entry name from limine.conf and matches it against os-release PRETTY_NAME (or `TARGET_OS_NAME` in `/etc/default/limine`) — mismatch → warning/notification on every boot.
**Fix**: `hook-branding-users.sh` syncs both sides: the limine.conf OS entry `/ +CachyOS` → `/ +Syntropia OS`, and pins `TARGET_OS_NAME="Syntropia OS"` in `/etc/default/limine`. Keep these in sync whenever the os-release name changes.

### Calamares hook fails with "Missing variables"
**Cause**: the Calamares shellprocess module macro-expands every command string with KWordMacroExpander('$'), which treats BARE `$word` as a macro. Any shell variable written as `$foo` in a hook command aborts the whole job before it runs.
**Fix**: never put bare `$vars` in a hook command string. Put shell logic in a script file (e.g. `hook-branding-users.sh`) and call it from the hook.

### os-release identity drift
**Cause**: the ISO and `syntropia transform` each carry the identity; a second copy would drift.
**Fix**: single source of truth = `OS_RELEASE_CONTENT` in `phase1/cli/syntropia/transform.py`. `build.sh` AST-extracts it at build time, and `test_transform.py::test_os_release_identity_contract` pins `ID=syntropia` + `ID_LIKE="arch cachyos"`. Change it in transform.py only.

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

1. Edit the source of truth (slides PNGs, `phase1/wizard/apps.list`, `dialog/main.go`, `transform.py` OS_RELEASE_CONTENT, etc.) and commit
2. Build: `sudo env SOURCE_DATE_EPOCH=$(date -d <stock-date> +%s) iso/build.sh --phase2`
3. Verify it baked in: `bsdtar -xf` the ISO, `unsquashfs` the sfs, and diff the shipped files against the repo (wizard script, os-release, apps.list, TUI binary)
4. Fresh-install test in the VM: reset the disk (fresh qcow2), attach the ISO as cdrom (boot order 1), boot, run Calamares, reboot from disk
5. Verify: wizard fires at first login, `fastfetch`/`lsb_release`/hostname report Syntropia, no limine-snapper notification

## Disk usage

- Work directory (`iso/work/`): ~10 GB (gitignored)
- Package cache: shared with system at `/var/cache/pacman/pkg/`
- Output ISOs: ~3 GB each (gitignored via `*.iso` pattern)
