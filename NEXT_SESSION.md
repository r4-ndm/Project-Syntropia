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
4. **Sessions:** **Hyprland (UWSM) only — Plasma removed (live + target).**
   The installer asks nothing about the desktop, `build.sh` deletes the stock
   KDE entries from `packages_desktop.x86_64` before pacstrap (and ships `sddm`
   as the login manager), and the runner wires SDDM autologin into
   `hyprland-uwsm.desktop`, the required session — a missing UWSM session is a
   build bug and aborts the install.
5. **Bootloader: Limine everywhere** (installed system; BIOS `ef02` + ESP
   partitions; identity `/+CachyOS Syntropia` synced with os-release).
6. **Identity single source:** `OS_RELEASE_CONTENT` in
   `phase1/cli/transform/syntropia_transform/transform.py` — build.sh
   AST-extracts it; never duplicate it elsewhere.

## 📍 Current status (2026-10-25)

- **First real-laptop install done** (2026-10-25, Hyprland-only ISO): reboot
  chain, Limine, branding, the app-wiz4rd install flow and audio all work.
  Four defects it surfaced are fixed in the tree (not yet in an ISO):
  1. **Keyring prompt, again** — SDDM's stock PAM stack carries
     `pam_gnome_keyring` lines that plasmalogin's never had, and the image does
     ship gnome-keyring (it owns `org.freedesktop.secrets`). `lib/keyring.sh`
     now wires the full auth/password/session `pam_kwallet5.so` stack into
     `sddm` **and `sddm-autologin`**, comments the gnome lines out, parks
     gnome-keyring's D-Bus activation files, and the runner drops autologin if
     the chain cannot feed the wallet.
  2. **Windows not grabbable** — stock `config/binds.lua` binds
     `SUPER + mouse:272/273` without Hyprland's `{ mouse = true }` flag, so they
     never fire. The Syntropia overlay now declares the mouse binds itself (plus
     `SUPER + CTRL_L`/`ALT_L` for touchpads) and pins the wizard window.
  3. **Brave broken** — `chrome-sandbox` needs `root:root 4755`; Brave arrives
     via the wizard (paru/AUR), so a pacman hook shipped by `build.sh` fixes it
     after any install (`/usr/local/bin/syntropia-fix-chrome-sandbox`).
  4. **PipeWire** — verified only: `pipewire`, `pipewire-pulse`, `wireplumber`
     (+ alsa/jack) are all in the live image and therefore the target. No change.
  Phase-1 tests: 415 passed.

- **Hyprland-only desktop (2026-10-25)**: Plasma is gone from the live ISO and
  the installed target. No desktop question in the TUI installer
  (`desktop_env` is fixed to `hyprland`), `build.sh` deletes the nine KDE
  entries from `packages_desktop.x86_64` before the pacstrap transaction and
  adds `sddm` as the login manager, and the runner emits SDDM autologin only —
  no `plasmalogin.conf*`, no `plasmalogin.service` wiring, no `plasma.desktop`
  fallback (a missing `hyprland-uwsm.desktop` now stops the install).
  **Not yet rebuilt into an ISO.**
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
- Repo state as of 2026-10-25 late evening (branch `main`, ahead of origin, not
  pushed): **13 files modified / 3 new, UNCOMMITTED** — Plasma removal + the four
  laptop fixes, all verified (bash -n, 415 tests) but NOT yet in any ISO.
  The USB stick is dd'd with the OLDER 22:39 build (Hyprland-only, keyring/mouse/
  Brave fixes NOT on it). Final Boss paused here: rebuild happens tomorrow (2026-10-26).

## ⏭️ Where we are / resume here (written 2026-10-26 evening)

1. Laptop re-test of the 2026-10-26 20:10+ ISO (stick dd'd, verified byte-exact)
   STILL shows BOTH: keyring "choose password" prompt AND "Welcome to Noctalia".
   VM install from the SAME ISO was clean (Final Boss: "looks good").
2. Root cause of the keyring prompt WAS found and fixed via VM-disk inspection
   (qcow2 → qemu-nbd → LUKS mount): keyring.sh:295 sed jammed
   `auto_startforce_run` into the PAM line, so pam_kwallet5.so never
   force-started the daemon. Fixed + regression test (416 tests). The fixed ISO
   is built and on the stick — the laptop re-test that still failed was run
   against an install whose actual state we have NOT verified.
3. TOMORROW: collect from the laptop (decisive evidence, in this order):
   - `stat -c '%y' /etc/pam.d/sddm` → the REAL install date
   - `grep -E 'kwallet|gnome' /etc/pam.d/sddm` → fixed line present?
   - `pacman -Q gnome-keyring kwallet-pam` → purge applied?
   - `ls -la ~/.config/noctalia/ ~/.local/state/noctalia/`
   - `cat ~/.config/kwalletrc` → check Enabled= (was flipped to false on VM)
   Working theory: the laptop install reuses/keeps the old @home subvolume, so
   the broken kwallet + noctalia wizard state survives every "fresh" install.
4. Noctalia welcome is a layer-surface, not a window — the windowrule fallback
   CANNOT catch it. Real suppression: setup_wizard_enabled=false +
   [shell.launcher.panels] ignored += "setup-wizard" + .setup-complete markers
   seeded synchronously BEFORE `noctalia` execs (autostart.lua chains them).
5. After laptop evidence: one scoped agent pass on the true cause, rebuild,
   re-flash, re-test. THEN ask the Final Boss to commit the whole batch
   (Plasma removal + all laptop fixes) — do not let the tree sit dirty
   (the Oct-24 loss lesson). Repo currently: ~15 files modified/untracked,
   all verified, 416 phase-1 tests pass.

## ✅ Verification checklist

**DONE**
- ✅ ISO boots as CD-ROM (OVMF) — installer works
- ✅ ISO boots as raw USB disk (OVMF usb-storage) — the laptop path
- ✅ Keyring prompt at login — no prompt on fresh install (VM-verified)
- ✅ Sessions = hyprland-uwsm only (Plasma removed 2026-10-25); launcher present in rootfs
- ✅ No proc/sys content in the squashfs; boot-config guard active

**DONE — 2026-10-25 laptop install**
- ✅ New ISO dd'd to stick boots on the laptop
- ✅ TUI install completes (keyboard → network → password → Limine)
- ✅ Reboots straight into installed system; Limine + branding applied
- ✅ Hyprland + Noctalia loads via UWSM
- ✅ First-boot wizard `app-wiz4rd` fires and installs picks
- ✅ PipeWire audio works (YouTube)

**OPEN — re-test after the next rebuild**
- ⬜ No wallet/keyring prompt at first login (SDDM + gnome-keyring fix)
- ⬜ Windows move/resize with SUPER + drag
- ⬜ Brave launches after the wizard installs it
- ⬜ No limine-snapper name warning

## ▶️ Next steps (in order)

1. Rebuild the ISO (the four laptop fixes above are **not** in the 2026-10-25
   image yet) and re-flash the stick, then re-test the OPEN checklist.
2. Fix whatever the re-test surfaces (one batched agent pass, scoped
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
