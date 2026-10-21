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
2. Applies three minimal patches:
   - Symlinks `packages.x86_64` → `packages_desktop.x86_64` (mkarchiso naming convention)
   - Appends `limine` to that list: Limine is the installed bootloader, and the TUI installer copies the live rootfs onto the target, so its payloads have to exist in the live image
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
4. Optimize ISO bootloader (GRUB timeout reduced to 2s, Syslinux to 3s, Syntropia menu title)
5. Configure the direct Omarchy-style TUI installer on tty1 (centered terminal UI, network step, password panel, LUKS2 encryption, desktop experience selection, progress dashboard; graphical display manager disabled). The scripts come from `iso/installer/` — see below.
6. Repack squashfs with `zstd` (`-comp zstd -Xcompression-level 19 -b 1M`) for ~9x faster kernel page decompression during live boot
7. Rebuild the ISO with `xorriso` (BIOS + UEFI hybrid)

Output: `iso/out/syntropia-YYYY.MM.DD-x86_64.iso`

Phase 2 also ships the rest of the Syntropia install experience (not just slides):
the default LUKS2 full-disk encryption with Btrfs subvolumes,
**Limine** as the installed bootloader (UEFI + BIOS, see below),
the interactive DE profile selector (KDE Plasma vs Hyprland + Omarchy hotkey/helper suite),
the apps wizard + TUI (`/etc/syntropia/`, from the vendored app-wiz4rd release tarball in `iso/vendor/`; shipped with an app-menu launcher, and picks made while offline are queued until a connection exists),
the Hyprland profile configs & helper scripts (`/etc/syntropia/profiles/hyprland/`: a traditional-desktop Hyprland — bottom Noctalia bar with the taskbar widget, floating windows resizable from the border, and KDE-style titlebar buttons from the `hyprbars` plugin, which is compiled into the ISO because it is AUR-only), paru in pacstrap `basePackages`,
the fastfetch ASCII-art branding (`/usr/share/syntropia/`), the **Syntropia identity**
(`os-release`/`lsb-release` generated from `transform.py`, copied into the installed
`/etc/` at install time), the `syntropia-${cpu}` hostname default, and the limine
bootloader identity sync. See `.agents/skills/iso-builder/SKILL.md` for the full
step list and pitfalls.

## The installer UI (`iso/installer/`)

The tty1 installer is **source code in this repo**, not heredocs pasted into
`build.sh`:

| Path | Role |
|------|------|
| `syntropia-install` | setup TUI: disk, identity, keymap, **network**, **passwords**, encryption, desktop, summary |
| `syntropia-install-runner` | the destructive backend: partition, format, copy, chroot setup, Limine install |
| `syntropia-install-dashboard` | progress dashboard that supervises the runner and reboots |
| `lib/common.sh` | palette, geometry, centring, logo (shared by both UIs) |
| `lib/config.sh` | the TUI↔runner config contract; writes `config.json` **0600** |
| `lib/password.sh` | masked password entry, strength estimate, confirmation, root-locked default |
| `lib/network.sh` | connectivity probe, `nmcli` Wi-Fi setup, `nmtui-connect` fallback |
| `lib/keyring.sh` | KWallet PAM auto-unlock, autologin/loadkey rule, Secret Service bridge |
| `lib/bootloader.sh` | `limine.conf` generation, UEFI copy + NVRAM entry, `limine bios-install` |

`build.sh` installs the three scripts to `/usr/local/bin/` and the libs to
`/usr/local/lib/syntropia-installer/` (both resolve their libs from either
location).

**Preview without installing anything:**

```bash
./iso/installer/syntropia-install --dry-run
```

### Bootloader: Limine

Limine is the installed bootloader on both firmware types and on **both install
paths** (confirmed in `NEXT_SESSION.md`):

- **TUI installer** — `iso/installer/lib/bootloader.sh` writes `limine.conf`,
  copies the EFI executable, registers the NVRAM entry and runs
  `limine bios-install`. It writes no systemd-boot entries and runs no
  `grub-install`.
- **Calamares** — `build.sh` pins `bootloader.conf` to
  `efiBootLoader: "limine"` (`efiBootLoaderVar` emptied because the bootloader
  picker is removed from the sequence), `efiBootloaderId: "syntropia"`,
  `installEFIFallback: true`, and `limineSplashLogo` → the Syntropia wallpaper.
  CachyOS' `partition.conf` then applies its `bootloaderOverrides: name: limine`
  entry (ESP at `/boot`), and CachyOS' limine module does the install. A
  `syntropia_limine` shellprocess step runs straight after it and fails the
  install when the disk would not boot (`iso/hook-scripts/hook-limine.sh`).

Both paths end up with the same ESP layout and the same OS entry name, so
`limine-snapper-sync` (when installed) and the identity sync agree.

The TUI layout is:

| Partition | Size | Type | Purpose |
|-----------|------|------|---------|
| 1 | 1 MiB | `ef02` BIOS boot | Limine's BIOS stage 2 |
| 2 | 512 MiB | `ef00` ESP | mounted at `/boot`: `limine.conf`, `limine-bios.sys`, kernels, initramfs, `EFI/BOOT/BOOTX64.EFI`, `EFI/limine/BOOTX64.EFI` |
| 3 | rest | `8309` | Btrfs `@,@home,@log,@pkg`, LUKS2 when encryption is on |

The ESP is mounted at `/boot`, which puts `limine.conf` at the volume root —
Limine's own config search finds it for both EFI paths. The OS entry is named
`/+CachyOS Syntropia` because that is os-release `PRETTY_NAME`; the branding
hook's identity sync and `limine-snapper-sync` (`TARGET_OS_NAME`) both match on
that exact string. Regenerating the config is safe:

```bash
source lib/bootloader.sh
limine_conf_write /boot "$(cat /proc/cmdline)" 0
```

It asks the same questions, prints the plan, writes no config and touches no
disk — which is also how `phase1/tests/test_installer_tui.py` drives it.

Passwords: **one** password, asked once with a confirmation field and a
strength estimate. **Root is locked** (`passwd -l root`), so `sudo`/polkit use
the account password and there is no second secret to invent — the
archinstall/Omarchy model. `--root-password` opts back into the old "same as
the user"/"different" menu (recorded as `root_password_mode` in `config.json`).
The account password doubles as the LUKS passphrase.

Keyring: the image ships KWallet, not gnome-keyring. `lib/keyring.sh` wires
`pam_kwallet5.so` into the installed display manager (`plasmalogin`, `sddm`,
plus `login`) so the wallet is created and unlocked with the login password —
ksecretd's PAM path creates a missing `kdewallet` silently, which is what
prevents the "create a new keyring password" dialog at first login. Autologin
types no password, so it is only enabled when `pam_systemd_loadkey` can recover
the LUKS passphrase (encrypted installs, with `KeyringMode=inherit`); an
unencrypted install gets a normal login screen so the password reaches PAM.
`~/.config/kwalletrc` enables `[org.freedesktop.secrets]` so libsecret apps
(Chromium, Electron) reuse the same wallet. Requires `kwallet-pam` + `socat` in
the image — phase 1 adds both to the package list and warns if they are missing.
The installer/wizard *code* ships with a phase-2 remaster, but those packages
cannot be installed by one: the first build after this change must be a full
`sudo iso/build.sh` (phase 1 re-pacstraps because the patched package list
changed).

Network: the installer probes for a connection and, if there is none, offers
Wi-Fi setup (via `nmcli`), a re-check, `nmtui-connect` for hidden/enterprise
networks, or "continue offline". Offline installs are supported; apps picked in
the first-boot wizard are queued and installed once the machine is online.

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

### Phase 2 "Stock ISO not found" — where the stock ISO is

Phase 2 looks for `syntropia-<today>-x86_64-stock.iso` and otherwise falls back to
the newest `syntropia-*-stock.iso` in `iso/out/`, so a stock ISO from an earlier day
is fine. If there is none, phase 1 has not produced one (run `sudo iso/build.sh
--phase1`); the error also names any leftover `cachyos-*.iso` from a phase 1 that
died before renaming its output.

That rename is by mtime, not by date: mkarchiso names its output
`cachyos-<iso_version>-x86_64.iso`, where `iso_version` comes from
`iso/work/mkarchiso-work/build_date` — pinned by the first build in that work dir
and never refreshed, so it can lag the real date by months. `iso/lib/find-built-iso.sh`
picks the newest `cachyos-*-x86_64.iso` written at or after the run started.

Phase 1 also discards the cached rootfs when the patched profile changed (stamp in
`iso/work/mkarchiso-work/syntropia-patches.sha256`), because mkarchiso otherwise
re-assembles an ISO around a stale `airootfs.sfs` — that is how an Oct-21 build
shipped an image without the `limine` package.

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

**Fix**: the installer's `lib/bootloader.sh` generates the entry already named
`/+CachyOS Syntropia`, and `iso/hook-scripts/hook-branding-users.sh` normalises
every name an installer can produce — `/+CachyOS` (CachyOS' installer),
`/+Syntropia` or `/Syntropia OS` (Calamares' limine module, which takes the name
from `branding.desc`) — to that canonical string, then pins
`TARGET_OS_NAME="CachyOS Syntropia"` in `/etc/default/limine` (creating the file
if the limine package shipped none). The rename is anchored to the whole line, so
re-running the hook is harmless. Keep both names in sync whenever the os-release
name changes.

### Installed disk has no boot entry (firmware falls through to the next device)

**Cause**: the ESP does not hold Limine, or `efibootmgr` could not create the NVRAM
entry and the firmware ignores the `\EFI\BOOT\BOOTX64.EFI` fallback.

**Fix**: mount the ESP and check for `limine.conf`, `limine-bios.sys`,
`EFI/BOOT/BOOTX64.EFI` and `EFI/limine/BOOTX64.EFI`. Register it by hand with
`efibootmgr --create --disk /dev/sdX --part 2 --label "Syntropia OS" --loader '\EFI\limine\BOOTX64.EFI'`.
A Calamares install uses `\EFI\syntropia\BOOTX64.EFI` instead (its
`efiBootloaderId`), and registers that path — check both before re-registering by
hand. On a BIOS machine, `limine bios-install /dev/sdX 1` must have been run against the
`ef02` partition. The runner aborts (instead of finishing) when the limine package
is missing from the image, so a completed install always had the payloads.

### First login asks to create a new wallet/keyring password

**Cause**: the installed system has KWallet but no PAM link to it, so the first
app that stores a secret asks the user to invent a wallet password. Autologin
makes it unavoidable: no password ever passes through PAM.

**Fix**: phase 1 ships `kwallet-pam` + `socat` in the live image and
`syntropia-install-runner` calls `lib/keyring.sh`. On an installed system:

```bash
grep -n pam_kwallet /etc/pam.d/plasmalogin /etc/pam.d/sddm
autologin=... ; grep -n '^\[Autologin\]' /etc/plasmalogin.conf   # only when encrypted
qdbus org.kde.kwalletd6 /modules/kwalletd6 isOpen kdewallet         # after login
ls ~/.local/share/kwalletd/kdewallet.kwl
```

If `pam_kwallet5.so` is missing, the image predates patch 1c — rebuild phase 1.
Root being locked is intentional (see the installer section); do not "fix" sudo
by setting a root password unless the user asked for one.

### Apps picked in the first-boot wizard but nothing installed

Check `~/.local/state/app-wiz4rd/install.log` first: every run and every paru
invocation is recorded there, so an empty file means the wizard never reached
the install step. The picker installs on **enter** from any row (the DONE row is
not an arming step), and `paru` output is live in that terminal. Offline, the
picker offers `nmtui-connect` before the app list; picks then wait in
`~/.config/syntropia/apps-wizard.pending` and `--once` retries on each login.
The wizard is shipped from `iso/vendor/app-wiz4rd-*.tar` (sha-pinned in
`build.sh`), so a wizard fix only reaches the ISO after regenerating that
tarball and bumping `APP_WIZ4RD_SHA256`.

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
- `SOURCE_DATE_EPOCH` sets the date in Syntropia's output names (it does not control mkarchiso's own `iso_version`, which comes from the work dir's `build_date`; phase 1 renames by mtime instead of predicting either)
- Exit codes: 0 on success, 1 on error (suitable for CI pipelines)
