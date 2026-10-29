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

## ⏭️ Where we are / resume here (written 2026-10-27, end of session — take a break)

**STATUS: ALL MAJOR ITEMS DONE.** The keyring/noctalia saga is closed, the
2026.10.27 ISO is built, verified, on the stick, and proven by a fresh-VM
install. Tree is clean and committed (tip 61b6701+). Nothing is on fire.

Done today (in order):
1. SSH into laptop set up (`r@192.168.1.22`, key-based; sshd enabled). Evidence
   collected: the Oct-26 install was fresh and carried the PAM sed fix, but its
   `/usr/local/lib/syntropia-installer/keyring.sh` was the OLD pre-fix lib —
   the stick's ISO (airootfs hash `e4769656…`) predated the repo fixes. The
   re-test failure was a stale-image problem, never an installer bug.
2. Laptop patched in place (/tmp/fix*.sh on it): gnome-keyring purged, PAM
   gnome lines commented, D-Bus files parked, `force_run kwalletd=` in both
   sddm stacks, full kwalletrc. Reboot → **no keyring prompt, no welcome,
   ksecretd running**. (faillock lesson: 5 tries/10 min lockout shows
   "Sorry, try again" for CORRECT passwords — wait, don't retype.)
3. Wizard failure diagnosed: stale CachyOS mirror (agent-browser 404 + bad
   sig) aborted the whole pacman batch. Mirrors re-rated; all 9 picks
   installed. Wizard hardened: per-package fallback retry (committed).
4. Committed everything in logical batches (d4a5e8b fixes, 90c8d73/1fe1b5b
   docs+tests, 1276aab wizard+guard, 61b6701 vm-verify).
5. Rebuilt: `iso/out/syntropia-2026.10.27-x86_64.iso` (sha256
   f3080cf609f2…aace0c3). New `verify_installer_libs()` build guard passed.
   Stick dd'd and content-verified (fixed keyring.sh on the stick).
6. Fresh-VM install (disk+vars wiped first) verified end-to-end: installer →
   app-wiz4rd picker (esc cancels cleanly) → desktop with no keyring prompt
   and no Noctalia welcome. SUPER+drag move/resize verified in-VM (needs qemu
   keyboard grab; xdotool can't send SUPER through QEMU GTK).
7. New skill `syntropia-usb-stick` — flash/verify checklist (freshness check +
   content check; never trust byte-exact dd alone).

## ⏭️ NEXT SESSION — resume here (written 2026-10-28, end of session)

**STATUS: wizard redesign done and pushed; tree clean; one ISO rebuild left to
carry the last two fixes.**

### Done today (2026-10-28)
1. **`syntropia-ssh-setup`** — one-command SSH server setup, shipped to
   `/usr/local/bin` on the live image AND the installed target (build.sh,
   install-runner, branding hook, and `verify_installer_libs()` byte-compares
   it). Installs openssh, enables sshd, makes an ed25519 key for the real user
   (SUDO_USER-aware, never /root), prints LAN IPs + `ssh-copy-id` hint; a
   second run after the key copy writes
   `/etc/ssh/sshd_config.d/50-syntropia-ssh.conf` (PasswordAuthentication no,
   KbdInteractiveAuthentication no, PermitRootLogin prohibit-password,
   AllowUsers <user>) validated by `sshd -t` and removed if invalid.
   Wizard catalog entry: `Remote|SSH Setup|syntropia-ssh-setup`.
2. **App wizard rebuilt around fzf** (the Go Bubble Tea TUI is no longer the
   shipped path; sources left in the repo). Full-width three-column list:
   coloured category · bold package name (`keet-bin`, not `keet`) · description
   truncated to the terminal width; optional 5th catalog field = aliases shown
   dimmed and searchable; centred slant SYNTROPIA banner; rounded border with
   no label; `selected-bg` stripe on ticked rows.
3. **Input model:** SPACE ticks (fzf's default is TAB only — this was a real
   bug: SPACE typed a space and ENTER installed the row under the cursor),
   ENTER installs only ticked rows, "nothing ticked" reopens the picker, and a
   `Proceed? [Y/n]` confirmation precedes anything touching the system.
   Answering **n returns to the picker** (a stray ENTER no longer ends the
   session); ESC still exits.
4. **yay replaces paru** as the AUR helper (both ship in the cachyos repo,
   identical flags). Tests and stub binaries renamed accordingly.
5. **Wizard terminal is chosen and sized**: preference order is
   kitty → ghostty → foot → alacritty → wezterm → konsole (konsole-first was a
   Plasma leftover), each launched at 110x34; the picker reads `tput cols` and
   only falls back to `COLUMNS` — an inherited COLUMNS from the launching shell
   was building rows wider than the window, which is what produced the wrapped,
   misaligned columns on the VM.
6. **Hyprland overlay** sizes wizard windows 1100x700.
7. **VM harness**: `~/vm-test/run-install-vm.sh` now shares the host
   `~/Desktop/app-wiz4rd` read-only as a 9p mount (`mount_tag=wizard`) so
   wizard UI changes can be tested without an ISO rebuild:
   `sudo mount -t 9p -o trans=virtio wizard /mnt/wizard`.
8. Tests: 428 passing; both repos pushed (`Project-Syntropia fa27aed`,
   `app-wiz4rd 8473cc3`).

### ⚠️ The one thing to do first
**The ISO in `iso/out/` is OLDER than the tree.** The last build (22:34)
carried the width/terminal fixes but NOT the picker loop-on-"no" or the
ticked-row stripe (they landed as `fa27aed` with tarball sha `5bff0d50…`).
Rebuild before any VM/laptop test:

```
cd ~/Desktop/Project-Syntropia
sudo -S -p '' env SOURCE_DATE_EPOCH=1786489200 ./iso/build.sh
```

Then verify the extracted `/etc/syntropia/app-wiz4rd` is byte-identical to
`~/Desktop/app-wiz4rd/app-wiz4rd` (the installer-lib guard does not cover it).

### Then (small)
1. **VM test the wizard properly**: kitty at 110x34, SPACE shows a ✓ + stripe,
   ENTER with nothing ticked reopens, `n` at the prompt returns to the picker,
   and `Remote → SSH Setup` + one normal app install in one batch. If the guest
   display is too small, turn off QEMU View → Zoom to Fit or raise the guest
   resolution (`hyprctl monitors`, then `hyprctl keyword monitor <name>,1600x900@60,0x0,1`).
2. **Two older checklist items** (one casual laptop session):
   - Brave launches after the wizard installs it
   - No limine-snapper name warning at boot
3. **Optional laptop hygiene:** reinstall the laptop from the current stick so
   it matches the verified path (it was patched in place from an older ISO).
4. **AUR packaging of the app wizard** — explicitly deferred today; revisit
   after the laptop/VM passes. (app-wiz4rd already has an `aur/PKGBUILD` and a
   `scripts/release.sh` that produces the source tarball + zero-install tarball.)

### Notes for whoever picks this up
- The wizard ships from the **vendored tarball** `iso/vendor/app-wiz4rd-0.1.0.tar`
  (built by `~/Desktop/app-wiz4rd/scripts/release.sh`, which archives
  `HEAD^{tree}` with pinned mtime and excludes `aur/`, `scripts/`, `.github/`).
  Always regenerate via that script — an ad-hoc `git archive` leaks those dirs
  into the tarball and re-hashes differently.
- **The standalone repo can drift behind the tarball.** Today the repo was
  missing the per-package solo-retry fallback that the shipped tarball had;
  rebuilding from repo HEAD silently dropped it and a test caught it. Diff the
  old and new tarballs after every regeneration.
- The confirm prompt is skipped when `SYNTROPIA_WIZARD_ASSUME_YES` is set or
  there is no tty; the test harness sets that variable.
- `iso/tests/test_ssh_setup.py` drives the shipped wizard through a pty with a
  stub `fzf`; if real fzf gains a required flag, that stub is what to update.

VM helpers: `~/vm-test/run-install-vm.sh` (points at the 2026.08.12 build, i.e.
the current tree; now also shares the wizard repo over 9p),
`~/vm-test/run-keytest-vm.sh` (adds `-monitor unix:` socket + `-k en-us` +
grab-on-hover for input testing). Wipe qcow2+OVMF_VARS before install tests.


## ⏭️ NEXT SESSION — resume here (written 2026-10-29)

**STATUS: laptop reinstalled from a current ISO and verified over SSH; all open
checklist items closed. Known limitation accepted: no KWallet under autologin.**

### Done today (2026-10-29)
1. **ISO rebuilt** (full build — the wizard tarball is baked into phase 1):
   `iso/out/syntropia-2026.08.12-x86_64.iso`, 2026-10-29 12:29, 3,494,998,016 B,
   sha256 `19c6554df248…92141a`. Verified: `}}` count 0 in grub.cfg, 3 nvidia
   blacklist entries + the Turing+ entry, `iso-boot-config.py check` passes,
   sessions = hyprland-uwsm + hyprland only, `verify_installer_libs()` passed,
   `/etc/syntropia/app-wiz4rd` byte-identical to `~/Desktop/app-wiz4rd`
   (28975c98…, carries `selected-bg` stripe + `space:toggle+down` + the
   picker loop-on-"no"), 428 tests green.
2. **Stick dd'd and content-verified**: the stick's `airootfs.sfs` sha256 equals
   the ISO's exactly (`442d0f41d71b…`); wizard, keyring.sh and ssh-setup pulled
   back off the stick match the repo.
3. **Laptop fresh-installed from that stick and checked over SSH**
   (`r@192.168.1.22`, key auth; the reinstall changed host keys — the stale
   `known_hosts` entry made the first attempts fail, `ssh-keygen -R` fixed it):
   - PRETTY_NAME="CachyOS Syntropia", ID=cachyos, VARIANT_ID=syntropia
   - sddm active, autologin → hyprland-uwsm.desktop; only the two Hyprland sessions
   - gnome-keyring absent; sddm + sddm-autologin carry the commented gnome lines
     and `pam_kwallet5 … force_run kwalletd=/usr/bin/ksecretd`
   - Noctalia: `.setup-complete` + `setup_wizard_enabled = false` → no welcome
   - wizard installed `freebuff-bin` cleanly, pending queue empty
   - PipeWire 1.6.10 with a real analog sink; all three units active
   - **Brave (checklist item) CLOSED**: brave-bin 1.98.60, sandbox root:root 4755,
     `brave --headless=new --dump-dom about:blank` renders
   - **limine-snapper warning (checklist item) CLOSED**: none in the boot journal
4. **chrome-sandbox hook path gap fixed**: brave-bin now installs its helper at
   `/opt/brave-bin/chrome-sandbox`, which neither the hook script's path list nor
   the pacman hook's Target list covered (it works today only because the package
   ships 4755). Added to `iso/hook-scripts/hook-chrome-sandbox.sh`,
   `iso/build.sh`'s `syntropia-chrome-sandbox.hook` and the test. Needs the next
   rebuild to reach an ISO.

### ✅ RESOLVED 2026-10-29 — KWallet now unlocks (no autologin, "security over convenience")

Final Boss' decision: **drop autologin**; the account password typed at the SDDM
greeter is the PAM path to the wallet. Root cause chain, proven on hardware:

1. `pam_systemd_loadkey` was never the problem — the LUKS passphrase reached
   `pam_kwallet5`, which hashed it and started `ksecretd --pam-login`.
2. `ksecretd` then blocked in `accept()` on `/run/user/<uid>/kwallet5.socket`
   waiting for `/usr/lib/pam_kwallet_init` to send the session environment.
   Nothing runs that binary under Hyprland/UWSM: its XDG autostart entry carries
   `X-systemd-skip=true` and `plasma-kwallet-pam.service` is static/Plasma-only.
3. `kwalletrc` carried `Enabled=false`, which makes ksecretd/kwalletd6 exit 255
   before `pamOpen()`; the installer only ADDED `Enabled=true` when the key was
   missing, so a pre-existing false survived.
4. Even with the handshake, `ksecretd` is a Qt app: with no display in the
   forwarded environment it aborts with "no Qt platform plugin could be
   initialized". Hyprland's own `/proc/<pid>/environ` has NO `WAYLAND_DISPLAY`
   (it is the compositor — only its children get one), so the environment has to
   be discovered, not copied.

Fix in the tree: `keyring.sh` forces `Enabled=true` + `Default Wallet=kdewallet`;
new `iso/installer/lib/syntropia-kwallet-unlock` discovers the `wayland-*` socket
(offscreen as fallback) and runs `pam_kwallet_init`, retrying until a `*.kwl`
appears; new user unit `syntropia-kwallet-unlock.service` enabled under
`graphical-session.target.wants`; the runner no longer writes autologin (empty
`sddm.conf`, `10-syntropia.conf` carries the default session) and installs the
helper + unit; `build.sh` and `hook-branding-users.sh` ship the same three files.

Proven on the laptop (2026-10-29, password login at the greeter, helper run by
hand): `syntropia-kwallet-unlock: wallet unlocked via PAM (Default keyring.kwl)`,
`org.freedesktop.secrets` owned by ksecretd, and `secret-tool store`/`lookup`
round-trip with no prompt. Note the collection lands as **"Default keyring.kwl"**
(KWallet 6 names it after the first libsecret consumer) — do not pin any check to
`kdewallet.kwl`. Tests: 434 passing.

### Wizard: the Proceed prompt no longer loses the ticks (2026-10-29)

fzf keeps no state between runs, so answering `n` and looping back into the picker
dropped every tick. The confirmation now runs INSIDE fzf: fzf >= 0.53 gets
`enter:execute(confirm)+transform:…` and the picker never closes on "no", so ticks
and cursor survive. The ticked set is tracked by the toggle bindings in a temp
file, because fzf's `{+}` expands to the row under the cursor when the selection
is empty — which is also why "nothing ticked" used to install the cursor row; it
now stays in the picker with a hint. fzf < 0.53, the numbered fallback and the
pty/stub-fzf tests keep the old bind and post-picker prompt.

Proven in tmux with real fzf + stub yay: tick two, ENTER, answer `n` → picker
still open with both ticks → ENTER, `y` → exactly those two packages installed.

**Gotcha that cost a suite timeout:** the version probe must be
`fzf --version </dev/null` — the test stub reads stdin and ignores argv, so an
inherited stdin blocks the wizard forever.

**VERIFIED 2026-10-29 evening on a FRESH install from the 16:26 ISO**
(sha256 `fb7a4a8b2f66…`, stick `airootfs.sfs` `6fb101375222…`), user `r5`:

- No autologin: `/etc/sddm.conf.d/10-syntropia.conf` only, no `[Autologin]` block;
  SDDM greeter asks for the password (journal shows `pam_kwallet5(sddm:session)`).
- The wallet unlocks BY ITSELF ~4 s after login — no manual helper run:
  `syntropia-kwallet-unlock[1080]: wallet unlocked via PAM (kdewallet.kwl)`,
  `kdewallet.kwl` + salt created at session start, `kwalletrc` `Enabled=true`
  `Default Wallet=kdewallet`, `org.freedesktop.secrets` owned by ksecretd.
- `secret-tool store` → `secret-tool lookup` round-trips (`probe`) with no prompt.
- Wizard installed `brave-bin` + `kitty` in one batch, queue empty, and the
  chrome-sandbox hook fired (`Syntropia: make chrome-sandbox a root-owned setuid
  helper`); `/opt/brave-bin/chrome-sandbox` is root:root 4755 and
  `brave --headless=new --dump-dom about:blank` renders.
- `pacman -Qkk` reports only "backup file … (Modification time mismatch)" noise;
  the only failed unit is `systemd-networkd-wait-online` (expected on this network).

**Still to do:** nothing blocking. The wizard's in-picker confirm was also exercised
on the laptop by the Final Boss (tick, ENTER, `n` — ticks kept). Only pushing the two
repos is left.

### ⚠️ Superseded note (kept for the history) — the limitation as first found
**KWallet never opens under SDDM autologin.** Evidence on the fresh laptop: only
`kdewallet.salt` exists (no `.kwl`), `kwalletrc` reads `Enabled=false`,
`org.kde.kwalletd6` will not activate ("unit failed") and
`org.freedesktop.secrets` is "not activatable"; `ksecretd --pam-login` runs with
`PAM_KWALLET5_LOGIN` set but has no password to unlock with. The Phase-1
non-negotiable (no prompt at first login) still holds; secret persistence is
simply unavailable. The choice is between (a) accept it — autologin stays, no
gnome-keyring, no unencrypted wallet — and (b) give up autologin so KWallet can
unlock with the login password. Nothing is decided yet; the Final Boss has not
picked. Revisit only if an app starts visibly failing on a missing secrets
service.

### Then (small)
1. Rebuild + re-flash so the chrome-sandbox hook path fix is in an image
   (`sudo env SOURCE_DATE_EPOCH=1786489200 ./iso/build.sh`).
2. Not yet exercised on hardware: the wizard's **`n` at the Proceed prompt returns
   to the picker** and **ENTER with nothing ticked reopens it** (the laptop run
   installed in one pass). Cheap check next time the wizard runs.
3. `syntropia-ssh-setup` second run on the laptop to apply the hardening drop-in
   (PasswordAuthentication no, AllowUsers r) — key auth is proven working.

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

**OPEN — re-test after the next rebuild** (closed 2026-10-27: fresh-VM install
from syntropia-2026.10.27 verified all of the below)
- ✅ No wallet/keyring prompt at first login (SDDM + gnome-keyring fix)
- ✅ No Noctalia welcome wizard on first boot
- ✅ Windows move/resize with SUPER + drag (laptop + fresh VM, qemu
  grab-on-hover; xdotool can't synthesize SUPER through QEMU GTK — use
  View/keyboard grab or the monitor when testing binds in a VM)
- ✅ Brave launches after the wizard installs it — 2026-10-29 laptop, brave-bin
  1.98.60, sandbox 4755, headless dump-dom renders
- ✅ No limine-snapper name warning — 2026-10-29 laptop boot journal clean

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
