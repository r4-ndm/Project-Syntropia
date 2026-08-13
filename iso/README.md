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

Phase 2 also ships the rest of the Syntropia install experience (not just slides):
the apps wizard + TUI (`/etc/syntropia/`), paru in pacstrap `basePackages`, the
fastfetch ASCII-art branding (`/usr/share/syntropia/`), the **Syntropia identity**
(`os-release`/`lsb-release` generated from `transform.py`, copied into the installed
`/etc/` at install time), the `syntropia-${cpu}` hostname default, and the limine
bootloader identity sync. See `.agents/skills/iso-builder/SKILL.md` for the full
step list and pitfalls.

## Branding slides

Source: `Branding/syntropia/calamares/slides/slide{1-6}.jxl` (single source of truth)

To update the slides:
1. Edit the PNGs in `Branding/syntropia/calamares/slides/`
2. Run the export pipeline to produce JXLs (see `Branding/NEXT.md`)
3. Re-run `sudo iso/build.sh`

> **Gotcha (fixed):** slides used to be duplicated into
> `Branding/syntropia/calamares/usr/share/calamares/branding/cachyos/` and the
> build copied from there — editing only `slides/` never reached the ISO. Now
> `build.sh` reads `slides/` directly; the packaged dir only holds branding
> config (branding.desc, QML, icons). Don't re-create slide copies there.

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

## Testing the ISO in a VM — gotchas learned

These were discovered the hard way while validating the ISO with QEMU/KVM. Read before your next test boot.

### Calamares MUST run as root (the "Boost.Python error in job mount" trap)

**Symptom:** install fails right after partitioning with `Boost: Python error in job "mount"`.

**Real cause:** the mount job runs `mount -t btrfs -o defaults,noatime,compress=zstd /dev/vda3 /tmp/calamares-root-XXX/`, and if Calamares is running as the non-root `liveuser` this fails with *"must be superuser to use mount"*. The mount module swallows that into a warning (`Cannot mount /dev/vda3`), then tries `btrfs subvolume create /tmp/calamares-root-XXX/@` on a directory that is **not** a btrfs mount → `Inappropriate ioctl for device` (ENOTTY) → the job dies. The welcome page shows the telltale warning *"The installer is not running with administrator rights"*.

**Correct launch in a test VM** (Calamares as root, shown on the liveuser's Wayland session):

```bash
# as root on the guest (via qemu-guest-agent / ssh):
env WAYLAND_DISPLAY=wayland-0 XDG_RUNTIME_DIR=/run/user/1000 DISPLAY=:0 QT_QPA_PLATFORM=wayland \
    /usr/bin/calamares
```

- `pkexec calamares` **does not work headlessly in a VM** — polkit has no auth agent to show, and pkexec aborts with `Authorization required, but no authorization protocol specified`. The ISO's nopasswd rule (`/etc/polkit-1/rules.d/49-nopasswd_global.rules`, wheel group) is fine; the VM console just can't render the prompt.
- The stock CachyOS "Launch installer" button (cachyos-hello) is also unreliable in a VM for the same reason. On real hardware it works.
- Sanity check that the btrfs volume is healthy: `mount -t btrfs /dev/vda3 /tmp/t && btrfs subvolume create /tmp/t/@` — both must succeed. The full Calamares debug log lives at `/home/liveuser/.cache/calamares/session.log`.

### VM disk must be ≥ 8 GiB virtual

A freshly created qcow2 can look tiny (`du` shows ~196K for a sparse file) while its **virtual** size is fine. Calamares refuses to install below 8 GiB with *"There is not enough drive space"* — but it **is** running with admin rights by then, so that warning is the disk, not permissions.

- Check the virtual size with `qemu-img info` (needs root) or inside the guest: `lsblk -o NAME,SIZE /dev/vda`.
- Grow with `sudo qemu-img resize /var/lib/libvirt/images/<vm>.qcow2 30G` (only meaningful if the virtual size is actually small; otherwise leave it).

### The slideshow only plays during the Install step

`show.qml` runs while Calamares is writing the system (after you press **Install**), **not** on the welcome page. A white welcome page with the step pills is correct — don't chase it.

### Phase 2 "Stock ISO not found" — date stamping

The ISO name comes from `SOURCE_DATE_EPOCH` or today's date. Phase 2 needs a
`*-stock.iso` for that date; if your stock ISO is from a previous day (the usual
case after the first build), pin it:

```bash
sudo env SOURCE_DATE_EPOCH=$(date -d <stock-date> +%s) iso/build.sh --phase2
```

### "No bootable device" after rebooting to the installed system

**Cause**: the Calamares install didn't actually complete (aborted, or returned to
the live desktop before "All done"). The disk is still blank — a fresh qcow2 shows
`disk size` of ~196 KiB in `qemu-img info` even though its virtual size is 40G.

**Fix**: before detaching the ISO, verify the install wrote data — `qemu-img info
<disk>.qcow2 | grep 'disk size'` should be multi-GiB, and the screen must show
"All done — Restart now". If the disk is still ~196K, re-attach the ISO and re-run
Calamares.

### limine-snapper: "Target OS name 'syntropia OS' not found in /boot/limine.conf"

**Cause**: the bootloader (limine.conf) is generated at install time with the CachyOS
name, but the branding hook renames os-release to Syntropia at the END of install.
`limine-snapper-sync` matches the limine.conf OS entry against os-release
(PRETTY_NAME) or `TARGET_OS_NAME` in `/etc/default/limine`, and warns on boot.

**Fix**: `iso/hook-scripts/hook-branding-users.sh` sets the limine.conf entry to
`/+Syntropia OS` and pins `TARGET_OS_NAME="Syntropia OS"` in `/etc/default/limine`.
Keep both in sync whenever the os-release name changes.

### Verify the amended slides are actually in the ISO

After baking, compare the live ISO's slides against the repo (they must be byte-identical):

```bash
# in the guest:
md5sum /usr/share/calamares/branding/cachyos/slide{1..6}.jxl
# on the host:
md5sum Branding/syntropia/calamares/slides/slide{1..6}.jxl
```

To eyeball them, decode the JXLs with `djxl` and view a gallery. Slide 1 should read "WELCOME TO Syntropia".

## CI/CD

The `build.sh` script is designed to be CI-friendly:
- `WORK_DIR` and `OUT_DIR` can be overridden via environment variables
- `SOURCE_DATE_EPOCH` controls the ISO date for reproducible builds
- Exit codes: 0 on success, 1 on error (suitable for CI pipelines)
