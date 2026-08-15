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
5. **Apps wizard + TUI** → `/etc/syntropia/`: `app-wiz4rd` (TUI-only driver), `apps.list`, and `dialog/` (source + a freshly built static TUI binary), extracted from the vendored `iso/vendor/app-wiz4rd-*.tar.gz` (sha256-pinned — the **app-wiz4rd repo** is the single source of truth; there is no in-repo copy). Autostart entry ships as a template in `/etc/syntropia/syntropia-apps.desktop` (NOT the live autostart dir — see step 6)
6. **Calamares install wiring** (patched into `settings_online/offline.conf`):
   - `syntropia_wizard` shellprocess — copies the wizard + autostart entry into the installed root (autostart comes from `/etc/syntropia/syntropia-apps.desktop`, so the live session stays vanilla)
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

## Base refresh policy (git HEAD — deliberate)

Phase 1 builds the stock ISO from **CachyOS-Live-ISO git HEAD**, not from CachyOS's published release snapshot. This is a deliberate decision, not an accident:

**Why HEAD (pros):** always current (no waiting for quarterly snapshots); fast refresh (git pull vs a 3 GB download); you see upstream profile breakage first while you're testing anyway; no version skew between the installer and the repos; fixes flow in automatically.

**Why not the released ISO (cons of HEAD):** HEAD is untested as a whole snapshot — a half-merged profile change can land in your ISO; builds are implicitly coupled to whatever upstream pushed that day; and ISOs are harder to reproduce (you'd need to pin a commit).

**Decision:** keep git HEAD for now — Syntropia is pre-1.0, has no users depending on installer stability, and the fast feedback loop is worth more than a quarterly pin. **Revisit this when real users exist** and a "it worked last quarter" complaint appears — that's the signal to switch to building from the published release ISO.

**Refresh-log convention:** every phase-1 refresh appends **one line** to `iso/BASE-REFRESH.md`:

```
2026-08-13  base=HEAD@<upstream-commit-short>  breakage=none  (or: breakage=profile X broke, pinned to <commit>)
```

This keeps ISO behavior reproducible and turns "why is this ISO different?" into a one-grep answer. Log it in the same commit as the build if you commit one.

## Release source tarball (AUR) — deterministic hash rules

The three AUR PKGBUILDs (`phase1/aur/syntropia-cli`, `-brews`, `syntropia`) all
fetch one shared source tarball (`release/syntropia-$pkgver.tar`, gitignored)
and pin its sha256 in `sha256sums=()`. Four rules keep that hash **stable
across rebuilds** — breaking any one silently breaks the AUR install:

1. **Exclude `phase1/aur` from the tarball.** It's the packaging itself and
   lives in the AUR repos, not in the source archive. If it's included, editing
   the sha256sums inside the PKGBUILDs changes the tarball's own hash — a
   circular dependency that makes the sums unreproducible.
2. **Archive `HEAD^{tree}`, not `HEAD`.** `git archive HEAD` embeds a
   `comment=<commit-id>` pax header, so the hash changes on *every* commit even
   when the shipped files are byte-identical. Archiving the tree drops that
   header — the hash then depends only on the files, not the commit id.
3. **Ship plain uncompressed `.tar`, not `.tar.gz`.** gzip output varies by
   zlib version, so the same files compress to different bytes on Arch vs
   Ubuntu CI — the sha would pass locally but fail on any other machine. The
   source is small enough (~11 MB) that compression buys nothing.
4. **Pin `--mtime`.** Otherwise `git archive` stamps the *current time* as entry
   mtimes, so the tarball hash changes on every run (same tree, different
   bytes).

Regenerate command (documented in each PKGBUILD header):

```bash
git archive --format=tar --prefix="syntropia-$pkgver/" \
  --mtime="2026-08-14 12:00:00 UTC" \
  -o release/syntropia-$pkgver.tar HEAD^{tree} -- . ':(exclude)phase1/aur'
```

After regenerating, update all three `sha256sums=` and regenerate each
`.SRCINFO` (`makepkg --printsrcinfo > .SRCINFO`). Verify with `makepkg -o` on a
scratch copy — it must report `Validating source files with sha256sums… Passed`.

> `app-wiz4rd` follows the same rules (it was where both the `HEAD^{tree}` and
> plain-`.tar` lessons were learned), with the extra exclusion of `.github/`
> and `scripts/` from its source archive.

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
**Fix**: single source of truth = `OS_RELEASE_CONTENT` in `phase1/cli/transform/syntropia_transform/transform.py`. `build.sh` AST-extracts it at build time, and `test_transform.py::test_os_release_identity_contract` pins `ID=syntropia` + `ID_LIKE="arch cachyos"`. Change it in transform.py only.

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

1. Edit the source of truth (slides PNGs, `transform.py` OS_RELEASE_CONTENT, etc.) and commit. Wizard changes happen in the **app-wiz4rd repo** (`github.com/r4-ndm/app-wiz4rd`): edit there, regenerate its release tarball into `iso/vendor/`, and update `APP_WIZ4RD_SHA256` in `build.sh` (see the header comment there for the exact `git archive` command)
2. **Only when refreshing the base:** run phase 1 (`iso/build.sh --phase1`), then append the one-line entry to `iso/BASE-REFRESH.md` (date, upstream commit, known breakage) per the base-refresh policy above
3. Build: `sudo env SOURCE_DATE_EPOCH=$(date -d <stock-date> +%s) iso/build.sh --phase2`
4. Verify it baked in: `bsdtar -xf` the ISO, `unsquashfs` the sfs, and diff the shipped files against the vendored tarball (wizard script, os-release, apps.list, TUI binary)
5. Fresh-install test in the VM: reset the disk (fresh qcow2), attach the ISO as cdrom (boot order 1), boot, run Calamares, reboot from disk
6. Verify: wizard fires at first login, `fastfetch`/`lsb_release`/hostname report Syntropia, no limine-snapper notification

## Snapshot-revert workflow (fast Layer 2 tests)

A full ISO → Calamares install → reboot cycle costs ~20-25 min. Most of that is
the reinstall, not the build. Once you have a **verified install**, snapshot it
and revert instead of reinstalling.

**When to snapshot vs. reinstall:**
- **Revert** (fast, ~30s) when testing changes that land on an *installed*
  system: the wizard behavior, `syntropia transform` output, branding files,
  identity files, hook scripts. Revert to the snapshot, apply/verify the change
  on the running system, done.
- **Reinstall** (slow) only when the *install flow itself* changed: Calamares
  hooks, the wizard autostart entry, paru-in-basePackages, the limine identity
  sync that runs at install time. Those only take effect during install, so a
  snapshot can't substitute.

**Take the snapshot** after a fully verified fresh install (identity reports
Syntropia, wizard completed, no limine warning):

```bash
virsh -c qemu:///system snapshot-create-as syntropia-iso clean-installed \
  --description "Verified: Syntropia identity, limine fix, wizard completed"
```

**Revert to it** before a test cycle:

```bash
virsh -c qemu:///system snapshot-revert syntropia-iso clean-installed
virsh -c qemu:///system start syntropia-iso
```

**Pitfalls:**
- The snapshot only exists if the VM was **shut off** at creation (a running
  VM's snapshot captures live RAM too and is slower to revert). Shut the VM
  down first: `virsh -c qemu:///system shutdown syntropia-iso`.
- This install's journald is **volatile** (`Storage=auto` with no
  `/var/log/journal`), so boot history is lost on shutdown — don't expect to
  grep the journal after a reboot.
- The VM disk is a qcow2 at `/var/lib/libvirt/images/syntropia-iso.qcow2`
  (root-owned). To read it directly (e.g. verify installed files without
  booting), `qemu-img convert -O raw` to a scratch dir with room (NOT `/tmp`,
  which is a small tmpfs), then `kpartx -av` and mount the `@` subvolume
  read-only: the system root is `/mnt/.../@`, not the mount root.

## Disk usage

- Work directory (`iso/work/`): ~10 GB (gitignored)
- Package cache: shared with system at `/var/cache/pacman/pkg/`
- Output ISOs: ~3 GB each (gitignored via `*.iso` pattern)
