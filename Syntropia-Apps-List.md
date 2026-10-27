# 😈 Syntropia — App List Worksheet

Use this to build the **final** app list for the first-boot apps wizard.
Every app is **one line**, pipe-separated:

```
category|display name|package|description
```

Copy the lines you want into the repo file:
`~/Desktop/Project-Syntropia/phase1/wizard/apps.list`

(Or on any installed box: run `syntropia-apps-wizard.sh --setup`, then edit
`~/.config/syntropia/apps.list` — your copy always wins.)

---

## The rules

- **package** = a pacman repo **or** AUR package name — paru installs either.
- **CLI apps** work exactly like GUI apps — same line format, paru installs
  them (e.g. `CLI|ripgrep|ripgrep|Fast grep`).
- **Web apps** = put an `https://` URL as the package — the wizard creates a
  PWA-style launcher instead of installing (e.g. `Web|Gmail|https://mail.google.com|Email`).
- Prefer **official-repo** packages (instant). AUR `-bin` / `.deb` repackages
  are fine and fast. Source-compiling AUR packages slow the wizard down.
- **Category order = section order** in the dialog. New category = new name
  on the line.
- Check your list: `~/Desktop/Project-Syntropia/phase1/wizard/syntropia-apps-wizard.sh --check`

---

## Current categories & apps (26)

### Chat
```
Chat|Telegram|telegram-desktop|Messaging app
Chat|Discord|discord|Voice, video and text chat
```
Add yours:
```

```

### Browser
```
Browser|Brave|brave-bin|Ad-blocking Chromium browser
```
Add yours (CachyOS already ships Firefox):
```

```

### DAW
```
DAW|Bitwig Studio|bitwig-studio|Digital audio workstation
DAW|Reaper|reaper|Digital audio workstation (native Linux)
```
Add yours:
```

```

### AI
```
AI|Kiro IDE|kiro-ide|Agentic AI code editor
AI|Freebuff|freebuff-bin|AI coding agent for the terminal
AI|Ollama|ollama|Run local LLMs
```
Add yours:
```

```

### Terminal
```
Terminal|Wezterm|wezterm|GPU-accelerated terminal emulator
```
Add yours:
```

```

### CLI
```
CLI|ripgrep|ripgrep|Blazingly fast grep
CLI|fzf|fzf|Fuzzy finder for the shell
CLI|zoxide|zoxide|Smarter cd
CLI|eza|eza|Modern ls replacement
CLI|bat|bat|cat with syntax highlighting
CLI|yazi|yazi|Terminal file manager
CLI|btop|btop|System monitor
CLI|tmux|tmux|Terminal multiplexer
```
Add yours (candidates: `helix`, `neovim`, `jq`, `lazygit`, `starship`, `atuin`):
```

```

### Video
```
Video|mpv|mpv|Minimal video player
Video|OBS Studio|obs-studio|Screen recording and streaming
```
Add yours:
```

```

### Wallet
```
Wallet|Electrum|electrum|Bitcoin wallet
```
Add yours:
```

```

### Web (URL = launcher, opens in its own window)
```
Web|WhatsApp|https://web.whatsapp.com|WhatsApp Web
Web|YouTube Music|https://music.youtube.com|Music streaming
Web|Spotify|https://open.spotify.com|Music streaming
Web|Notion|https://www.notion.so|Notes and docs
Web|Figma|https://www.figma.com|Design tool
Web|Gmail|https://mail.google.com|Email
```
Add yours (e.g. X, Instagram, Reddit, Canva, Google Drive):
```

```

---

## Verify-a-name cheat sheet

`curl -s "https://archlinux.org/packages/search/json/?name=<pkg>"` → official repo
`curl -s "https://aur.archlinux.org/rpc/v5/info?arg[]=<pkg>"` → AUR

Then run `syntropia-apps-wizard.sh --check` to see the whole list load.
