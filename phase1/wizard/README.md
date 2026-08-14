# 😈 Syntropia Apps Wizard

A first-boot "pick your favorites" installer: one grouped checkbox dialog
(Syntropia, Chat, Browser, DAW, Audio, AI, Terminal, CLI, Video, Graphics,
Wallet) that installs whatever you check via **paru** — which handles both
official-repo and AUR packages — with live output in the terminal. All picks
install in one `paru -S` transaction.

It's intentionally a *wrapper around `paru`*: no baked packages, no ISO
rebuilds, no Calamares surgery. The app list is just a text file, so adding
an app is a one-line edit.

## The UI

The **only** frontend is the TUI (`dialog/syntropia-apps-tui`, source
`dialog/main.go`) — a Bubble Tea (Charm ecosystem) glamour UI: dark
purple/pink theme, gradient banner, category groups, keyboard-first checkbox
grid (`↑/↓`/`jk` move, `←/→` between columns, `space` toggle, `a` select
all, `n` clear, `space` on the DONE row arms it, `enter` installs, `esc`
cancels). It's a **static binary with zero runtime dependencies**
(`CGO_ENABLED=0`). It runs in a terminal — the same place the install output
lands — and when launched without a TTY (e.g. the first-boot autostart entry)
the wizard relaunches it inside a terminal window itself.

`iso/build.sh` step 3.6 builds it and ships it prebuilt into
`/etc/syntropia/dialog/`. From a bare repo checkout the wizard builds it on
demand when `go` is present.

**paru is not on a stock CachyOS install** — the wizard bootstraps it itself
on first use (`sudo pacman -S paru`). The ISO stays stock CachyOS; nothing is
preinstalled, apps are the user's first-boot picks.

## The catalog: `apps.list`

One app per line, pipe-separated:

```
category|display name|package|short description
```

- `package` is a pacman repo **or** AUR package name — paru resolves either.
  CLI apps work the same (ripgrep, fzf, Freebuff…): paru installs them, no
  launcher needed.
- **Web apps:** if `package` is an `https://` URL, the wizard creates a
  PWA-style desktop launcher (dedicated window, taskbar icon) — no `paru`.
  Brave/Chromium `--app=URL` if present, else Firefox. Launchers land in
  `~/.local/share/applications/` as `syntropia-<slug>.desktop`.
- **Category = a section**, shown in file order in one grid.
- Resolution order:
  1. `--config FILE`
  2. `~/.config/syntropia/apps.list` — **user override** (copy + edit to customize)
  3. `/etc/syntropia/apps.list` — system default
  4. `apps.list` next to the script (bundled fallback)

## Usage

```bash
./syntropia-apps-wizard.sh            # run the dialog
./syntropia-apps-wizard.sh --once     # run, but exit quietly if already done
./syntropia-apps-wizard.sh --config FILE   # use a specific catalog
./syntropia-apps-wizard.sh --install-autostart   # one-shot on next login
./syntropia-apps-wizard.sh --remove-autostart    # undo the above
```

`--install-autostart` writes a desktop entry to `~/.config/autostart/` that
runs the wizard `--once` on next login. `--once` self-disables after a
**successful** install (completion marker at
`~/.config/syntropia/apps-wizard.done`; delete it to run again).

## Installing apps

Checked apps install with a single `paru -S --noconfirm <packages>`, inline
in the same terminal with live output. Web-app picks create their launchers
after the package install.

## Notes

- **Syntropia's own packages** are the first category: `syntropia` (the
  rebrand tooling — `transform`/`update`) and `syntropia-brews` (the optional
  Windows-app helper). They're plain AUR packages, so a user who wants
  Syntropia *without* Wine just leaves Brews unchecked; `syntropia-cli` is a
  dependency of both and is pulled automatically.
- Windows apps (Ableton, FL Studio) deliberately live **outside** this wizard
  — they need Wine prefixes, which is the `.brew` engine's job
  (`syntropia install ableton-live-12`). This wizard is for native apps.
- **Cancelling does not skip forever** — cancelling (or selecting nothing)
  shows a "run it later" note and writes *no* marker, so the wizard can be
  re-run any time. Only a completed install marks it done.
- **Shipped in the ISO**: `iso/build.sh` phase 2 copies the wizard (script +
  `apps.list` + the `dialog/` TUI source and prebuilt binary) into
  `/etc/syntropia/` and installs a first-boot autostart entry
  (`/etc/xdg/autostart/`), so fresh installs get the dialog at first login.
