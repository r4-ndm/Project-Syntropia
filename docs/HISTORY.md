# 📚 Syntropia — Session History (archive)

> **This is history, not instructions.** It is the session-by-session evidence
> trail behind today's code: what broke, what was proven on hardware, and which
> fixes were tried first. Read it when you need the *why* behind a decision.
>
> For what is true **now** and what to do **next**, read `NEXT_SESSION.md`.
> For binding rules, read `agent-rules/`. For build steps, read `iso/README.md`
> and `.agents/skills/iso-builder/SKILL.md`.
>
> The log below is kept verbatim, newest entries last. Several sections are
> explicitly marked **superseded** — the newer section wins; the older one is
> kept only because it records the evidence that led to the fix.

## Reading guide

| Looking for | Section |
|-------------|---------|
| 2026-10-25 laptop install, first real end-to-end run, four defects it surfaced | *Current status (2026-10-25)* |
| 2026-10-27 keyring/Noctalia saga closed, first verified fresh-VM install | *resume here (written 2026-10-27)* |
| 2026-10-28 SSH setup helper + wizard rebuilt around fzf | *resume here (written 2026-10-28)* |
| 2026-10-29 wallet resolution (drop autologin), wizard tick fix, laptop verification | *resume here (written 2026-10-29)*, both entries |
| 2026-11-19 sshd hardening no-op fixed, CachyOS base refresh | *resume here (written 2026-11-19)*, plus the `✅ RESOLVED (2026-11-19)` section |
| 2026-11-21 repo cleanup, sshd proof on hardware, installer residue fix, AUR refresh | *resume here (written 2026-11-21)* |
| 2026-11-21 (late) Phase 1 closed on hardware; ssh-setup made one-command; wizard SSH pick found to be a no-op | *resume here (written 2026-11-21 late)* |
| Recurring traps and lessons | *Session lessons*, *Do-not-repeat* |

---

# Archive (verbatim)

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

## ⏭️ NEXT SESSION — resume here (written 2026-10-29, end of session)

**STATUS: Phase 1 works end to end on real hardware. Nothing is on fire. One known
bug to fix (sshd hardening), then Phase 1 is closable.**

### Read this first
1. `NEXT_SESSION.md` (this file) → `AGENTS.md` → every file in `agent-rules/`.
2. The 2026-10-29 sections below carry the full evidence trail for the wallet and
   the wizard; you do not need to re-derive it.
3. Both repos are clean and pushed:
   - Project-Syntropia `79d6239`
   - app-wiz4rd `eef2b37`

### THE ONE THING TO DO
**Fix the sshd hardening no-op.** `iso/installer/lib/ssh-setup.sh` writes
`50-syntropia-ssh.conf`, but the image ships `10-archiso.conf` with
`PasswordAuthentication yes` + `PermitRootLogin yes` and **sshd honours the first
value it reads** — so on every fresh install the "hardened" box still accepted
passwords and root password logins. Required change: write
`00-syntropia-ssh.conf`, neutralise `10-archiso.conf` (rewrite its values — do not
trust ordering alone), and verify the EFFECTIVE config with
`sshd -T | grep -E '^(passwordauthentication|permitrootlogin|allowusers)'`, failing
loudly and reverting when something outbids it. Test must include a `10-…=yes` file
that must not win. Then: rebuild ISO → flash → reinstall → verify from the desktop
that `ssh -o PubkeyAuthentication=no -o PreferredAuthentications=password` fails with
`Permission denied (publickey)`.

### Then (small, optional)
1. AUR/package refresh (`syntropia`, `syntropia-cli`, `syntropia-brews`) from the
   current tree + the base-refresh policy check — this is the last item of the
   Phase-1 close sequence.
2. Declare Phase 1 done and open Phase 2 (Awakening) deliberately.

### Machine facts you will need
- Laptop: `r5@192.168.1.22`, key auth works; **every reinstall rotates the host key**
  → `ssh-keygen -R 192.168.1.22` then `ssh-copy-id r5@<ip>`.
  `ssh -o PubkeyAuthentication=no …` is now refused (after the manual hardening).
- Host build: `cd ~/Desktop/Project-Syntropia && sudo env SOURCE_DATE_EPOCH=1786489200 ./iso/build.sh`
  (FULL build — the wizard tarball, helper and profiles are baked into phase 1).
  Pre-flight: `df -h /`, `free -g`, `grep remaster /proc/mounts` (0),
  `ls /var/lib/pacman/db.lck` (absent).
- Flash: `sudo dd if=/home/r4/Desktop/Project-Syntropia/iso/out/syntropia-2026.08.12-x86_64.iso of=/dev/sdd bs=4M conv=fsync status=progress`
  — **never `/dev/sdX`**: dd happily creates `/dev/sdX` as a 3.3G file and flashes
  nothing. Verify by hashing the stick's `arch/x86_64/airootfs.sfs` against the ISO's.
- Current verified image: 2026-10-29 16:26, sha256 `fb7a4a8b2f66…`, stick sfs
  `6fb101375222…`.
- Wizard repo: edit `~/Desktop/app-wiz4rd/app-wiz4rd` → `./scripts/release.sh` →
  copy the tarball into `iso/vendor/` → re-pin `APP_WIZ4RD_SHA256` in `iso/build.sh`
  AND `aur/PKGBUILD` → run the suites. The tarball is built from `HEAD^{tree}`, so
  **commit the wizard first**.
- Tests: `~/.local/bin/pytest -q phase1/tests iso/tests` (434 passing).

### Do-not-repeat (learned the hard way today)
- `loginctl terminate-session` on the graphical session can leave sddm running with
  **no greeter** — blank screen, ssh fine. Recover with `systemctl reboot` over ssh;
  a clean logout is `uwsm stop` (Hyprland here is Lua-configured, `hyprctl dispatch
  exit` is invalid).
- Never test wallet/handshake changes mid-session: forcing the handshake kills the
  PAM-started ksecretd (the hash lives only in that process) and costs a login cycle.
- `pam_systemd_loadkey` was never the problem under autologin; the missing piece was
  the session-environment handoff plus ksecretd needing a Qt platform. Full story in
  the 2026-10-29 sections and in the `project-syntropia` skill.
- The wizard's fzf version probe must run `</dev/null`, or the test stub blocks the
  whole suite (cost a 10-minute timeout).

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

### ✅ RESOLVED (2026-11-19) — sshd hardening no-op fixed in the tree, not yet in an ISO

`iso/installer/lib/ssh-setup.sh` now writes `00-syntropia-ssh.conf` (not `50-`), so it
is read before `10-archiso.conf`. It also directly neutralizes any `10-archiso.conf`
found in the drop-in dir (rewrites `PasswordAuthentication`/`PermitRootLogin` off
`yes` in place — do not trust ordering alone), and after `systemctl restart sshd`
re-derives the EFFECTIVE config with `sshd -T` and reverts + fails loudly if anything
still outbids the hardening (covers the general case, not just the known archiso
file). New tests: `test_sshd_hardening_neutralizes_archiso_dropin_so_it_cannot_win`
and `test_sshd_hardening_fails_loudly_and_reverts_when_something_still_outbids_it`.
436 tests passing (phase1 + iso). **Still needed: rebuild the ISO, reflash, and
verify on real hardware** — `ssh -o PubkeyAuthentication=no -o
PreferredAuthentications=password` must fail with `Permission denied (publickey)`
on a fresh install, and `sshd -T` on the box should show `permitrootlogin
prohibit-password`.

### 🔴 OPEN BUG, superseded above (found 2026-10-29) — sshd hardening is a no-op on installed systems

`syntropia-ssh-setup`'s second run wrote `/etc/ssh/sshd_config.d/50-syntropia-ssh.conf`
with `PasswordAuthentication no` / `AllowUsers <user>` and reported success, but the
settings never took effect: the image ships **`10-archiso.conf`** (archiso leftover)
containing `PasswordAuthentication yes` + `PermitRootLogin yes`, and **sshd honours the
FIRST value it reads**, so the lexically-earlier file wins. Net effect on a fresh
install: password auth stayed enabled and **root password login was permitted** until
it was patched by hand on the laptop (renamed to `00-syntropia-ssh.conf`, and the
`10-archiso.conf` values rewritten to `no` / `prohibit-password`).

Fix in the repo: `iso/installer/lib/ssh-setup.sh` must write `00-syntropia-ssh.conf`
(never `50-`), and must verify the EFFECTIVE config — `sshd -T | grep -E
'^(passwordauthentication|permitrootlogin|allowusers)'` — instead of trusting the file
it just wrote, failing loudly (and reverting) when something outbids it. Add a test
that a `10-archiso.conf` with `yes` cannot defeat the result. Same lesson class as the
wallet's `Enabled=false`: a file that looks correct while the runtime disagrees.

**Still to do:** that sshd fix. The wizard's in-picker confirm was also exercised
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

## ⏭️ NEXT SESSION — resume here (written 2026-11-19, end of session)

**STATUS: sshd fix is built, tested, in a rebuilt ISO, and on the stick.
Laptop reinstall + real-hardware verification is the one thing left — paused
here for the day, pick up tomorrow.** Context for this push: the Final Boss
wants to start using Syntropia as a daily-driver main machine and keep
building Syntropia from within it; the open sshd hole was the blocker, so
closing it end-to-end (not just in the repo) is what unblocks that move.

### Done today (2026-11-19)
1. **sshd hardening no-op fixed** (see the `✅ RESOLVED` section above this
   one for the full technical writeup) — `00-syntropia-ssh.conf`,
   `10-archiso.conf` neutralization, `sshd -T` effective-config verification
   with revert-on-mismatch. Two new regression tests. 436 tests passing.
2. **CachyOS base was 6+ weeks stale and is now refreshed.** The vendored
   `iso/work/CachyOS-Live-ISO` clone was pinned at a Sep-30 commit (11 commits
   behind upstream's Nov-15 "26.11" changelog) because `build.sh`'s own
   in-place patches to `packages_desktop.x86_64` (KDE/gnome-keyring removal)
   left the clone dirty, so `git pull --ff-only` silently never advanced once
   upstream touched that same file — it just failed and (because this is
   mid-script, not caught) nobody noticed. **Fixed:** `build.sh` now runs
   `git -C "$WORK_DIR/CachyOS-Live-ISO" reset --hard HEAD` before pulling —
   safe, since every patch is reapplied deterministically each run. Confirmed
   the pull then fast-forwards `3215497..b0ebcae`.
3. **Rebuilt, verified, and flashed:**
   `iso/out/syntropia-2026.08.12-x86_64.iso`, 2026-11-19 21:21, 3,534,958,592 B,
   sha256 `e802b85e38c74bb5711c02251b290d332f3e14e080a928dcdec93d66a7813163`.
   `verify_installer_libs()` passed (embedded `ssh-setup.sh` matches the fixed
   repo version). Boot config check passed (9 files), `}}` count 0, 3 nvidia
   blacklist/nouveau entries present. Stick (`/dev/sdd`) dd'd and
   content-verified: `arch/x86_64/airootfs.sfs` sha256
   `88bbd58024ad394578e629ca8e42453aaa347e987779be1f450f0b30f82419cd` matches
   the ISO exactly.

### THE ONE THING TO DO
**Boot the laptop from the flashed stick and reinstall, then verify the sshd
fix on real hardware.** Steps:
1. Plug the stick (`/dev/sdd` on this host) into the laptop, boot from it,
   run the TUI install (keyboard → network → one password → Limine).
2. Reboot rotates the laptop's SSH host key —
   `ssh-keygen -R 192.168.1.22` before connecting again.
3. Verify: `ssh -o PubkeyAuthentication=no -o
   PreferredAuthentications=password r5@192.168.1.22` must fail with
   `Permission denied (publickey)`. On the box, `sshd -T | grep -E
   '^(passwordauthentication|permitrootlogin|allowusers)'` must show
   `passwordauthentication no`, `permitrootlogin prohibit-password`.
4. Since the CachyOS base moved 11 commits (package list churn: `-staging`,
   `linux-atm` dropped, `ghostty-terminfo`/`kmscon-terminfo` added, "grub:
   Sync with archiso 92", `profiledef: Remove buildmodes`), do a quick general
   sanity pass too, not just sshd: boots to Hyprland/Noctalia with no
   wallet/welcome prompts, wizard installs cleanly, audio works. Low risk
   (Syntropia's own `drm-module-awaiter-generator` overwrite is unaffected by
   any of these upstream commits — checked this session), but it's new
   upstream content that hasn't touched hardware yet.
5. Once hardware-verified: commit + push both the sshd fix and the build.sh
   git-reset fix (currently uncommitted in the tree), then this is genuinely
   ready for daily-driver use.

### Do-not-repeat (learned the hard way today)
- **The `!` passthrough is fragile with long lines and careless pasting.**
  Keep every `!`-prefixed command to one short physical line. Pasting the
  whole chat block back into the terminal (including the assistant's own
  `●`/`⎿` tool-call lines) feeds that text as shell input and produces
  confusing cascades (`bash: syntax error near unexpected token '('`, a stray
  interactive root shell left open from a truncated `sudo env ... bash
  <script>` line, etc.). Ask for one line, get one line back.
- **`sudo -v` in the user's own terminal does not cache a credential visible
  to this agent's own Bash tool** — it's a different process/session. Any
  command that genuinely needs root must be run by the user via `!`; the
  agent's own Bash tool can only do root-requiring diagnosis by asking the
  user to run `id`/`sudo id` style probes.
- **A vendored git clone that build.sh patches in place (`iso/work/CachyOS-
  Live-ISO`) must be reset before every pull**, or any upstream commit
  touching the same file as a Syntropia patch (here: `packages_desktop.x86_64`)
  aborts the update with a merge-conflict-style error. Now fixed in `build.sh`
  itself (`git reset --hard HEAD` before `git pull --ff-only`).
- Reading an ISO's contents (`xorriso -osirrox on -indev ... -extract`) needs
  no sudo — useful for `iso-boot-config.py check` and hashing
  `arch/x86_64/airootfs.sfs` without touching the build's root-owned work dir.

---

## ⏭️ NEXT SESSION — resume here (written 2026-11-21, end of session)

**Where this left off:** everything is committed, the tree is clean, 437 tests
pass. Three commits (`893e5a0`, `ad32eea`, `9e4e15a`) were **not pushed** —
origin stopped at `50e39d5`.

### Done today (2026-11-21)

**1. Repo made legible to the next agent** (`50e39d5`, +952/−2186)
- The 601-line append-only `NEXT_SESSION.md` was archived verbatim into this
  file and rewritten as *status + next steps*. It had become a log where the
  newest truth sat beside three superseded sections, so an agent could read a
  fixed bug as still-broken (or the reverse) depending on which section it hit
  first. History now answers "why", `NEXT_SESSION.md` answers "what now".
- Deleted `STRUCTURE.md` and `Syntropia-Apps-List.md`: both were repo maps that
  had drifted from `README.md` and from each other. One map, or none.
- Deleted the deprecated `phase1/wizard/` (701-line Go TUI, old shell driver,
  desktop entry) — but only after `git grep` proved the one thing still consumed
  is `phase1/wizard/apps.list`, read by `iso/build.sh:637` and
  `iso/tests/test_ssh_setup.py`. Prove the reference before deleting the file.
- Added `docs/GLOSSARY.md` and `iso/BASE-REFRESH.md`.

**2. sshd hardening proved on real hardware** (`d97ec65`, `2a97e73`)
Installed the 2026-11-19 image on the laptop and verified from the outside, not
from the config file. `/etc/ssh/sshd_config.d/` contains both
`00-syntropia-ssh.conf` and archiso's `10-archiso.conf`; the server offered
`publickey` only and refused password auth outright. The 2026-10-29 no-op is
therefore genuinely dead. `build.sh` also now resets the vendored
`iso/work/CachyOS-Live-ISO` clone before `git pull --ff-only`.
Then `2488ac3..50e39d5` was pushed to `origin/main`.

**3. Installed target no longer inherits the build chroot** (`893e5a0`)
Root cause: `syntropia-install-runner:144` copies the live root with
`rsync -aAX` instead of pacstrapping, so every package in the build chroot
arrives on the target recorded as *explicitly installed*. Hardware evidence
from the same install: `cachyos-calamares-staging` 3.4.2-6 (18.22 MiB,
`Required By: None`) and `mkinitcpio-archiso` present on a finished system, and
`/etc/modules-load.d/zfs.conf` asking for `extramodules/spl.ko.zst` the image
never ships — one failed unit on every boot.
The fix went into the *existing* "purge live-only leftovers" block next to the
`gnome-keyring` purge (runner ~line 358), not into a new function: that block is
already the answer to "what must the target not inherit".
```bash
for pkg in cachyos-calamares-staging mkinitcpio-archiso; do
  arch-chroot "$TARGET" pacman -Rdd --noconfirm "$pkg" 2>/dev/null || true
done
compgen -G "$TARGET/usr/lib/modules/*/extramodules/spl.ko*" >/dev/null \
  || rm -f "$TARGET/etc/modules-load.d/zfs.conf"
```
`compgen -G` is the trick worth remembering: it globs *in the target* and
returns non-zero when nothing matches, so ZFS stays configured for anyone who
actually installs ZFS modules instead of being deleted unconditionally. The
`build.sh` comment claiming the target is pacstrapped was true only of the
Calamares path and was corrected.
Covered by `test_installer_strips_installer_only_packages_from_the_target`
(436 → 437 tests). **Not yet on hardware** — needs the next reinstall.

**4. AUR refreshed** (`ad32eea`)
`release/syntropia-0.1.0.tar` regenerated from `HEAD^{tree}` with the pinned
`--mtime="2026-08-14 12:00:00 UTC"`, plain `.tar`, `phase1/aur` excluded:
14 MB, sha256 `b0b48cb4b8c0909d30b1916a34a0275582c4fd99df37f5aaf3ad908d84adfb1a`
(was `5bb16239…`). All three PKGBUILDs and `.SRCINFO`s updated, `pkgrel=2`.
All three then validated in scratch copies: `syntropia-0.1.0.tar ... Passed`.

### The one thing that blocks AUR users

A PKGBUILD fetches the **release asset**, not the repo. The new hash is
committed, but `github.com/r4-ndm/Project-Syntropia/releases/download/v0.1.0/
syntropia-0.1.0.tar` still serves the *old* bytes, so every AUR build now fails
checksum validation. Upload `release/syntropia-0.1.0.tar` over that asset (a
publish action — ask first) or don't ship the new hash.

### Lessons (2026-11-21)
- **`makepkg -o` failing with `Missing dependencies: -> syntropia-cli` is not a
  hash failure.** It checks runtime deps before extracting, so a clean box
  reports the same error for a perfectly good package. Re-run with
  `makepkg -o --nodeps` to isolate the checksum step, and read the line *above*
  the error before believing it.
- **Bump `pkgrel`, not `pkgver`,** when the source changes but `__version__`
  doesn't: `pkgver` is pinned in lockstep with
  `phase1/cli/syntropia/__init__.py` by the tests, so bumping it silently means
  a broken release.
- **Verify packaging in a scratch copy** (`/tmp/...`), never in `phase1/aur/`:
  `makepkg` drops `src/` and `pkg/` next to the PKGBUILD.
- **A stale status doc is worse than none.** Every claim in `NEXT_SESSION.md`
  that stopped being true ("uncommitted: 4 files", "not hardware-verified") had
  to be hunted down today. Update it in the same commit as the change.

## ⏭️ NEXT SESSION — resume here (written 2026-11-21 late, end of session)

Picked up after a machine crash mid-session. Nothing was lost: the tree was
clean and everything through `647eef2` was already pushed. The crash had
interrupted step 1 of the then-current plan — the ISO rebuild — which had in
fact completed at 18:31 without anyone seeing the result.

### What was proven on hardware (the 18:31 image)
`cachyos-calamares-staging` and `mkinitcpio-archiso` both reported "was not
found" on the installed laptop, and `journalctl -b -p 3 | grep -i spl` came back
empty. That closed the last open Phase 1 item — the installer cleanup patch
(`893e5a0`) had only ever been unit-tested. **Phase 1 is done.**

The full chain was verified rather than assumed: rebuild → extract the squashfs
and byte-compare every installer file against the tree → flash → hash the bytes
back off `/dev/sdd` → install → run the checks.

### The SSH helper was not what it claimed
`syntropia-ssh-setup` was described as "one-command SSH server setup" and could
not be one command. Hardening was gated on `~/.ssh/authorized_keys`, and the
only route it offered to populate that file was `ssh-copy-id` — which must log
in to deposit a key, so password authentication had to be enabled first. The
real flow was: start sshd with passwords on, `ssh-copy-id`, re-run to harden.
On a fresh install that window is worse than it sounds, because archiso's
`10-archiso.conf` survives into the target with `PasswordAuthentication yes`
*and* `PermitRootLogin yes`, and sshd honours the first value it reads.

Three defects came out of reading it properly:

1. **The window was structural, not incidental.** Fixed by taking the client's
   key up front (`--key` / `--key-file` / `--github`), which reorders the run to
   authorize → harden → start. sshd is never reachable while passwords are
   accepted. Keys are validated against the types sshd honours, so a pasted
   fragment or a private key is refused *and sshd is not started* — it fails
   closed. Duplicates match on the key body, ignoring the comment.
2. **Hardening was gated on `~/.ssh/id_ed25519` and returned silently without
   it.** That keypair is for this host connecting *outward* and has nothing to
   do with who may log in here. The silent return meant sshd could be left
   running unhardened with nothing in the output saying so. `authorized_keys` is
   now the only condition.
3. **The wizard's "SSH Setup" pick did nothing at all.** app-wiz4rd runs helpers
   as `helper 2>&1 | tee -a "$INSTALL_LOG"`, so our stdout is a pipe, and the
   sudo re-exec required `[[ -t 0 && -t 1 ]]`. sudo prompts on `/dev/tty`, not
   stdout, so `-t 1` was never the right test — the wizard route skipped
   escalation, ran unprivileged, printed `sudo pacman -S …` instructions,
   generated a passphrase-less keypair nobody asked for, and **exited 0 looking
   like success**. No openssh, no sshd. Gating on stdin alone fixes it.

With (3) fixed the wizard would still have landed on the legacy flow, since it
cannot pass `--key`, so the helper now **prompts** for a key when given none and
stdin is a TTY (Enter skips, junk re-prompts twice, `SYNTROPIA_SSH_NO_PROMPT=1`
disables). Both entry points get one-pass hardening and **app-wiz4rd needed no
release** — the bug and the fix both live in `ssh-setup.sh`, which this repo
owns, even though the wizard is a separate sha-pinned repo.

Tests went 437 → 449. One pins the harden-before-start ordering; one drives the
exact `… | tee` invocation over a pty, because that is the shape that was broken.

### State at end of session
- Latest ISO `d7a5a4978dc0…f56e16` (20:41), rebuilt for the ssh fixes,
  byte-compared against the tree, boot-config checked, and **flashed to the
  stick with the write hashed back**. Not installed — no hardware verification.
- `iso/out/*.iso.verified-2026-11-21` (`55e1cf2944b7…cdd352`) is the best
  known-good fallback: the image that installed cleanly and passed both checks.
- Everything committed and pushed; tree clean.

### Lessons (2026-11-21 late)
- **"Verified" must name the artifact, not the feature.** `build.sh` re-pulls
  the CachyOS base on every run, so a rebuild is a genuinely new image, not the
  proven one plus a patch. The 20:41 ISO inherits nothing from the 18:31 one.
- **Preserve the proven image before rebuilding.** The build overwrites
  `iso/out/syntropia-2026.08.12-x86_64.iso` in place; today's hardware-verified
  image would have been destroyed. `cp --reflink=auto` is free on btrfs.
- **A helper that exits 0 can still have done nothing.** The wizard's SSH pick
  printed instructions and succeeded for weeks. Assert on the *effects*
  (openssh installed, sshd enabled), never on the exit status.
- **`-t 1` is almost always the wrong gate.** Terminal-detection on *stdout*
  breaks every caller that pipes or logs you. Gate on stdin, or on `/dev/tty`.
- **Tests can pass for the wrong reason.** The first key prompt read `/dev/tty`,
  so under pytest it hit a different terminal, returned EOF and skipped — green
  without exercising anything. Reading stdin made it deterministic and
  immediately exposed an existing pty test hanging on the new prompt.
