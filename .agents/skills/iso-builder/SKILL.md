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
  2. Appends `limine` to that package list — Limine is the installed bootloader, and the TUI installer *rsyncs the live rootfs* onto the target, so `/usr/bin/limine` and `/usr/share/limine/{BOOTX64.EFI,limine-bios.sys}` must already be in the live image (an offline install cannot pacman them afterwards)
  3. Adds `NoExtract` for slide files in `pacman.conf` [options] section (safety net)
  4. **Stale-work-dir guard**: clears the mkarchiso `build._build_buildmode_*` / `iso._build_iso_image` markers when the expected stock ISO is missing, so a previously-renamed stock ISO forces re-assembly instead of silently exiting
- Runs `mkarchiso` → `iso/out/syntropia-*-stock.iso`

### Phase 2: Remaster (injection)

1. Extract the stock ISO (`bsdtar`), unsquash the rootfs
   - **Stale-stock guard**: before touching anything else, `iso/lib/verify-live-image.sh` inspects the unsquashed rootfs for the current live package set — the `limine` package in pacman's local db **and** `usr/share/limine/{BOOTX64.EFI,limine-bios.sys}` — and **fails in the first minute** when the stock ISO predates the package patch, printing the reason and pointing at a full build. Phase 2 can only swap files, so a stale image remasters cleanly and then fails every install at the bootloader step (2026-10-21 VM test). Pinned by `phase1/tests/test_phase2_guard.py`.
2. **Slides**: copy `slide{1-6}.jxl` into `/usr/share/calamares/branding/cachyos/`
3. **pacman.conf NoUpgrade+NoExtract** (must stay inside `[options]`): protects the slides AND the Calamares configs we patch — `settings_online.conf`, `settings_offline.conf`, `etc/calamares/modules/pacstrap.conf`, `etc/calamares/modules/users.conf` — from the live-boot `cachyos-calamares-next` update
4. **Direct Omarchy-style TUI installer on tty1**: Disables graphical display-manager auto-start for instant boot (<3s); sets the default systemd target to `multi-user.target`. Configures autologin on `tty1` to launch `syntropia-install` centred on screen with robust dynamic terminal geometry (`stty size < /dev/tty`, `tput`, `shutil.get_terminal_size`), the Syntropia dark console palette, ASCII banner/logo, interactive console keyboard layout selection (UK vs US with immediate `loadkeys` + `/etc/vconsole.conf` persistence), NumLock via `setleds`, a **network step**, and a **password panel**, then a curses-style progress dashboard (`syntropia-install-dashboard` + `syntropia-install-runner`). Fallback GUI launcher `start-plasma` remains available.
   - **Source of truth: `iso/installer/`**, not heredocs in `build.sh`. `build.sh` installs `syntropia-install`, `-runner` and `-dashboard` to `/usr/local/bin/`, plus `iso/installer/lib/*.sh` (common, config, password, network) to `/usr/local/lib/syntropia-installer/`. Keep it that way — as files the UI can be syntax-checked, dry-run (`syntropia-install --dry-run`) and tested (`phase1/tests/test_installer_tui.py`).
   - **Passwords are collected twice**: the account password (masked entry, strength estimate with "Meets/Missing" feedback, confirmation loop, ANSI-escape rejection for keypad End and friends) and the root password, which defaults to "same as the user" with an explicit "different root password" option. Both land in `/run/syntropia-install/config.json` (`password`, `root_password`) — created **0600** by `lib/config.sh` — and the runner applies both with `chpasswd` over stdin. The account password is also the LUKS passphrase; the summary says so.
   - **Network step**: probes a default route plus ICMP/DNS (`lib/network.sh`). Offline it offers `nmcli` Wi-Fi setup, a re-check, or "continue without internet"; the answer is stored as `online` in the config so the runner skips its online-only Hyprland `pacman -Sy` fallback instead of stalling.
   - **Bootloader: Limine** (`lib/bootloader.sh`, decision recorded in `NEXT_SESSION.md`) — the runner no longer writes systemd-boot entries or runs `grub-install`. Partitions are `p1` 1 MiB **BIOS boot** (GPT type `ef02`, holds Limine's BIOS stage 2), `p2` 512 MiB **ESP** (mounted at `/boot`), `p3` root (Btrfs/LUKS). `limine_conf_write` generates `/boot/limine.conf` (volume root, so Limine's own search order finds it), `limine_install_efi` copies `BOOTX64.EFI` to **both** `\EFI\BOOT\` (firmware fallback) and `\EFI\limine\` (the NVRAM entry, recreated with `efibootmgr`), and `limine_install_bios` drops `limine-bios.sys` on the ESP and runs `limine bios-install <disk> <bios-partnum>`. The OS entry is `/+CachyOS Syntropia` — exactly os-release `PRETTY_NAME`, i.e. what `TARGET_OS_NAME` in the branding hook and limine-snapper-sync match — and the hook normalises every installer spelling (`/+CachyOS`, `/+Syntropia`, `/Syntropia OS`) to it, so a second install run can't produce `... Syntropia Syntropia`. If the limine package is missing from the image the runner **aborts** rather than shipping an unbootable disk. Pinned by `phase1/tests/test_installer_bootloader.py`.
5. **Apps wizard + TUI + Hyprland Noctalia overlay** → `/etc/syntropia/`: `app-wiz4rd` (TUI-only driver), `apps.list`, `dialog/` (source + a freshly built static TUI binary), and the Syntropia overlay on stock `cachyos-hypr-noctalia` (providing Noctalia shell integration, Syntropia branding/wallpaper, DAW/VST floating window rules, and `syntropia-cheatsheet` hotkey suite). Autostart entry ships as a template in `/etc/syntropia/syntropia-apps.desktop` (NOT the live autostart dir — see step 6), with the app-menu launcher shipped separately (below).
   - **Offline picks queue instead of vanishing**: every selection is written to `~/.config/syntropia/apps-wizard.pending` *before* `paru` runs, successful installs clear their entries, and `--once` keeps firing while the queue is non-empty (it honours `apps-wizard.done` only when nothing is pending). `app-wiz4rd --resume` installs the queue without the picker, and a normal run retries it first. Web-app picks are just local launchers, so they work offline. Pinned by `phase1/tests/test_app_wiz4rd_pending.py` against the vendored tarball.
   - The tarball's `app-wiz4rd.desktop` is also shipped, with `Exec` repointed to `/etc/syntropia/app-wiz4rd`, as `/usr/share/applications/syntropia-apps.desktop` — the wizard must stay reachable from the app menu after the one-shot autostart has fired.
   - **Hyprland Lua & Noctalia**: Hyprland configuration is managed upstream via Lua (`hl.*` API) and UWSM by CachyOS's `cachyos-hypr-noctalia` package; the unified Rust-based `noctalia` shell replaces separate Waybar/SwayNC/Rofi/wlogout packages.
   - **hyprbars** (`install_hyprbars_plugin()`): titlebar window buttons are the one Hyprland piece that is AUR-only, so it is compiled in the freshly-pacstrapped rootfs (Hyprland ships its headers + `hyprland.pc`) and installed to `/usr/lib/hyprland/hyprbars.so`. The installed system gets the same module copied in by `syntropia-install-runner`. Best-effort: a failed build only warns, and `config/hyprbars.lua` skips loading when the `.so` is absent.
6. **Calamares install wiring** (patched into `settings_online/offline.conf`):
   - `syntropia_wizard` shellprocess — copies the wizard + autostart entry into the installed root (autostart comes from `/etc/syntropia/syntropia-apps.desktop`, so the live session stays vanilla)
   - `paru` **and `limine`** added to pacstrap `basePackages` — every install ships both (NoUpgrade-protected). Limine has to be in the target: CachyOS' Calamares bootloader module runs `limine` there, and the old systemd-boot override existed only because it was missing (see the 82% freeze entry).
   - `syntropia_branding` shellprocess — copies branding + identity into the installed root
   - `syntropia_limine` shellprocess — runs right after `bootloader` (before `umount`) and verifies the disk will boot: `limine.conf` with a menu entry, the Limine EFI executable on the ESP (repaired from the package when missing), `limine-bios.sys` + an `ef02` BIOS-boot partition and `limine bios-install` on BIOS. A disk that would not boot **fails the install** instead of only failing at the next reboot (`hook-limine.sh`; pinned by `phase1/tests/test_calamares_limine.py`).
   - **Both installers select Limine.** `bootloader.conf` is pinned to `efiBootLoader: "limine"` (with `efiBootLoaderVar` emptied because the picker instance is not in the sequence), `efiBootloaderId: "syntropia"`, `installEFIFallback: true`, and `limineSplashLogo` points at the Syntropia wallpaper — the same image `lib/bootloader.sh` puts on the ESP for the TUI path. CachyOS' `partition.conf` keys its `bootloaderOverrides: name: limine` entry off this value (ESP at `/boot`, like the runner).
7. **Terminal ASCII art** → `/usr/share/syntropia/` (logo.txt, `branding/fastfetch-color.json`) + `/etc/skel/.config/fastfetch/config.jsonc` (generated from the repo's `build_fastfetch_conf` — same single source as `syntropia transform`)
8. **Identity**: `os-release` + `lsb-release` generated from `transform.py`'s `OS_RELEASE_CONTENT` (AST-extracted at build time — the same constant `test_transform.py::test_os_release_identity_contract` pins). Shipped to `/usr/share/syntropia/branding/`. **Both** install paths copy them into the installed `/etc/`: Calamares via the `syntropia_branding` shellprocess, and `syntropia-install-runner` itself (after the branding hook, so nothing overwrites them) — a TUI install must not keep CachyOS' `PRETTY_NAME`. Pinned by `phase1/tests/test_installer_identity.py`.
9. **Hostname default**: `users.conf` hostname template `cachyos-${cpu}` → `syntropia-${cpu}` (user can still override in Calamares)
10. **ISO bootloader & Calamares unbranding & centering**: Patch GRUB timeout to 2s, Syslinux timeout to 3s, sync `archisosearchuuid`, and rebrand all boot titles to Syntropia only (removing CachyOS labels). Rebrand Calamares `branding.desc` to Syntropia OS with `windowPlacement: center`, purge generic multi-OS choosers (`packagechooser@desktop`, `packagechooser@bootloader`, `netinstall`), pin `bootloader.conf` to **Limine** for the installed system (the 82% freeze it used to work around was a missing `limine` package, now shipped in the image and in `basePackages`), configure offline `unpackfs` as default in `calamares-online.sh` to avoid network hangs, disable `cachyos-hello`, and prompt the user to remove the USB flash drive upon install completion.
11. Repack squashfs (`-comp zstd -Xcompression-level 19 -b 1M` for ~900 MB/s single-threaded kernel page decompression), update checksum, remove the unsquashed rootfs, rebuild hybrid ISO with `xorriso` (BIOS + UEFI via appended FAT EFI partition image `efiboot.img`, volume label `SYNTROPIA`, and synchronized `--modification-date`)

### The install-time branding hook

The `syntropia_branding` shellprocess runs in the **live env** (not the chroot) with `${ROOT}` = the target root. It:

- copies `/usr/share/syntropia/` → `${ROOT}/usr/share/syntropia/`
- copies `os-release` + `lsb-release` → `${ROOT}/etc/` (the installed system reports Syntropia; the live ISO stays CachyOS). The TUI path does not go through this hook for the identity — `syntropia-install-runner` copies the same two files itself, from the same `/usr/share/syntropia/branding/` source
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

### Phase 2 built an ISO that cannot install (stale stock image)
**Symptom**: the ISO boots and the TUI installer runs, then dies at "Installing Limine" ("Limine is missing from this image and there is no network to install it"); Calamares fails the same way in its `syntropia_limine` hook.
**Cause**: `--phase2` only remasters — it cannot install packages. A stock ISO built *before* patch 1b (which adds `limine` to `packages.x86_64`) remasters perfectly and then cannot install anything. Hit on 2026-10-21: an Oct-21 ISO whose live image still carried the Aug-12 package set, because phase 1 never re-ran.
**Fix**: guarded now — `iso/lib/verify-live-image.sh` refuses to remaster when the stock image's rootfs lacks the `limine` package or its payloads. Rebuild with `sudo iso/build.sh` (phase 1 must run to pick up the patched package list), then remaster.

### Phase 1 silently produces no ISO (stale work dir)
**Cause**: mkarchiso's completed-step markers exist but the stock ISO was renamed away, so mkarchiso concludes the build is done and exits without an ISO.
**Fix**: handled automatically by the stale-work-dir guard in `build.sh` (clears the ISO-assembly markers). If you hit it, delete `iso/work/mkarchiso-work/build._build_buildmode_*` and `iso._build_iso_image` and rebuild.

### limine-snapper: "Target OS name 'syntropia OS' not found in /boot/limine.conf"
**Cause**: the bootloader (limine.conf) is generated at install time with the CachyOS name, but os-release is renamed to Syntropia at the END of install. `limine-snapper-sync` reads the OS entry name from limine.conf and matches it against os-release PRETTY_NAME (or `TARGET_OS_NAME` in `/etc/default/limine`) — mismatch → warning/notification on every boot.
**Fix**: `hook-branding-users.sh` syncs both sides: it normalises the limine.conf OS entry — `/+CachyOS` (CachyOS installer), `/+Syntropia` or `/Syntropia OS` (Calamares' limine module takes the name from `branding.desc`) — to the canonical `/+CachyOS Syntropia`, and pins `TARGET_OS_NAME="CachyOS Syntropia"` in `/etc/default/limine` (creating the file when absent). The rename is anchored to the whole line, so re-running is a no-op. Keep these in sync whenever the os-release name changes.

### Calamares hook fails with "Missing variables"
**Cause**: the Calamares shellprocess module macro-expands every command string with KWordMacroExpander('$'), which treats BARE `$word` as a macro. Any shell variable written as `$foo` in a hook command aborts the whole job before it runs.
**Fix**: never put bare `$vars` in a hook command string. Put shell logic in a script file (e.g. `hook-branding-users.sh`) and call it from the hook.

### os-release identity drift
**Cause**: the ISO and `syntropia transform` each carry the identity; a second copy would drift.
**Fix**: single source of truth = `OS_RELEASE_CONTENT` in `phase1/cli/transform/syntropia_transform/transform.py`. `build.sh` AST-extracts it at build time, and `test_transform.py::test_os_release_identity_contract` pins `ID=cachyos` + `VARIANT_ID=syntropia` (the freedesktop derivative pattern — keeps CachyOS tools working). Change it in transform.py only.

### UEFI boot fails: "No bootable device" / "Invalid El Torito image"
**Cause**: Pointing `-e` in `xorriso` directly to a raw `.EFI` PE executable instead of a FAT filesystem EFI partition image (`efiboot.img`).
**Fix**: `iso/build.sh` extracts partition 2 (type `0xef`) from the stock ISO and appends it via `-append_partition 2 0xef "$efiboot_img"` and `-e '--interval:appended_partition_2:all::'`.

### Live installer freezes at 82% ("Configuring Limine bootloader & kernel")
**Cause**: `mkinitcpio -P` fails because stray `linux.preset` from archiso expects missing kernel paths, `mkinitcpio.conf` used incompatible `encrypt` hook with systemd initramfs (needs `sd-encrypt`), and **Limine's payloads were not in the image**, so the module had nothing to install.
**Fix**: `iso/build.sh` removes stray archiso presets, copies all kernels to `/boot`, configures `sd-encrypt`, runs specific presets, ships the `limine` package in the live rootfs *and* in pacstrap `basePackages`. The TUI runner installs Limine from `lib/bootloader.sh`; the Calamares path uses CachyOS' limine module and then verifies it with `hook-limine.sh`. Do not "fix" a freeze here by switching the loader back to systemd-boot — that was the old workaround and it left Calamares installs on a different bootloader than the TUI installer.

### Kernel boots but panics: "Device ... not found after 30 seconds"
**Cause**: The archiso initramfs hook searches for `/dev/disk/by-uuid/<archisosearchuuid>`, but remastering changed the ISO filesystem UUID (which ISO9660 derives from modification date).
**Fix**: `iso/build.sh` preserves the stock ISO's UUID and passes `--modification-date` to `xorriso`, while syncing `archisosearchuuid` in `grub.cfg` and `archiso_sys*.cfg`.

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

### Install finishes but the machine boots nothing (firmware menu, no "Syntropia OS")
**Cause**: Limine is not on the disk: either the image was built without the `limine` package (the runner now aborts with "Rebuild the ISO") or the disk has no BIOS boot partition, so `limine bios-install` had nowhere to put stage 2.
**Fix**: Check `/boot` on the target (ESP): it must hold `limine.conf`, `limine-bios.sys`, `EFI/BOOT/BOOTX64.EFI`, `EFI/limine/BOOTX64.EFI` plus the kernel and initramfs. `efibootmgr -v` must list "Syntropia OS" → `\EFI\limine\BOOTX64.EFI`. On a BIOS machine, `limine bios-install <disk> 1` must have run against the `ef02` partition; re-running it from the installed system is safe.

### Hyprland windows have no titlebar / window buttons
**Cause**: `hyprbars` is AUR-only (`hyprland-plugin-hyprbars`), so it cannot be listed in `packages_desktop.x86_64` or the pacman package arrays; `install_hyprbars_plugin()` compiles it into the rootfs instead. If that build fails (network, a Hyprland release with no matching `hyprland-plugins` tag, a header API change) the build only warns and the ISO ships without `/usr/lib/hyprland/hyprbars.so`; `config/hyprbars.lua` then skips loading it, and windows float with no titlebar.
**Fix**: Look for the `[WARN] ... hyprbars` line in the phase-2 log and the compiler output (re-run with `bash -x`, or build by hand inside the rootfs: `make` in `hyprland-plugins/hyprbars`). The plugin must be rebuilt whenever Hyprland's version changes — its API hash is baked in at compile time.

## Typical workflow

1. Edit the source of truth (slides PNGs, `transform.py` OS_RELEASE_CONTENT, etc.) and commit. Wizard changes happen in the **app-wiz4rd repo** (`github.com/r4-ndm/app-wiz4rd`): edit there, regenerate its release tarball into `iso/vendor/`, and update `APP_WIZ4RD_SHA256` in `build.sh` (see the header comment there for the exact `git archive` command)
2. **Only when refreshing the base:** run phase 1 (`iso/build.sh --phase1`), then append the one-line entry to `iso/BASE-REFRESH.md` (date, upstream commit, known breakage) per the base-refresh policy above
3. Build: `sudo env SOURCE_DATE_EPOCH=$(date -d <stock-date> +%s) iso/build.sh --phase2`
4. Verify it baked in: `bsdtar -xf` the ISO, `unsquashfs` the sfs, and diff the shipped files against the vendored tarball (wizard script, os-release, apps.list, TUI binary). Also check that `iso/lib/verify-live-image.sh` passed — it aborts the remaster before any work when the stock image predates the live package set (a stale image boots and then fails every install)
5. Fresh-install test in the VM: reset the disk (fresh qcow2), attach the ISO as cdrom (boot order 1), boot, run Calamares, reboot from disk
6. Verify: the machine boots through Limine (menu title "Syntropia Bootloader", entry `/+CachyOS Syntropia`, LTS entry when the LTS kernel is present), wizard fires at first login, `fastfetch`/`lsb_release`/hostname report Syntropia, no limine-snapper notification

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
