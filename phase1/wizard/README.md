# 😈 Syntropia Apps Wizard

A first-boot "pick your favorites" installer: **one grouped checkbox dialog**
with category sections (Chat, Browser, DAW, AI, Terminal, CLI, Video, Wallet, Web)
that installs whatever you check via **paru** — which handles both
official-repo and AUR packages — with live output in a terminal window. All
picks across every category install in one `paru -S` transaction.

It's intentionally a *wrapper around `paru`*: no baked packages, no ISO
rebuilds, no Calamares surgery. The app list is just a text file, so adding
an app is a one-line edit.

## Why this exists (and why it's not something else)

| Alternative | Why not |
|---|---|
| Calamares checkbox screen (netinstall) | Only installs pacman-repo packages; AUR names don't resolve; custom UI would need C++/Qt |
| Baked local repo in the ISO | Works, but every new app means rebuilding packages + ISO; versions pinned to bake date |
| CachyOS `packageinstaller` | Great general tool, but its curated list comes from *their* GitHub and it only does `pacman -S` (no AUR) |
| "Paste this paru command" | Works, but paru isn't guaranteed on a fresh install and a terminal-first ask is weak UX for new users |

The wizard's dependencies are the **dialog tool**, **paru** (installs;
bootstrapped automatically if missing), and a terminal emulator. Dialog
tiers, best first (auto-detected, override with `--dialog`):

1. **Qt grid dialog** (`syntropia-apps-dialog.py`, PySide6) — a native Qt
   window styled like **Windows 98** (gray canvas, beveled 3D borders) with
   a **4-column checkbox grid per category**; each category in its own
   outlined group box, padded with empty placeholder cells so every
   category fills a full row and the columns stay aligned. Cells are
   **sunken when checked, raised when unchecked**, and play a synthesized
   click sound when checked (no audio asset needed — the WAV is generated
   at first use). Needs `python-pyside6`.
2. **kdialog** (the `kdialog` package — it moved out of `kde-cli-tools` in
   KF6) — one grouped dialog with category separator rows; renders as a
   **native Plasma window** on the default CachyOS desktop
3. **zenity** — GTK fallback for non-KDE desktops (Cinnamon, GNOME)

On non-Plasma desktops the wizard forces the **Breeze widget style** for
Qt/kdialog (`QT_STYLE_OVERRIDE=breeze`), because GTK platform themes paint
checklist checkboxes invisibly. On a Plasma session the native style is
already active and nothing is overridden.

`base-devel` is guaranteed in the target base install, so AUR builds work on
first boot. When shipping, declare `kdialog` (or `zenity`) + `paru` as
dependencies — neither is guaranteed on a stock install.

## The catalog: `apps.list`

One app per line, pipe-separated:

```
category|display name|package|short description
```

- `package` is a pacman repo **or** AUR package name — paru resolves either.
  CLI apps work exactly the same (e.g. ripgrep, fzf — or Freebuff, a CLI
  agent under AI): paru installs them, no launcher needed.
- **Web apps:** if `package` is an `https://` URL, the wizard creates a
  PWA-style desktop launcher (dedicated window, taskbar icon) that opens the
  site — no `paru` needed. It uses Brave/Chromium `--app=URL` if present,
  else Firefox. Launchers land in `~/.local/share/applications/` as
  `syntropia-<slug>.desktop`.
- **Category = a section.** One dialog shows every category in file order,
  with plain `— Chat —` separator rows between the apps — no window
  respawn between categories, everything installs together. (Earlier
  per-category dialogs were dropped for this smoother single dialog.)
- Prefer binary / `.deb`-repackage AUR packages so installs stay fast.
- The wizard loads the catalog in this order:
  1. `--config FILE`
  2. `~/.config/syntropia/apps.list` — **user override** (copy + edit to customize)
  3. `/etc/syntropia/apps.list` — system default
  4. `apps.list` next to the script (bundled fallback)

## Usage

```bash
./syntropia-apps-wizard.sh              # run the dialog
./syntropia-apps-wizard.sh --check      # sanity check (catalog + toolchain)
./syntropia-apps-wizard.sh --list       # print the resolved catalog
./syntropia-apps-wizard.sh --dialog kdialog  # force the dialog tool
./syntropia-apps-wizard.sh --setup      # one-command setup (see below)
./syntropia-apps-wizard.sh --install-autostart   # one-shot on next login
./syntropia-apps-wizard.sh --remove-autostart    # undo the above
```

### `--setup` — the one-command onboarding

```bash
./syntropia-apps-wizard.sh --setup
```

1. Seeds `~/.config/syntropia/apps.list` from the default catalog (if you
   don't already have one) — this is **your editable copy**.
2. Installs the one-shot autostart entry.
3. Prints where to edit and how to re-show the dialog.

After setup, customizing the wizard is just editing `~/.config/syntropia/apps.list`:

```
Chat|Telegram|telegram-desktop|Messaging app
DAW|Bitwig Studio|bitwig-studio|Digital audio workstation
```

One line per app; `package` may be a repo **or** AUR package (paru handles
both). The wizard prefers your copy over the system default automatically.

`--install-autostart` installs a desktop entry into
`~/.config/autostart/` that runs the wizard `--once` on next login.
`--once` self-disables after use (a completion marker is written to
`~/.config/syntropia/apps-wizard.done`; delete it to run again).

## Installing apps

Checked apps install with a single `paru -S --noconfirm <packages>` in a
terminal window (konsole → gnome-terminal → xfce4-terminal → kitty →
alacritty → xterm, first one found, or `$TERMINAL`). paru is installed
first if missing (`pkexec pacman -S paru`).

## Notes

- Windows apps (Ableton, FL Studio) deliberately live **outside** this
  wizard — they need Wine prefixes, which is the `.brew` engine's job
  (`syntropia install ableton-live-12`). This wizard is for native apps.
- Cancelling the dialog in `--once` mode writes the done-marker too, so it
  won't nag every login.
- **Shipped in the ISO**: `iso/build.sh` phase 2 copies the wizard (script +
  `apps.list` + `syntropia-apps-dialog.py`) into the rootfs `/etc/syntropia/`
  and installs a first-boot autostart entry (`/etc/xdg/autostart/`), so fresh
  installs get the dialog at first login. The transform path (installed
  systems) is the same files, no changes needed.
- **Dialog dependency**: the first-boot dialog needs `python-pyside6` (Qt
  grid), `kdialog`, or `zenity` present on the installed system — none is
  guaranteed, so until a package dependency is declared the wizard degrades
  to whichever exists (see the open "Package as dependency-clean unit" task).
