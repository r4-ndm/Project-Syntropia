# 😈 Syntropia Apps Catalog (`APPS-LIST.md`)

This document is the finalized master specification for all applications curated by the Final Boss (L5) for the **Syntropia First-Boot App Wiz4rd** (`apps.list`).

---

## 📊 Summary

- **Total Curated Applications**: 51
- **Categories**: 15
- **Package Sources**:
  - **Arch / CachyOS Official Repos**: Fast native binaries
  - **AUR (Arch User Repository)**: Curated tools (e.g. `brave-bin`, `bitwig-studio`, `kiro-ide`, `lm-studio-bin`, `antigravity`)
  - **Dedicated Web Apps (PWAs)**: URL launchers (e.g. ZKX Wallet)
  - **Syntropia Tooling**: `syntropia` and `syntropia-brews` (Wine/VST3 bridging)

---

## 📦 Curated Application Catalog

### 1. Syntropia Core Tooling
| Display Name | Package / URL | Source | Description |
|---|---|---|---|
| **Syntropia** | `syntropia` | AUR | Rebrand tooling — `syntropia transform` & `syntropia update` |
| **Syntropia Brews** | `syntropia-brews` | AUR | Install Windows DAWs & VST3 plugins via Wine + yabridge |

### 2. Chat & Communication
| Display Name | Package / URL | Source | Description |
|---|---|---|---|
| **Telegram** | `telegram-desktop` | Repo | Fast and secure desktop messaging client |
| **Discord** | `discord` | Repo | All-in-one voice, video, and text communication |
| **Element** | `element-desktop` | Repo | End-to-end encrypted Matrix communication client |
| **Keet** | `keet-bin` | AUR | Peer-to-peer encrypted messaging and video |

### 3. Web Browsers *(Firefox is pre-installed in CachyOS base)*
| Display Name | Package / URL | Source | Description |
|---|---|---|---|
| **Brave** | `brave-bin` | AUR | Privacy-focused Chromium browser with ad/tracker blocking |
| **Chromium** | `chromium` | Repo | Fast open-source browser engine |

### 4. Digital Audio Workstations (DAW)
| Display Name | Package / URL | Source | Description |
|---|---|---|---|
| **Bitwig Studio** | `bitwig-studio` | AUR | Modern modular Digital Audio Workstation |

### 5. Audio Production & Editing
| Display Name | Package / URL | Source | Description |
|---|---|---|---|
| **Audacity** | `audacity` | Repo | Multi-track audio recorder and waveform editor |
| **Ocenaudio** | `ocenaudio-bin` | AUR | Fast and functional audio waveform editor |

### 6. AI, LLMs & Code Intelligence
| Display Name | Package / URL | Source | Description |
|---|---|---|---|
| **Kiro IDE** | `kiro-ide` | AUR | Spec-driven agentic AI code editor |
| **Antigravity** | `antigravity` | AUR | Google Antigravity multi-agent platform |
| **Freebuff** | `freebuff-bin` | AUR | Terminal AI coding agent |
| **LM Studio** | `lm-studio-bin` | AUR | Discover, download, and run local LLMs locally |
| **Ollama** | `ollama` | Repo | Background daemon for running local LLMs |
| **Crush** | `crush-bin` | AUR | AI terminal coding assistant |
| **Gemini CLI** | `gemini-cli` | Repo | Google Gemini CLI assistant for terminal workflows |

### 7. Terminal Emulators
| Display Name | Package / URL | Source | Description |
|---|---|---|---|
| **Wezterm** | `wezterm` | Repo | GPU-accelerated terminal emulator with Lua configuration |
| **Alacritty** | `alacritty` | Repo | Lightweight, high-performance GPU-accelerated terminal |
| **Ghostty** | `ghostty` | Repo | Fast, native, feature-rich GPU terminal emulator |

### 8. CLI Power Utilities
| Display Name | Package / URL | Source | Description |
|---|---|---|---|
| **ripgrep** | `ripgrep` | Repo | Ultra-fast regex search tool (`rg`) |
| **fzf** | `fzf` | Repo | General-purpose command-line fuzzy finder |
| **zoxide** | `zoxide` | Repo | Smarter directory navigation based on frecency (`z`) |
| **eza** | `eza` | Repo | Modern, colorized replacement for `ls` |
| **bat** | `bat` | Repo | Cat clone with syntax highlighting and git integration |
| **yazi** | `yazi` | Repo | Blazing fast terminal file manager with image previews |
| **btop** | `btop` | Repo | Resource monitor showing CPU, memory, disks, and processes |
| **duf** | `duf` | Repo | Better `df` alternative for disk usage overview |
| **tmux** | `tmux` | Repo | Terminal multiplexer with sessions, windows, and panes |
| **glances** | `glances` | Repo | Comprehensive system monitoring tool in Python/curses |
| **7-Zip** | `7zip` | Repo | High compression file archiver (CLI) |
| **herdr** | `herdr` | Repo | Terminal workspace manager for AI coding agents |
| **torlnk** | `torlink` | AUR | Sleek terminal-native torrent finder and downloader |

### 9. Development & Virtualization
| Display Name | Package / URL | Source | Description |
|---|---|---|---|
| **Neovim** | `neovim` | Repo | Hyperextensible Vim-based text editor |
| **Micro** | `micro` | Repo | Modern terminal text editor with standard keybindings |
| **Gedit** | `gedit` | Repo | Simple GNOME desktop text editor |
| **Meld** | `meld` | Repo | Visual diff and three-way merge tool |
| **Virt-Manager** | `virt-manager` | Repo | Desktop GUI for KVM / QEMU virtual machines |
| **Docker** | `docker` | Repo | Container runtime platform |
| **GitHub CLI** | `github-cli` | Repo | GitHub command-line interface (`gh`) |

### 10. Video & Streaming
| Display Name | Package / URL | Source | Description |
|---|---|---|---|
| **MPV** | `mpv` | Repo | Minimalist, high-performance media player |
| **VLC** | `vlc` | Repo | Versatile multimedia player supporting all codecs |
| **OBS Studio** | `obs-studio` | Repo | Professional screen recording and live streaming studio |
| **Video Downloader** | `video-downloader` | Repo | GTK graphical video downloader for YouTube and video sites |
| **Grayjay** | `grayjay-bin` | AUR | Universal extensible media player and streaming hub |

### 11. Graphics & Design
| Display Name | Package / URL | Source | Description |
|---|---|---|---|
| **GIMP** | `gimp` | Repo | GNU Image Manipulation Program (Photoshop alternative) |
| **Flameshot** | `flameshot` | Repo | Advanced screenshot utility with in-app annotations |
| **Simple Scan** | `simple-scan` | Repo | Document and image scanning utility |

### 12. Privacy & Security
| Display Name | Package / URL | Source | Description |
|---|---|---|---|
| **Mysterium VPN** | `mysterium-vpn-desktop-bin` | AUR | Decentralized P2P VPN client |

### 13. System Utilities & File Management
| Display Name | Package / URL | Source | Description |
|---|---|---|---|
| **Thunar** | `thunar` | Repo | Lightweight desktop file manager |
| **Engrampa** | `engrampa` | Repo | Archive manager GUI (ZIP, 7z, TAR, RAR) |
| **qBittorrent** | `qbittorrent` | Repo | Feature-rich BitTorrent client |
| **Btrfs Assistant** | `btrfs-assistant` | Repo | GUI for managing Btrfs subvolumes and Snapper snapshots |
| **Sticky Notes** | `sticky` | Repo | Desktop sticky note manager |

### 14. Cryptocurrency Wallets
| Display Name | Package / URL | Source | Description |
|---|---|---|---|
| **Electrum** | `electrum` | Repo | Lightweight Bitcoin wallet |
| **ZKX Wallet** | `https://app.zkxwallet.com/#/unlock` | Web App | Web3 decentralized wallet (dedicated window) |

### 15. Internet & Email
| Display Name | Package / URL | Source | Description |
|---|---|---|---|
| **Thunderbird** | `thunderbird` | Repo | Mozilla Thunderbird standalone email and news client |
