# 😈 Syntropia Apps Wizard

A first-boot "pick your favorites" installer: a series of checkbox dialogs —
one per category (Chat, Browser, DAW, AI, Terminal, Video, Wallet…) — that
install whatever you check via **paru**, which handles both official-repo and
AUR packages, with live output in a terminal window. All picks across every
category install in one `paru -S` transaction.

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
bootstrapped automatically if missing), and a terminal emulator:

- **kdialog** (the `kdialog` package — it moved out of `kde-cli-tools` in
  KF6) — preferred; renders as a **native Plasma window** with the
  CachyOS/Breeze theme on the default CachyOS desktop
- **zenity** — GTK fallback for non-KDE desktops (Cinnamon, GNOME)
- override with `--dialog kdialog|zenity`

On non-Plasma desktops the wizard forces the **Breeze widget style** for the
kdialog call (`QT_STYLE_OVERRIDE=breeze`), because GTK platform themes paint
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
- **Web apps:** if `package` is an `https://` URL, the wizard creates a
  PWA-style desktop launcher (dedicated window, taskbar icon) that opens the
  site — no `paru` needed. It uses Brave/Chromium `--app=URL` if present,
  else Firefox. Launchers land in `~/.local/share/applications/` as
  `syntropia-<slug>.desktop`.
- **Category = one dialog.** The wizard walks the categories in file order
  and shows a checklist per category; cancelling a category skips just that
  one, so the walk always finishes.
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
- Ship points: add this wizard (script + `apps.list` + desktop entry) to the
  ISO's `/etc/syntropia/` or run `--install-autostart` from the transform —
  same files, no changes needed.
