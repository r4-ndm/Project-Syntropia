# 📋 Syntropia — Mission & Status

> **Every agent: start here.** Then `AGENTS.md` → every file in `agent-rules/`;
> `.agents/skills/iso-builder/SKILL.md` before any ISO work.
>
> This file is the single source of truth for what is **true** and what is **next**.
> Past session evidence (the full trail of what broke and why) lives in
> `docs/HISTORY.md` — read it only when you need the "why"; it is history, not
> instructions. Update this file in the same commit as any status change.

## 🎯 Mission

**Syntropia is a laptop-friendly everyday Linux for the Final Boss and music
producers** (Phase 1 scope). A **CachyOS re-skin** — the same relationship Linux
Mint has to Ubuntu: CachyOS base and repos, Syntropia branding, apps wizard, and
an audio-production layer on top. Identity follows the freedesktop derivative
pattern (`ID=cachyos`, `VARIANT_ID=syntropia`, `PRETTY_NAME="CachyOS Syntropia"`).
The long-term goal is a full fork, but **not yet**.

- Ship target today: the install ISO (`iso/`), consumed by the Final Boss's own
  machines. Pre-1.0: no users depend on installer stability.
- Non-negotiables: pre-Turing NVIDIA GPUs (GTX 1070 class) must boot; one
  password at install; no wallet/keyring prompt at first login.
- The **host box is NOT a test target** — it has the live transform applied.
  `syntropia transform --check` only, never `--yes` (`transform-safety.md`).

## 🏗️ Architecture (settled, approved by Final Boss)

1. **TUI installer** (`syntropia-install` on tty1, <3s boot): keyboard layout →
   network → one password (LUKS2 + Btrfs subvolumes) → progress dashboard
   (`syntropia-install-dashboard` + `-runner`). Source of truth is
   `iso/installer/`, never heredocs in `build.sh`.
2. **Desktop: stock CachyOS Hyprland + Noctalia** (`cachyos-hypr-noctalia`,
   UWSM, upstream Lua config). **No hand-rolled dotfiles** — only a Syntropia
   drop-in overlay in `iso/profiles/hyprland/`.
3. **First-boot wizard `app-wiz4rd`** — a standalone repo shipped as a
   sha-pinned tarball in `iso/vendor/`; the catalog is
   `phase1/wizard/apps.list`.
4. **Sessions: Hyprland (UWSM) only.** Plasma is removed from the live image
   and the installed system; `sddm` is the login manager.
5. **Bootloader: Limine everywhere** (UEFI + BIOS `ef02`, ESP at `/boot`),
   entry name `/+CachyOS Syntropia`.
6. **Identity single source:** `OS_RELEASE_CONTENT` in
   `phase1/cli/transform/syntropia_transform/transform.py`. `build.sh`
   AST-extracts it — never duplicate it.

## 📍 Status — 2026-11-21

**Phase 1 is done.** It works end to end on real hardware (fresh installs
verified 2026-10-29, on the 2026-11-19 image, and again on the 2026-11-21
rebuild): TUI install → Limine → Hyprland + Noctalia → wizard → audio → wallet
unlocks with the login password. The last open item — proving the installer
cleanup patch on hardware — passed on the 2026-11-21 reinstall.

- **Tests: 445 passing** (`phase1/tests` + `iso/tests`).
- **Latest ISO**: `iso/out/syntropia-2026.08.12-x86_64.iso` (2026-11-21 18:31,
  sha256 `55e1cf2944b7…cdd352`) — rebuilt 2026-11-21 after the installer cleanup
  patch, boot-config checked (9 files), and content-verified against the tree:
  the three `usr/local/bin/syntropia-install*` binaries, all seven
  `installer/lib/*.sh`, and `usr/local/bin/syntropia-ssh-setup` are byte-identical
  to `iso/installer/`. The runner in the image strips the installer-only packages
  and removes `/etc/modules-load.d/zfs.conf`. **Flashed and installed on the
  laptop 2026-11-21.** The previous 2026-11-19 image is kept as a known-good
  fallback at `syntropia-2026.08.12-x86_64.iso.verified`.
- **sshd hardening fixed in the tree** (`iso/installer/lib/ssh-setup.sh` writes
  `00-syntropia-ssh.conf`, neutralises `10-archiso.conf`, re-derives the
  effective config with `sshd -T` and reverts+fails if something outbids it;
  two regression tests). Previously a silent no-op: sshd read the archiso
  drop-in first and kept password + root logins enabled. **Hardware-verified
  2026-11-21** on the installed laptop: `/etc/ssh/sshd_config.d/` holds both
  `00-syntropia-ssh.conf` and archiso's `10-archiso.conf`, and the server offers
  `publickey` only — password logins are refused outright.
- **`syntropia-ssh-setup` is now genuinely one command** (2026-11-21).
  `--key "<pubkey>"` / `--key-file <path>` / `--github <user>` authorize a key,
  then harden, *then* start sshd — so sshd is never reachable while password
  auth is still permitted. Keys are validated (a pasted private key or
  fragment is refused and sshd is not started), deduplicated by key body
  ignoring the comment, and written 600 with `.ssh` 700. Hardening is no longer
  gated on a local `id_ed25519` — that key is for *outbound* connections and
  used to cause a silent skip that could leave sshd unhardened with no output
  saying so. The legacy no-flag path still works but now states plainly that
  password login is open until you re-run. 8 new tests, one of which pins the
  harden-before-start ordering.
- **CachyOS base refresh fixed** — `build.sh` resets the vendored
  `iso/work/CachyOS-Live-ISO` clone before pulling, so upstream changes to
  `packages_desktop.x86_64` no longer abort the update silently.
- **Committed 2026-11-21**: `d97ec65` sshd drop-in ordering + effective-config
  check, `2a97e73` CachyOS-Live-ISO reset before pulling, `50e39d5`
  docs/cleanup, `893e5a0` installer target cleanup, `ad32eea` AUR rehash,
  `9e4e15a` status, `b5a2624` session write-up, `647eef2` status, `4b53592`
  ssh-setup `--key`, `d8aec3c` Phase 1 closure. **Pushed through `647eef2`** —
  `4b53592` and `d8aec3c` are committed locally but NOT yet pushed.
- **AUR source tarball published 2026-11-21.** The `v0.1.0` release asset was
  replaced with the regenerated `release/syntropia-0.1.0.tar`; downloaded back
  from GitHub it hashes `b0b48cb4b8c0…adfb1a` (14,213,120 bytes), matching the
  `sha256sums` in all three `pkgrel=2` PKGBUILDs. AUR builds validate again.
- **The stick now holds the rebuilt image** (flashed 2026-11-21). Read back from
  `/dev/sdd`, the first 3,538,399,232 bytes hash `55e1cf2944b7…cdd352` —
  identical to the ISO, so the stale-ISO gap is closed and the media carries the
  installer cleanup patch. The stick is an unbranded USB 3 drive
  (`346d:5678`, serial `FC00460E56632818`) that reports 29 GiB; its identifiers
  are placeholder strings (`VendorC`/`ProductCode`), so the claimed capacity is
  unverified. Irrelevant at a 3.5 GB image, but don't trust it for large writes.

- **Installer cleanup patch hardware-verified 2026-11-21** on the reinstall from
  the rebuilt stick. Both findings from the earlier install are fixed:
  - `pacman -Q cachyos-calamares-staging mkinitcpio-archiso` → both "was not
    found". The target no longer inherits the build chroot's installer-only
    packages (previously present, `Required By: None`, marked explicitly
    installed at ISO build time).
  - `journalctl -b -p 3 | grep -i spl` → empty. The runner deletes
    `/etc/modules-load.d/zfs.conf` when no ZFS modules ship, so
    `systemd-modules-load` no longer fails on `extramodules/spl.ko.zst`.
  - Still open, cosmetic: `/usr/bin/noctalia` was seen replaced on disk
    mid-session on the earlier install (running process mapped a deleted
    inode); resolves on next login.

## ⏭️ Next, in order

**Phase 1 has no open items.** Rebuild, flash, reinstall and both cleanup checks
are all done and verified on hardware.

1. **Open Phase 2 deliberately** — scope it with the Final Boss before writing
   code. `phase2/` exists but Phase 2 has never been scoped; do not drift into it
   by accident.
2. **The ISO and the installed laptop carry the OLD ssh helper.** The
   `--key` work landed after the 2026-11-21 build, so `iso/out/`, the stick and
   the laptop all have the two-pass version. Nothing is broken by this — but to
   use `--key` on the laptop either rebuild the ISO or copy
   `iso/installer/lib/ssh-setup.sh` to `/usr/local/bin/syntropia-ssh-setup`
   there. `build.sh`'s `verify_installer_libs` will refuse a stale image anyway.
3. **The wizard still invokes the helper with no arguments**, so picking "SSH
   Setup" in the first-boot wizard gets the legacy two-pass flow and its
   password-auth window, not the one-command path. Making the wizard pick good
   needs an interactive "paste your public key" prompt for the TTY/no-args case.
   Decide whether to add it.
4. **Optional, not blocking:** the stick's real capacity is unverified
   (`f3probe` would settle it).

## 🧰 Commands

```bash
# Tests (the whole suite; ~10s)
python -m pytest -q phase1/tests iso/tests

# Installer UI without touching a disk (safe on any box)
./iso/installer/syntropia-install --dry-run

# Full ISO build (~15 min first run, ~5 min cached) — sudo required
sudo env SOURCE_DATE_EPOCH=1786489200 ./iso/build.sh

# Inspect a built ISO's boot configs (no sudo needed)
iso/lib/iso-boot-config.py check <extracted-boot-dir>

# Branding check only — never apply on the host box
syntropia transform --check
```

## 🔻 Traps (learned the hard way)

- **Flash to a real device**: `dd of=/dev/sdd …`. `dd` will happily create
  `/dev/sdX` as a 3 GB *file* and flash nothing. Verify by hashing the stick's
  `arch/x86_64/airootfs.sfs` against the ISO's.
- **Wipe VM disks first** (`rm -f ~/vm-test/*.qcow2 ~/vm-test/OVMF_VARS.fd`), or
  you boot the old installed system and chase phantom installer bugs.
- **Test the USB boot path**, not just CD-ROM; `grub-script-check` is not a
  validator (`}}` closers pass it), `iso-boot-config.py check` is.
- **A stale ISO is not an installer bug.** If a fix seems missing on hardware,
  compare the ISO's embedded file hash first.
- `loginctl terminate-session` on the graphical session can leave sddm running
  with no greeter; recover with `systemctl reboot`, and log out cleanly with
  `uwsm stop`.
- **`sshd -T` needs root.** As a normal user it exits with `sshd: no hostkeys
  available -- exiting`, which looks like a config error and isn't. Prove the
  effective config from outside instead: `ssh -vv -o
  PreferredAuthentications=none r5@<ip>` → `Authentications that can continue:`
  must list `publickey` only.
- The wizard's fzf version probe must read `</dev/null`, or the pty test stub
  blocks the whole suite.
