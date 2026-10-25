# 📋 Syntropia — Mission & Status (single source of truth)

> **Every agent: start here.** Then read `agent-rules/README.md` + every file in
> `agent-rules/`, and `.agents/skills/iso-builder/SKILL.md` for ISO work.
> This file carries the mission, the current state, and the open checklist.
> Update it in the same commit as any change that alters status.

## 🎯 Mission

**Syntropia is a laptop-friendly everyday Linux for the Final Boss and music
producers** (Phase 1 scope). A **CachyOS re-skin** — the same relationship
Linux Mint has to Ubuntu: CachyOS base and repos, Syntropia branding, apps
wizard, and audio-production layer on top. Identity follows the freedesktop
derivative pattern (`ID=cachyos`, `VARIANT_ID=syntropia`, `PRETTY_NAME="CachyOS
Syntropia"`); the long-term goal is a full fork, but **not yet**.

- Ship target today: the install ISO (`iso/`), consumed by the Final Boss's own
  machines. Not a community distro yet — pre-1.0, no users depending on
  installer stability.
- Non-negotiables: pre-Turing NVIDIA GPUs (GTX 1070 class) must boot — the
  live/install boot configs blacklist nvidia-open and select nouveau; the
  TUI installer is the primary path, Calamares secondary; no keyring/wallet
  prompt at first login; one password at install.
- The **host box is NOT a test target**: it has the live transform applied.
  `syntropia transform --check` only, never `--yes` (transform-safety rule).

## 🏗️ Architecture (settled, approved by Final Boss)

1. **Omarchy-style TUI installer** (`syntropia-install` on tty1, <3s boot):
   keyboard layout → network → one password (LUKS2 + Btrfs subvols) →
   progress dashboard (`syntropia-install-dashboard` + `-runner`).
2. **Base desktop: stock CachyOS Hyprland Noctalia** (`cachyos-hypr-noctalia`
   + `noctalia`): upstream-maintained Lua config under UWSM; Noctalia (Rust)
   replaces Waybar/SwayNC/Rofi/wlogout. **No hand-rolled dotfiles** — only a
   Syntropia drop-in overlay (wallpaper, wizard autostart, DAW/VST floating
   rules, cheatsheet hotkeys).
3. **First-boot wizard** `app-wiz4rd` (TUI in a floating terminal, launched by
   `iso/profiles/hyprland/bin/syntropia-app-wiz4rd`; offline queue + resume).
4. **Sessions:** Plasma + Hyprland (UWSM) only — plain `hyprland.desktop`
   entries are stripped from live and target rootfs; autologin requires
   `hyprland-uwsm.desktop`.
5. **Bootloader: Limine everywhere** (installed system; BIOS `ef02` + ESP
   partitions; identity `/+CachyOS Syntropia` synced with os-release).
6. **Identity single source:** `OS_RELEASE_CONTENT` in
   `phase1/cli/transform/syntropia_transform/transform.py` — build.sh
   AST-extracts it; never duplicate it elsewhere.

## 📍 Current status (2026-10-25)

- **ISO rebuilt 2026-10-25 18:35** (`iso/out/syntropia-2026.08.12-x86_64.iso`,
  3.5G) and **verified**: no `}}` in any boot config, `iso/lib/iso-boot-config.py
  check` passes, nvidia blacklist + Turing+ entry present in GRUB and syslinux,
  OVMF raw-USB-disk boot (the laptop failure path) renders the menu and boots
  with zero lexer errors. Phase-1 tests: 397 passed.
- **USB-boot bug FIXED** (root cause: `}}` menuentry closers in grub.cfg broke
  real-firmware GRUB; CD-ROM/El-Torito boots and `grub-script-check` masked it).
  Guard now fails the build on that class of error. Commit `89bc9d4`.
- Earlier fixes all in: keyring/KWallet PAM wiring, app-wiz4rd launcher chain,
  session-picker cleanup, remaster-mount hardening (lazy umount + squashfs
  excludes; the 15-hour mksquashfs hang class), zstd 15, stale-stock guard,
  Limine verification hook.
- Repo state: working tree clean as of 2026-10-25 (branch `main`, **ahead of
  origin — not pushed**, per git-hygiene rule 2).

## ✅ Verification checklist

**DONE**
- ✅ ISO boots as CD-ROM (OVMF) — installer works
- ✅ ISO boots as raw USB disk (OVMF usb-storage) — the laptop path
- ✅ Keyring prompt at login — no prompt on fresh install (VM-verified)
- ✅ Sessions = plasma + hyprland-uwsm only; launcher present in rootfs
- ✅ No proc/sys content in the squashfs; boot-config guard active

**OPEN — laptop (real hardware) test**
- ⬜ New ISO dd'd to stick boots on the laptop
- ⬜ TUI install completes (keyboard → network → password → Limine)
- ⬜ Reboots straight into installed system
- ⬜ Hyprland + Noctalia loads via UWSM; Syntropia wallpaper/branding applied
- ⬜ First-boot wizard `app-wiz4rd` fires and installs picks
- ⬜ PipeWire audio works; no limine-snapper name warning

## ▶️ Next steps (in order)

1. Final Boss re-flashes the stick with the 2026-10-25 ISO and tests on the
   laptop against the OPEN checklist above.
2. Fix whatever the laptop run surfaces (one batched agy/freebuff pass, scoped
   `touch ONLY iso/`, then rebuild + re-verify).
3. VM open-checklist items (Hyprland/Noctalia, wizard, audio) if laptop leaves
   any doubt, using `~/vm-test/run-install-vm.sh` (wipe qcow2 + OVMF vars first).
4. Only after a clean laptop install: consider an AUR/package refresh and the
   base-refresh policy check (`.agents/skills/iso-builder/SKILL.md`).

## ⚠️ Session lessons (do not repeat)

- **VM test script reuses** `syntropia-test.qcow2` + `OVMF_VARS.fd` — wipe both
  (`rm -f ~/vm-test/syntropia-test.qcow2 ~/vm-test/OVMF_VARS.fd`) or you boot
  the OLD installed system (masks as a LUKS emergency-mode bug).
- **Test the USB path, not just CD-ROM.** Attach the ISO via `-device
  usb-storage` in OVMF; `grub-script-check` is NOT a validator (accepts `}}`).
  `iso/lib/iso-boot-config.py check <extracted-boot-dir>` is.
- `run-install-vm.sh` needs `DISPLAY=:0 XAUTHORITY=~/.Xauthority` from an agent
  shell, else "gtk initialization failed".
- The ISO's grub.cfg carries no cryptdevice/host UUID — if boot weirdness
  appears, suspect the VM disk first, not the ISO.
- A killed build leaves `/var/lib/pacman/db.lck` (sudo rm) and can leave
  read-only kernel mounts in `iso/work/remaster/rootfs` (lazy-umount then
  rm -rf; see iso-builder skill).
- Heavy pacstrap can freeze the 16GB/4-core box; builds flip the UEFI
  BootOrder after reboots — check `efibootmgr` (CachyOS entry first, Windows
  second) if a reboot lands on Windows.
- Old VM background notifications ("terminating on signal 15") are cleanup,
  not failures.
- Agent-orchestration note: drive fix work via agy or freebuff (tmux, task
  spec in a file), then **verify independently** (`bash -n`, targeted
  checkers, pytest) — never trust the agent's self-report alone. Uncommitted
  fixes CAN get lost from the tree (the Oct-24 set did) — commit verified
  work promptly after asking the Final Boss.
