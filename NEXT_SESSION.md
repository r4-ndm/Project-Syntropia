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

## 📍 Status — 2026-11-22

**Phase 1 is done, and the shipping image is fully hardware-verified.** It works
end to end on real hardware (fresh installs verified 2026-10-29, on the
2026-11-19 image, on the 2026-11-21 rebuild, and the 20:41 image installed on
the laptop 2026-11-22): TUI install → Limine → Hyprland + Noctalia → wizard →
audio → wallet unlocks with the login password. The last open item — proving the
SSH helper and its sshd hardening outside test stubs — passed 2026-11-22.

- **Tests: 452 passing** (`phase1/tests` + `iso/tests`).
- **ssh-setup hardened further 2026-11-22 (polish pass).** Decision: keep the
  existing design — the `ssh-copy-id` route stays, so the skip path still
  starts sshd with passwords open. No new input modes. Three changes:
  - **Real gap closed: the effective-config check verified only three of the
    four directives the drop-in writes.** `KbdInteractiveAuthentication` was
    set and never verified, so anything outbidding *just that one* left a
    password-reachable box reporting `effective config verified` and exiting 0.
    PAM can serve a password prompt through keyboard-interactive even with
    `PasswordAuthentication no`. Proven by reverting the fix: the new test
    fails against the old code with `returncode 0`. All four are checked now,
    and the failure diagnostic prints the offending directive.
  - `10-archiso.conf` neutralisation extended to `KbdInteractiveAuthentication`
    and legacy `ChallengeResponseAuthentication`, and its misleading "Allow
    root login using password authentication" comment is replaced with one
    describing what the file actually does.
  - The skip-path warning now names all four ways to close the password window
    (`--key`, `ssh-copy-id`, `--github`, or `systemctl disable --now sshd`)
    instead of only stating that it is open.
  - **Not in any ISO yet.** The installed laptop and the 20:41 image both carry
    the pre-polish helper. Needs a rebuild to ship; the hardware-verified
    behaviour above is unaffected, since all three changes are additive.
- **Latest ISO**: `iso/out/syntropia-2026.08.12-x86_64.iso` (2026-11-21 20:41,
  sha256 `d7a5a4978dc0…f56e16`) — rebuilt to pick up the `ssh-setup.sh` `--key`
  and piped-stdout fixes. Boot-config checked (9 files) and content-verified
  against the tree: the three `usr/local/bin/syntropia-install*` binaries, all
  seven `installer/lib/*.sh`, and `usr/local/bin/syntropia-ssh-setup` are
  byte-identical to `iso/installer/`; the shipped helper carries `--key`, the
  `public key>` prompt and the `-t 0`-only escalation gate. **Flashed to the
  stick 2026-11-21 20:5x** — read back from `/dev/sdd`, the first 3,538,399,232
  bytes hash `d7a5a4978dc0…f56e16`, identical to the ISO. **Installed on the
  laptop 2026-11-22 and verified** — see the laptop-install entry below. This is
  now the best image: hardware-proven, and the only one carrying the ssh-setup
  fixes.
- **Laptop install of the 20:41 image verified 2026-11-22.** Installed from the
  stick, booted, logged in. Identity correct (`ID=cachyos`,
  `VARIANT_ID=syntropia`, `PRETTY_NAME="CachyOS Syntropia"`, chassis `laptop`,
  kernel `7.3.5-2-cachyos`). Both cleanup checks pass on this freshly pulled
  CachyOS base: `pacman -Q cachyos-calamares-staging mkinitcpio-archiso` → both
  "was not found", `journalctl -b -p 3 | grep -i spl` → empty.
  `systemctl --failed` is empty. The cosmetic noctalia item from the earlier
  install did **not** recur: `/usr/bin/noctalia` is cleanly owned by
  `noctalia 5.6.0-1`. Reachable as `r5@192.168.1.22` (DHCP — re-check the lease
  before assuming that address).
- **The SSH helper is hardware-verified 2026-11-22 — its first run outside test
  stubs, via the wizard's "SSH Setup" pick.** Both fixes bite on real hardware:
  - *Escalation under the wizard's pipe.* The pick printed
    `root privileges are needed … Re-running via sudo` and prompted for the
    password. This is the `-t 0`-only gate working where the old `-t 0 && -t 1`
    gate made the whole pick a silent no-op.
  - *The `public key>` prompt appears* and openssh was already installed by the
    first pass.
  - *Skipping the prompt behaves as designed, and is not a regression.* First
    run, the prompt was skipped: the helper started sshd **without** hardening
    and said password login stays open until re-run — correct, since hardening
    with zero authorized keys would lock the box out. Measured from the desktop
    at that point: `publickey,password`. Worth knowing sshd is reachable with
    passwords open in that window.
  - *Hardening applied on the re-run with `--key`.* Measured from the desktop,
    `ssh -vv -o PreferredAuthentications=none r5@192.168.1.22` now answers
    `Authentications that can continue: publickey` — password auth refused
    outright. Key login from the desktop works.
  - *The drop-in ordering fix is confirmed from inside.* `sshd_config.d/` holds
    `00-syntropia-ssh.conf` (`PasswordAuthentication no`,
    `KbdInteractiveAuthentication no`, `PermitRootLogin prohibit-password`,
    `AllowUsers r5`) and a neutralised `10-archiso.conf` — whose stale comment
    still reads "Allow root login using password authentication" while its
    directives say `no`. That file is what used to outbid the hardening.
    `authorized_keys` is `600` inside a `700` `.ssh`; `sshd` is enabled+active.
  - *A lossy paste still worked.* The key arrived without its trailing comment
    (81 bytes, key body only) and authorized fine, as it should — dedup is by
    key body. The validator's refusal path was **not** exercised on hardware;
    it remains test-stub-only.
  - *Caveat on method.* The helper's own
    `sshd hardening: applied … (effective config verified)` line was never
    captured, so the evidence here is external measurement plus inspection of
    the installed drop-ins — not the helper's self-report. Both agree.
  - Verified as `r5` over SSH, not root: `sshd -T` needs root, so the effective
    config was proven from outside, per the trap below.
- **Known-good fallbacks in `iso/out/`** (both bootable, both hardware-proven):
  - `…iso.verified-2026-11-21` — sha256 `55e1cf2944b7…cdd352`, the image that
    installed cleanly and passed both cleanup checks on 2026-11-21. A good
    fallback, but it predates the ssh-setup fixes, so the 20:41 image above is
    the one to prefer now.
  - `…iso.verified` — the older 2026-11-19 image, which predates the installer
    cleanup patch.
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
- **The wizard's "SSH Setup" pick used to do nothing** — fixed 2026-11-21.
  app-wiz4rd runs helpers as `helper 2>&1 | tee -a "$INSTALL_LOG"`, so the
  helper's stdout is a pipe; escalation was gated on `[[ -t 0 && -t 1 ]]`, and
  the `-t 1` half meant it never re-exec'd under sudo. It ran unprivileged,
  printed `sudo pacman -S …` instructions, generated a passphrase-less keypair
  nobody asked for and exited 0 — openssh not installed, sshd not enabled.
  sudo prompts on `/dev/tty`, not stdout, so the gate is now `-t 0` only.
  **No app-wiz4rd release was needed**: the bug and the fix are both in
  `ssh-setup.sh`, which this repo owns.
- **The helper now prompts for a key** when given none and stdin is a TTY
  (Enter skips, `SYNTROPIA_SSH_NO_PROMPT=1` disables, junk re-prompts twice).
  So the wizard route and a bare terminal both get one-pass hardening without
  the wizard knowing anything about `--key`. The prompt writes to stderr, since
  stdout carries the accepted key back and callers pipe it.
- **CachyOS base refresh fixed** — `build.sh` resets the vendored
  `iso/work/CachyOS-Live-ISO` clone before pulling, so upstream changes to
  `packages_desktop.x86_64` no longer abort the update silently.
- **Committed 2026-11-21**: `d97ec65` sshd drop-in ordering + effective-config
  check, `2a97e73` CachyOS-Live-ISO reset before pulling, `50e39d5`
  docs/cleanup, `893e5a0` installer target cleanup, `ad32eea` AUR rehash,
  `9e4e15a` status, `b5a2624` session write-up, `647eef2` status, `4b53592`
  ssh-setup `--key`, `9580f7c` Phase 1 closure. **Everything described in this
  file is committed and pushed to `origin/main`; the tree is clean.** Verify
  rather than trust: `git status --short` and
  `git log --oneline origin/main..HEAD` should both be empty.
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

**Phase 1 has nothing left to prove.** Every item that stood here on
2026-11-21 — the laptop install, both cleanup checks, and the SSH helper on
hardware — passed on 2026-11-22. The tree is clean, pushed, and the 20:41 image
is hardware-verified. Do not invent more Phase 1 verification work.

**Decided 2026-11-22, planned for the next session: rebuild the ISO with the
ssh-setup polish, then install Syntropia on the HOST DESKTOP.** This is a
deliberate reversal of the "host box is not a test target" posture — the point
is to replace a box carrying the in-place transform with one built the way
users get it, which retires that special case. `transform-safety.md` still
applies until the reinstall actually happens: `--check` only, never `--yes`.

**Step 0 is urgent and must happen BEFORE any rebuild.** `build.sh` writes
`iso/out/syntropia-2026.08.12-x86_64.iso` — the exact filename of the 20:41
image that became hardware-verified on 2026-11-22. A rebuild overwrites it and
it then survives only on the USB stick. Preserve it first:

```bash
sudo cp --reflink=auto iso/out/syntropia-2026.08.12-x86_64.iso \
                       iso/out/syntropia-2026.08.12-x86_64.iso.verified-2026-11-22
```

Reflink on Btrfs is instant and costs no space. **As of these notes this has
NOT been done.**

1. **Back up what is not in git, to the laptop** (`r5@192.168.1.22`, key-only
   SSH, 458G free, `~/syntropia-backup/`). The desktop is about to be wiped and
   its own recovery images live on the disk being wiped — that is the main
   hazard, not the install itself.

   | Asset | Why |
   |---|---|
   | `~/.ssh/aur` + `.pub` | AUR publishing key for the three PKGBUILDs. Least replaceable thing on the box. |
   | `phase1/raw/` (36K, gitignored) | `eitri_protocol_plan.md`, `eitri_dependency_and_ui_plan.md` — exist nowhere else. |
   | `iso/out/*.verified-2026-11-21` | 3.5G fallback. Useless if it stays on the wiped disk. |
   | `~/.ssh/{id_ed25519,syntropia-verify,syntropia_vm,config}` | Regenerable, but authorized on other machines incl. the laptop. |
   | `.freebuff/` (4K) | Small, unidentified; sweep it up rather than decide. |

   Safe to lose: `iso/work` (14G build cache), the three gitignored
   `.agents/skills/` dirs (reinstallable via `skills-lock.json`; `iso-builder`
   is tracked), all `__pycache__`/`.venv`/egg-info. All code is pushed.
   Verify the backup by sha256, not by rsync's exit code.
2. **Remaster, do NOT full-rebuild — use `--phase2`.**

   ```bash
   sudo ./iso/build.sh --phase2
   ```

   `ssh-setup.sh` is injected during the *remaster* stage (`build.sh:735`,
   writing into the unsquashed `rootfs/`), not during the mkarchiso base
   build. So shipping `34cc69e` needs only phase 2: unsquash the existing
   stock ISO, swap the file, resquash. Minutes instead of ~15, no pacstrap.

   **This also preserves hardware verification.** A full `build.sh` pulls a
   fresh CachyOS base, so the image inherits none of what was proven on
   2026-11-22. `--phase2` does not touch the base, so everything verified on
   the 20:41 build still holds and only one file changes. Reach for the full
   build **only** when the CachyOS base or boot config must change.

   `verify_installer_libs` (`build.sh:1505`) still asserts the embedded
   helper matches the tree, so a stale remaster fails loudly — keep that.
3. **Flash and byte-verify the stick**, same read-back method as 2026-11-21:
   recreate the guarded flasher (see Traps), then hash exactly the ISO's byte
   count back off the device with `iflag=count_bytes`.
4. **Install on the host desktop.** Afterwards re-run the usual checks on it:
   both cleanup checks, `syntropia transform --check`, and the SSH helper.
5. **Then open Phase 2 deliberately** — scope it with the Final Boss **before
   writing code**. `phase2/` exists but Phase 2 has never been scoped; do not
   drift into it by accident.

   **Candidate raised 2026-11-22, to think about, not to start: a
   `syntropia-installer` package.** There is no such package today — the name
   exists only as the path `/usr/local/lib/syntropia-installer/`, which is an
   easy thing to misremember. The three AUR packages (`syntropia`,
   `syntropia-cli`, `syntropia-brews`) all cover the post-install Python
   surface; none ship the installer shell layer (`syntropia-install`,
   `-runner`, `-dashboard`, the seven `installer/lib/*.sh`, `ssh-setup.sh`).
   That layer lives only inside the ISO, which is why a one-line shell fix has
   no upgrade path for an already-installed machine.

   Packaging it would make the ISO a thin bootable shell that changes only
   when the base or boot config does. Two things to weigh first:
   - **`/usr/local` is the blocker.** An Arch package must not own anything
     under it — that tree belongs to the local admin. Packaging means
     relocating to `/usr/lib/syntropia-installer/` and `/usr/bin/`, touching
     every path in `build.sh`, the hook scripts and `iso/README.md`. The seam
     already exists though: `hook-branding-users.sh:67` resolves libs via
     `${SYNTROPIA_INSTALLER_LIB:-/usr/local/lib/syntropia-installer}`, so this
     is a relocation, not a redesign.
   - **Do not lose `verify_installer_libs`.** It guarantees the shipped helper
     matches the tree, and exists because of the "a stale ISO is not an
     installer bug" trap. A package version assertion must replace it.

   Note `--phase2` already solves the *iteration speed* complaint. The package
   solves a different problem: upgrading installed machines. Don't conflate
   them.
6. **Optional, not blocking:** the stick's real capacity is unverified
   (`f3probe` would settle it). Its identifiers are placeholder strings, so
   29 GiB is the controller's claim, not a fact.
7. **If an install misbehaves**, re-flash a known-good fallback from `iso/out/`
   rather than debugging blind — then compare.

### ⚠️ Two things an agent cannot do here unattended

Both were hit on 2026-11-22; do not burn time rediscovering them.

- **`sudo` requires a password on this box.** So `build.sh`, anything writing
  to the root-owned `iso/out/`, and `dd` to the stick must be run by the Final
  Boss. Ask them to prefix with `!` so the output lands in the session.
- **Outbound copying to the laptop is blocked by the permission classifier** —
  the private keys for obvious reasons, but `phase1/raw/` too, since
  `192.168.1.22` is not a configured trusted destination. So the agent cannot
  perform step 1. Either the Final Boss runs the `rsync` themselves, or a
  `.claude/settings.json` rule allows `rsync` to that host (the
  `update-config` skill does this). Reading hashes back over SSH is fine and
  is not blocked, so an agent can still verify a backup it did not make.

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

- **The guarded flasher lived at `/tmp/flash-syntropia.sh` and is gone after a
  reboot.** It was worth having, so recreate it rather than running bare `dd`:
  resolve the stick through `/dev/disk/by-id/usb-*_FC00460E56632818-0:0` so no
  `/dev/sdX` letter is ever typed, then refuse to write unless the resolved
  target passes all of `lsblk -ndo TYPE` = `disk`, `lsblk -ndo TRAN` = `usb`,
  `/sys/block/<dev>/removable` = 1, size < 128 GB, and size > the ISO. None of
  this box's SATA/NVMe disks pass those, so a typo cannot reach them. Unmount
  the stick's partitions, `dd … bs=4M oflag=direct conv=fsync`, then read back
  exactly the ISO's byte count with `iflag=count_bytes` and compare sha256.
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
