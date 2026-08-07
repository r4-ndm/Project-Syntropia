# 😈 Phase 1: Syntropia Core Master Plan

**Goal**: Ship `syntropia` as an **AUR package** that transforms a stock CachyOS install into Syntropia OS — rebranded, audio-optimised, and ready to install Windows VST3 plugins with one command (`syntropia install <brew>`).

**Delivery model (package-first)**: User installs stock CachyOS → `yay -S syntropia` (or `curl | bash`) → `syntropia transform --yes` → done. The AUR package is the install mechanism; the Seed ISO is a future polish item (built and tested, but deferred past Phase 1).

**Scope Strategy**: Phase 1 ships **without Hermes**, without safety gates, and without self-mutating AI daemons. It focuses entirely on developer/musician UX, system identity, and smooth Windows audio plugin execution on CachyOS.

---

## 🧬 The Bootstrap & Development Strategy

Phase 1 follows a **package-first** strategy — the AUR package is the delivery vehicle, `syntropia transform` is the application mechanism, and the ISO is a sidelined future polish:

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
│ 3. Ship via AUR — `yay -S syntropia`                     │
│    (PKGBUILD → makepkg → `syntropia transform --yes`)     │
└─────────────────────────────┬─────────────────────────────┘
                              │
                              ▼
┌───────────────────────────────────────────────────────────┐
│ 4. Users install stock CachyOS, one command → Syntropia   │
└─────────────────────────────┴─────────────────────────────┘

(Sidelined) Seed ISO — mkarchiso pipeline working & tested,
            deferred to Phase 2 as a polish deliverable.
```

---

## 📦 Core Deliverables

### 1. Transformation Script (PRIORITY #1)
* **`syntropia transform`**: Safe, non-destructive, idempotent script that turns any running CachyOS system into Syntropia OS:
  - Applies `/etc/os-release` & `/usr/share/syntropia/logo.txt`.
  - Configures shell prompt `😈 \u@\h \W $ ` in `~/.bashrc` & `~/.zshrc` (fish support: pending).
  - Installs audio packages (`wine-staging`, `winetricks`, `yabridge`, `yabridgectl`, `pipewire`, `pipewire-pulse`, `wireplumber`).
  - Sets up directories (`~/.config/syntropia/brews`, `~/.local/share/syntropia/prefixes`, `~/.vst3/Syntropia`).
  - Deploys `/usr/local/bin/syntropia` CLI executable.
  - Applies PipeWire low-latency quantum configuration (`~/.config/pipewire/pipewire.conf.d/99-syntropia.conf`).

### 2. Visual Rebranding Kit
* **`/etc/os-release`**: Custom OS metadata identifying system as Syntropia OS (powered by CachyOS).
* **Fastfetch ASCII Logo**: Triangle logo banner at terminal launch via fastfetch config.
* **Terminal Shell Prompt**: `😈 user@host` prompt prefix (bash/zsh; fish uses fastfetch greeting instead).
* **GRUB Theme**: Dark cosmic GRUB bootloader splash (`splash.png` → `/boot/grub/splash.png`).
* **Plymouth Boot Animation**: Animated boot splash — frames exist but are **stock CachyOS**, need custom Syntropia animation.
* **Wallpaper**: Syntropia-themed desktop background.

### 3. The `.brew` System (AUR-style package manager for Windows VSTs)
Application and plugin manifests called **brews** (`.brew` TOML format). The `.brew` is the analog of a PKGBUILD — it describes how to install a Windows app through Wine.

* **Target DAWs**: Ableton Live 12 (`ableton-live-12.brew`), FL Studio (`fl-studio.brew`).
* **Target VSTs**: Xfer Serum (`serum.brew`), Vital Wavetable Synth (`vital.brew`), Surge XT (`surge.brew`).
* **Nidavellir Registry — AUR-style**: A `.brew` manifest is the analog of a PKGBUILD. The **local registry** at `~/.config/syntropia/brews/` is your personal tree — a git-able clone of the shared registry. The **shared registry** is a public GitHub repo of `.brew` files (the community "AUR") that anyone can submit to via PR.
  - `syntropia save <file>.brew` — validate a manifest and copy it into the local registry (saving again overwrites = update).
  - `syntropia install <name>` — resolves bare names against the registry, AUR-style (`syntropia install surge`), or a file path.
  - `syntropia remove <name>` / `list-brews` / `search` / `info` — the rest of the read/write surface.
  - `syntropia submit <name>` — pushes a new/changed brew to the shared GitHub registry as a PR via `gh`.

### 4. Syntropia CLI & VST3 Engine
* **`syntropia install <brew>`**: Parses `.brew` specs, provisions isolated Wine prefixes, applies DLL overrides (`d2d1 = "disabled"`, `gdiplus = "native"`), runs `winetricks`, registers VST3 DLLs with `yabridgectl`, and triggers automatic sync to `~/.vst3/Syntropia`.

### 5. AUR Package & Updates (PRIORITY #2)
* **AUR PKGBUILD**: `yay -S syntropia` installs the CLI, branding assets, and systemd services. The `PKGBUILD` wraps `phase1/cli/` with `setuptools` and ships everything to `/usr/`.
* **`syntropia update`**: Pulls the brews registry (`git -C ~/.config/syntropia/brews pull`), checks the AUR for a newer syntropia version, and re-runs `syntropia transform --yes` to apply updated branding. The `yay -Syu` equivalent for the Syntropia layer.
* **One-liner installer** (`install-syntropia.sh`): `curl | bash` fallback for users without an AUR helper — clones the repo, builds the venv, runs `syntropia transform --snapshot --yes`.

### 6. Seed ISO (SIDELINED — working, deferred to Phase 2)
* **ISO build pipeline**: mkarchiso profile in `iso/`, fully working and tested. Builds a bootable 3 GB hybrid ISO with Syntropia branding baked into Calamares, GRUB, and Plymouth. Kept as a battle-tested artifact for when a "download one ISO" experience is desired.

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
| **Week 2** | `.brew` Parser & VST Engine | Write `brew.py`, build `syntropia install <brew>` with `wine.overrides` and `winetricks` support, automate Wine prefix initialization and `yabridgectl sync`. |
| **Week 3** | Target DAW & VST Brews | Test and finalize `ableton-live-12.brew`, `fl-studio.brew`, `serum.brew`, and `vital.brew` on local transformed CachyOS system. |
| **Week 4** | AUR Package, Updates & DAW Validation | Build AUR PKGBUILD so `yay -S syntropia` works, add `syntropia update` subcommand, prove end-to-end DAW/VST3 installs with real installers. |

## 🤖 Git Butler Helper (Phase 1)

- **Purpose**: Simplify Git operations for Syntropia development.
- **Script**: `~/bin/syn` Bash script that provides `syn push "msg"`, `syn pull`, `syn status`, `syn sync`, `syn undo`.
- **Tasks**:
  - [ ] Create `syn` script in `~/bin` and make executable.
  - [ ] Add `~/bin` to PATH.
  - [ ] Test push, pull, sync, undo commands.

---

## 🏗️ Repository Structure (Phase 1)

```
Project-Syntropia/
├── install-syntropia.sh         # One-line installer (curl | bash)
├── phase1/
│   ├── plan.md                  # This document
│   ├── tasks.md                 # Task board
│   ├── phase1-requirements.md   # Requirements spec
│   ├── cli/
│   │   ├── pyproject.toml       # Python package metadata
│   │   └── syntropia/
│   │       ├── cli.py           # CLI command dispatch (click)
│   │       ├── brew.py          # .brew TOML parser + registry ops
│   │       ├── transform.py     # System transformation logic
│   │       ├── wine_helper.py   # Wine prefix + yabridge engine
│   │       ├── branding.py      # Plymouth, GRUB, wallpaper install
│   │       └── registry.py      # AUR-style submit (gh PR flow)
│   ├── brews/                   # Bundled .brew manifests
│   │   ├── template.brew
│   │   ├── surge.brew
│   │   ├── vital.brew
│   │   ├── serum.brew
│   │   ├── ableton-live-12.brew
│   │   └── fl-studio.brew
│   ├── tools/                   # Dev utilities
│   │   ├── png_to_ascii.py      # PNG to ASCII art converter
│   │   └── generate_spinner.py  # Spinner animation generator
│   ├── tests/                   # pytest suite (122 tests, all passing)
│   │   ├── conftest.py
│   │   ├── test_brew.py
│   │   ├── test_cli.py
│   │   ├── test_transform.py
│   │   ├── test_wine_helper.py
│   │   ├── test_branding.py
│   │   ├── test_registry.py
│   │   └── test_png_to_ascii.py
│   └── services/                # systemd units
│       ├── syntropia-registry-sync.service
│       └── syntropia-registry-sync.timer
├── Branding/syntropia/          # Asset-drop dir (what transform installs)
│   ├── logo.txt                 # ASCII triangle (fastfetch)
│   ├── fastfetch-color.json     # Color map for logo.txt
│   ├── wallpaper.png            # Desktop background
│   ├── grub/
│   │   ├── splash.png           # GRUB boot menu background
│   │   └── syslinux-splash.png  # Legacy BIOS boot splash
│   ├── plymouth/                # Boot animation (36 frames, stock CachyOS — needs custom)
│   └── calamares/               # Installer branding (ISO-only, sidelined)
│       ├── slides/              # Single source of truth for slides
│       └── usr/share/calamares/branding/cachyos/  # branding.desc, QML, icons
├── iso/                         # mkarchiso pipeline (sidelined, working)
│   ├── build.sh                 # Reproducible ISO build
│   ├── README.md
│   └── out/                     # Built ISOs
├── agent-rules/                 # Rules agents read at session start
│   ├── README.md
│   ├── transform-safety.md
│   ├── git-hygiene.md
│   └── software-inclusion-policy.md
├── .freebuff/                   # Freebuff app data (git-ignored)
└── README.md
```

---

## 🎯 Success Criteria

### Minimum Viable Product (MVP)
- [x] `syntropia transform` works on clean CachyOS installation
- [ ] `syntropia install` proves end-to-end with a real installer (Serum or Vital)
- [ ] VST3 runs in a DAW with <=10ms round-trip latency
- [ ] AUR package real and installable (`makepkg -si` succeeds, `yay -S syntropia` works)
- [ ] `syntropia update` subcommand works (pull brews + re-apply transform)
- [ ] Custom Plymouth boot animation (replace stock CachyOS frames)

### Quality Gates
- **Performance**: Audio latency <=10ms round-trip
- **Reliability**: Transform script idempotent and safe (122 tests, all passing)
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
