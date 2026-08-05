# 😈 Phase 1: Syntropia Core Master Plan

**Goal**: Deliver an installable, rebranded CachyOS-based operating system ("Syntropia OS") with native Wine/yabridge VST3 plugin management driven by a simple CLI (`syntropia install <brew>`).

**Scope Strategy**: Phase 1 ships **without Hermes**, without safety gates, and without self-mutating AI daemons. It focuses entirely on developer/musician UX, system identity, and smooth Windows audio plugin execution on CachyOS.

---

## 🧬 The Bootstrap & Development Strategy

Phase 1 prioritizes rapid local development using **`syntropia transform`** before building ISO images:

```
┌───────────────────────────────────────────────────────────┐
│ 1. Rapid Local Dev via `syntropia transform`              │
│    (In-place branding, configs, wine & yabridge setup)    │
└─────────────────────────────┬─────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────┐
│ 2. Test DAWs & VST3 Brews (Ableton, FL Studio, Serum)     │
└─────────────────────────────┬─────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────┐
│ 3. Bake verified transform configs into Seed ISO v0.1     │
│    (Using Archiso / CachyOS build profiles)               │
└─────────────────────────────┬─────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────┐
│ 4. Install Seed ISO on target hardware & self-host        │
└─────────────────────────────┴─────────────────────────────┘
```

---

## 📦 Core Deliverables

### 1. Transformation Script (PRIORITY #1)
* **`syntropia transform`**: Safe, non-destructive, idempotent script that turns any running CachyOS system into Syntropia OS:
  - Applies `/etc/os-release` & `/usr/share/syntropia/logo.txt`.
  - Configures shell prompt `😈 \u@\h \W $ ` in `~/.bashrc` & `~/.zshrc`.
  - Installs audio packages (`wine-staging`, `winetricks`, `yabridge`, `pipewire`, `pipewire-pulse`, `wireplumber`).
  - Sets up directories (`~/.config/syntropia/brews`, `~/.local/share/syntropia/prefixes`, `~/.vst3/Syntropia`).
  - Deploys `/usr/local/bin/syntropia` CLI executable.
  - Applies PipeWire low-latency quantum configuration (`~/.config/pipewire/pipewire.conf.d/99-syntropia.conf`).

### 2. Visual Rebranding Kit
* **`/etc/os-release`**: Custom OS metadata identifying system as Syntropia OS (powered by CachyOS).
* **Fastfetch ASCII Logo**: Syntropia infinity logo banner (`syntropia fetch` / terminal launch).
* **Terminal Shell Prompt**: `😈 user@host` prompt prefix.
* **GRUB Theme & Plymouth Splash**: Dark cosmic GRUB bootloader theme and animated boot splash.

### 3. The `.brew` System (Replacing Recipes)
Application and plugin manifests called **brews** (`.brew` TOML format) targeting primary DAWs and VST3 plugins:
* **Target DAWs**: Ableton Live 12 (`ableton-live-12.brew`), FL Studio (`fl-studio.brew`).
* **Target VSTs**: Xfer Serum (`serum.brew`), Vital Wavetable Synth (`vital.brew`).
* **Nidavellir Registry**: Local directory index stored at `~/.config/syntropia/brews/`.

### 4. Syntropia CLI & VST3 Engine
* **`syntropia install <brew>`**: Parses `.brew` specs, provisions isolated Wine prefixes, applies DLL overrides (`d2d1 = "disabled"`, `gdiplus = "native"`), runs `winetricks`, registers VST3 DLLs with `yabridgectl`, and triggers automatic sync to `~/.vst3/Syntropia`.

### 5. ISO & Distribution Helper
* **`syntropia download-iso`**: CLI command to discover, download, verify checksums, and flash official Syntropia ISO images.
* **Seed ISO v0.1 Profile**: CachyOS `archiso` profile pre-packaged with Syntropia branding and audio environment.

---

## 🍺 `.brew` Specification Schema

```toml
# Example: brews/serum.brew
[brew]
name = "Xfer Serum VST3"
version = "1.368"
category = "vst3_synth"
maintainer = "Syntropia Team <hello@project-syntropia.io>"

[wine]
version = "cachyos-wine"
prefix = "~/.local/share/syntropia/prefixes/serum"
arch = "win64"

[wine.overrides]
d2d1 = "disabled"   # Bypasses Wine Direct2D graphics bug (Serum black screen fix)
gdiplus = "native"  # Uses native GDI+ for text and knob anti-aliasing

[winetricks]
packages = ["gdiplus", "corefonts", "vcrun2022"]

[yabridge]
enabled = true
plugin_dirs = ["~/.vst3/Syntropia"]

[environment]
WINEDLLOVERRIDES = "winemenubuilder.exe=d"
WINE_AUDIO_BACKGROUND = "1"
LANG = "en_US.UTF-8"

[install]
commands = [
  "wine /tmp/Serum_Setup.exe /S",
  "cp -r '$WINEPREFIX/drive_c/Program Files/Common Files/VST3/Serum.vst3' ~/.vst3/Syntropia/"
]
```

---

## 🗓️ Phase 1 Roadmap Timeline

| Week | Focus Area | Key Targets |
| :--- | :--- | :--- |
| **Week 1** | `syntropia transform` & Branding | Implement `syntropia transform` script, `/etc/os-release`, Fastfetch ASCII logo, shell prompt (`😈`), PipeWire 128 quantum config, and CLI binary installation. |
| **Week 2** | `.brew` Parser & VST Engine | Write `src/syntropia/brew.py`, build `syntropia install <brew>` with `wine.overrides` and `winetricks` support, automate Wine prefix initialization and `yabridgectl sync`. |
| **Week 3** | Target DAW & VST Brews | Test and finalize `ableton-live-12.brew`, `fl-studio.brew`, `serum.brew`, and `vital.brew` on local transformed CachyOS system. |
| **Week 4** | Seed ISO Assembly & Bootstrap | Package verified `transform` configs into Archiso profile, build `cachyos-syntropia-v0.1.iso`, and perform clean install. |

## 🤖 Git Butler Helper (Phase 1)

- **Purpose**: Simplify Git operations for Syntropia development.
- **Script**: `~/bin/syn` Bash script that provides `syn push "msg"`, `syn pull`, `syn status`, `syn sync`, `syn undo`.
- **Hermes Skill**: `~/.hermes/skills/git-butler.md` enables voice commands like "Hermes, push my changes".
- **Tasks**:
  - [ ] Create `syn` script in `~/bin` and make executable.
  - [ ] Add `~/bin` to PATH.
  - [ ] Write Hermes skill file.
  - [ ] Test push, pull, sync, undo commands.

---

## 🏗️ Repository Structure (Phase 1)

```
syntropia/
├── install-syntropia.sh       # One-line installer
├── cli.py                     # Main CLI entry point
├── src/
│   └── syntropia/
│       ├── __init__.py
│       ├── cli.py            # CLI command implementations
│       ├── brew.py           # Brew parser and validator
│       ├── transform.py      # System transformation logic
│       ├── wine_helper.py    # Wine/yabridge automation
│       └���─ services.py       # Systemd service management
├── brews/
│   ├── vlc.brew
│   ├── ableton.brew
│   ├── serum.brew
│   └── template.brew
├── systemd/
│   ├── syntropia.service
│   └── syntropia-reaper.service
├── skills/
│   └── git-butler.md         # Hermes skill (Phase 2 integration)
├── bin/
│   └── syn                   # Git helper script
├── iso-builder/
│   └── archiso-profile/      # Seed ISO configuration
└── docs/
    └── brew-spec.md          # Detailed brew specification
```

---

## 🎯 Success Criteria

### Minimum Viable Product (MVP)
- [ ] `syntropia transform` works on clean CachyOS installation
- [ ] `syntropia install serum.brew` successfully installs Serum VST3
- [ ] Serum runs in tested DAW with ≤10ms latency
- [ ] Seed ISO boots and self-hosts successfully
- [ ] Git Butler (`syn` script) functional for development workflow

### Quality Gates
- **Performance**: Audio latency ≤10ms round-trip
- **Reliability**: Transform script idempotent and safe
- **Usability**: CLI intuitive and well-documented
- **Compatibility**: Works on target hardware configurations

### Exit to Phase 2
Phase 1 must be **fully shipped and stable** before Phase 2 begins:
- [ ] AUR package real and installable (`makepkg -si` succeeds)
- [ ] Real users have successfully used it
- [ ] No critical bugs in core functionality
- [ ] Documentation complete and usable

---

**Theme**: *"First, we build the womb. Then, we grow the god."*