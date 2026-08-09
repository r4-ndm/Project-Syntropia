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
  - Sets up directories (`~/.config/syntropia/brews`, `~/.local/share/syntropia/prefixes`, `~/VST3` — the user-facing drop folder for Windows VST3s).
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
  - `syntropia plugins folder [--create]` / `syntropia plugins sync [--check]` — the drop-folder workflow: users drop Windows VST3s into `~/VST3` (created on demand), `sync` registers the folder with `yabridgectl` (idempotent) and bridges them (stubs land in `~/.vst3/yabridge`). See §4a for the shared-folder architecture and bundle/registry gotchas.

### 4. Syntropia CLI & VST3 Engine
* **`syntropia install <brew>`**: Parses `.brew` specs, provisions isolated Wine prefixes, applies DLL overrides (`d2d1 = "disabled"`, `gdiplus = "native"`), runs `winetricks`, registers VST3 DLLs with `yabridgectl`, and triggers automatic sync. Brew installs copy their VST3s into `~/VST3` (the single user-facing folder), which `yabridgectl` bridges to `~/.vst3/yabridge`.

### 4a. Shared `~/VST3` Folder Architecture (both DAWs)

**One real folder, two DAWs.** `~/VST3` is the single user-facing folder for Windows VST3 plugins. Manual drops (`syntropia plugins sync`) and brew installs both land here; then **both** DAWs consume the same files:

```
~/VST3/                          ← THE one real folder (bundle layout required)
├── Arturia/         (vendor subdirs allowed)
├── <Plugin>.vst3/   (bundle: Contents/x86_64-win/<Plugin>.vst3)
└── ...

~/.wine/drive_c/Program Files/Common Files/VST3      ─┐
…/prefixes/<brew>/drive_c/Program Files/Common Files/VST3 ─┤  both symlink → ~/VST3
```

* **Bitwig / native Linux DAWs** read `~/.vst3/yabridge/` — the Linux stubs `yabridgectl sync` writes for every Windows plugin in `~/VST3`. No per-DAW setup needed (Bitwig scans it by default).
* **Ableton (wine-hosted)** scans its own prefix's `C:\Program Files\Common Files\VST3`, which is a **symlink to `~/VST3`**, so it sees the exact same plugins.

**Bundle requirement**: Ableton only scans VST3 **bundle** layout (`Plugin.vst3/Contents/x86_64-win/Plugin.vst3`). Flat single-file `.vst3` DLLs (what many zips ship, e.g. Arturia's manual installs) are invisible to Ableton — yabridge accepts them for Bitwig, but they must be wrapped into bundle dirs for Ableton. (CRMBL and all 35 Arturia plugins were converted this way.)

**Vendor data + registry**: Some vendors (Arturia especially) also need their data dir and `installdir` registry keys present in the DAW's prefix, or the plugin loads-but-fails to initialize:

```
# per Ableton prefix (symlinked, not copied — 5.8 GB for Arturia):
drive_c/ProgramData/Arturia          → ~/.wine/drive_c/ProgramData/Arturia
  drive_c/ProgramData/ArturiaSC      → ~/.wine/.../ArturiaSC
drive_c/Program Files/Arturia        → ~/.wine/.../Arturia

# per plugin, in the DAW prefix's registry (added via wine reg add, wine-11.x):
HKLM\Software\Arturia\<Plugin>  installdir = "C:\ProgramData\Arturia\<Plugin>"
HKLM\Software\Arturia           InstallVST364Dir = "C:\Program Files\Common Files\VST3"
```

**Gotchas learned (bake these into tooling):**
* Use the prefix's **own wine** for `reg add` (`/opt/syntropia-wine/bin/wine` for Ableton) — system wine errors with a version mismatch against a custom-wine prefix.
* `yabridgectl sync` **verifies each plugin by launching it** and hangs on some Arturia bundles — use `--no-verify` for drop-folder syncs.
* Clearing the Ableton plugin DB (`AppData/Local/Ableton/Live Database/Live-plugins-1.db`) forces a full rescan after folder changes.
* This wiring (symlinks + registry) is currently **manual per-machine** — a `syntropia plugins link --data <vendor>` command is the planned automation.

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
plugin_dirs = ["~/VST3"]

[environment]
WINEDLLOVERRIDES = "winemenubuilder.exe=d"
WINE_AUDIO_BACKGROUND = "1"
LANG = "en_US.UTF-8"

# OPTIONAL — vendor data linking (Arturia-class plugins)
# Links a vendor's data dirs + installdir registry keys from another
# prefix (default ~/.wine) into THIS brew's prefix, so plugins that load
# in Bitwig via yabridge also initialize in a wine-hosted DAW like
# Ableton. Best-effort: skipped with a warning when the vendor isn't
# installed in the source prefix yet.
[vendor_data]
source = "~/.wine"
vendors = ["Arturia"]

[install]
commands = [
  "wine /tmp/Serum_Setup.exe /S",
  "cp -r '$WINEPREFIX/drive_c/Program Files/Common Files/VST3/Serum.vst3' \"$HOME/VST3/\""
]
```

**`[vendor_data]`** (optional) — wires a vendor's data into the brew's own
prefix. `source` is the prefix that already has the vendor installed
(default `~/.wine`); `vendors` lists the vendor names to link. The install
engine runs this as its own step after the install commands: data
directories are symlinked (never copied) and missing `installdir` registry
keys are added with the prefix's own wine — existing keys are never
clobbered. When the vendor isn't present in the source prefix the step
warns and continues rather than failing the DAW install.

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
│   │   └── syntropia/│   │   ├── cli.py           # CLI command dispatch (click)
│   │   ├── brew.py          # .brew TOML parser + registry ops
│   │   ├── plugins.py       # Drop-folder VST3 workflow (~/VST3 + yabridge sync)
│   │   ├── transform.py     # System transformation logic
│   │   ├── wine_helper.py   # Wine prefix + yabridge engine
│   │   ├── branding.py      # Plymouth, GRUB, wallpaper install
│   │   ├── registry.py      # AUR-style submit (gh PR flow)
│   │   └── update.py        # syntropia update (AUR/git/pip detection)
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
│   ├── tests/                   # pytest suite (166 tests, all passing)
│   │   ├── conftest.py
│   │   ├── test_brew.py
│   │   ├── test_cli.py
│   │   ├── test_plugins.py
│   │   ├── test_transform.py
│   │   ├── test_wine_helper.py
│   │   ├── test_branding.py
│   │   ├── test_registry.py
│   │   ├── test_uninstall.py
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
- **Reliability**: Transform script idempotent and safe (166 tests, all passing)
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
