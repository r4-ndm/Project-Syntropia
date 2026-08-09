# Phase 1: Syntropia Core Requirements

## 🎯 Mission Statement
> *"First, we build the womb. Then, we grow the god."*

Phase 1 ships `syntropia` as an **AUR package** that transforms a stock CachyOS install into Syntropia OS — rebranded, audio-optimised, and ready to install Windows VST3 plugins with one command (`syntropia install <brew>`).

**Delivery model (package-first)**: User installs stock CachyOS → `yay -S syntropia` (or `curl | bash`) → `syntropia transform --yes` → done. The AUR package is the install mechanism; the Seed ISO is a future polish item (built and tested, but deferred past Phase 1).

**Core Philosophy**: Phase 1 ships **without Hermes**, without safety gates, and without self-mutating AI daemons. It focuses entirely on developer/musician UX, system identity, and smooth Windows audio plugin execution on CachyOS.

---

## 🧬 Development Strategy

### Bootstrap Approach
```
1. Rapid Local Dev via `syntropia transform`
   (In-place branding, configs, wine & yabridge setup)
   │
   ▼
2. Test DAWs & VST3 Brews (Ableton, FL Studio, Serum, Vital)
   │
   ▼
3. Ship via AUR — `yay -S syntropia`
   (PKGBUILD → makepkg → `syntropia transform --yes`)
   │
   ▼
4. Users install stock CachyOS, one command → Syntropia

(Sidelined) Seed ISO — mkarchiso pipeline working & tested,
            deferred to Phase 2 as a polish deliverable.
```

### Key Insight
We prioritise **rapid local development** using `syntropia transform` on running CachyOS systems rather than building ISO images. The transform is idempotent, so iterating is fast: edit code → run transform → test → repeat. The same transform is what the AUR package runs, so development and delivery share the same code path.

---

## 📦 Core Deliverables

### 1. Transformation Script (PRIORITY #1) ✅ DONE
**`syntropia transform`**: Safe, non-destructive, idempotent script that turns any running CachyOS system into Syntropia OS:

- **System Branding**: Custom `/etc/os-release` & `/usr/share/syntropia/logo.txt`
- **Shell Identity**: `😈 \u@\h \W $ ` prompt in `~/.bashrc` & `~/.zshrc` (fish uses fastfetch greeting instead)
- **Audio Stack**: Automated installation of `wine-staging`, `winetricks`, `yabridge`, `yabridgectl`, `pipewire`, `pipewire-pulse`, `wireplumber`
- **Directory Structure**: Creates `~/.config/syntropia/brews/`, `~/.local/share/syntropia/prefixes/`, `~/VST3/` (user-facing drop folder for Windows VST3s)
- **CLI Deployment**: Installs `/usr/local/bin/syntropia` executable
- **Audio Optimization**: Applies PipeWire low-latency configuration (`quantum=128`)
- **Safety**: `--check` dry-run, snapper snapshot before applying, `--yes` flag for automation

### 2. Visual Rebranding Kit ✅ MOSTLY DONE
- **OS Identity**: Custom `/etc/os-release` metadata identifying as "Syntropia OS (powered by CachyOS)"
- **Terminal Experience**: Fastfetch ASCII triangle logo with 6-color palette, `😈 user@host` prompt prefix
- **Boot Experience**: Dark cosmic GRUB splash (done), Plymouth animation (⚠️ frames exist but are stock CachyOS — need custom Syntropia animation)
- **Wallpaper**: Syntropia-themed desktop background

### 3. The `.brew` System ✅ DONE
Application and plugin manifests called **brews** (`.brew` TOML format) — the AUR-style package manager for Windows VSTs:

- **Target DAWs**: Ableton Live 12, FL Studio (manifests exist, not yet tested with real installers)
- **Target VSTs**: Xfer Serum, Vital Wavetable Synth, Surge XT (manifests exist, not yet tested)
- **Registry**: AUR-style local tree at `~/.config/syntropia/brews/` (git clone of shared [r4-ndm/syntropia-brews](https://github.com/r4-ndm/syntropia-brews))
- **Commands**: `save`, `remove`, `install` (by path or registry name), `list-brews`, `search`, `info`, `submit` (gh-based PR flow)

### 4. Syntropia CLI & VST3 Engine ✅ DONE
- **`syntropia install <brew>`**: Parses `.brew` specs, provisions Wine prefixes, applies DLL overrides, runs `winetricks`, registers VST3 DLLs, triggers `yabridgectl sync`
- **`syntropia list-brews`**: Lists available local brews
- **`syntropia search`**: Searches brew repository
- **`syntropia plugins folder` / `syntropia plugins sync`**: Drop-folder VST3 workflow — `~/VST3` is the single user-facing folder for Windows VST3s; `sync` registers it with `yabridgectl` (idempotent) and bridges everything in it
- **Shared-folder architecture (see plan.md §4a)**: `~/VST3` is symlinked into every wine prefix's `Common Files/VST3`, so Bitwig (via `~/.vst3/yabridge` stubs) and Ableton (direct scan) share the same plugins. Bundle layout required for Ableton; vendor data dirs + `installdir` registry keys needed for Arturia-class plugins
- **166 tests, all passing**

### 5. AUR Package & Updates 🔨 TO BUILD
- **AUR PKGBUILD**: `yay -S syntropia` installs the CLI, branding assets, and systemd services
- **`syntropia update`**: Pulls brews registry, checks AUR for newer syntropia, re-runs transform
- **One-liner installer** (`install-syntropia.sh`): `curl | bash` fallback, tested on fresh CachyOS VM ✅

### 6. Seed ISO (SIDELINED — deferred to Phase 2) ⏸️
- **mkarchiso pipeline**: Fully working in `iso/`, builds bootable 3 GB hybrid ISO
- **Calamares slides**: 6 slides baked in, single source of truth in `Branding/syntropia/calamares/slides/`
- Kept as a battle-tested artifact for when a "download one ISO" experience is desired

---

## 🍺 `.brew` Specification

### TOML Schema
```toml
[brew]
name = "Xfer Serum VST3"
version = "1.368"
category = "vst3_synth"
maintainer = "Syntropia Team"

[wine]
version = "cachyos-wine"
prefix = "~/.local/share/syntropia/prefixes/serum"
arch = "win64"

[wine.overrides]
d2d1 = "disabled"   # Bypasses Wine Direct2D graphics bug
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

[install]
commands = [
  "wine /tmp/Serum_Setup.exe /S",
  "cp -r '$WINEPREFIX/drive_c/Program Files/Common Files/VST3/Serum.vst3' \"$HOME/VST3/\""
]
```

### Key Features
- **DLL Override Automation**: Automatic `winecfg` DLL overrides for common issues
- **Winetricks Integration**: Automated installation of required Windows components
- **Yabridge Sync**: Automatic VST3 registration with `yabridgectl`
- **Isolated Prefixes**: Each brew gets its own Wine prefix for stability

---

## 🗂️ Repository Structure

```
Project-Syntropia/
├── install-syntropia.sh         # One-line installer (curl | bash)
├── phase1/
│   ├── plan.md / tasks.md / requirements.md
│   ├── cli/syntropia/           # Python package (cli, brew, transform, wine_helper, branding, registry)
│   ├── brews/                   # 6 .brew manifests
│   ├── tools/                   # png_to_ascii, generate_spinner
│   ├── tests/                   # 122 pytest tests (all passing)
│   └── services/                # systemd units
├── Branding/syntropia/          # Asset-drop dir (logo, wallpaper, grub, plymouth, calamares)
├── iso/                         # mkarchiso pipeline (sidelined, working)
├── agent-rules/                 # Rules for AI agents
└── README.md
```

---

## 🔧 Technical Requirements

### System Dependencies
- **Base OS**: CachyOS (Arch Linux derivative)
- **Python**: 3.11+ with `click` and `toml` libraries
- **Audio Stack**: PipeWire, WirePlumber
- **Windows Compatibility**: Wine-staging, Winetricks, Yabridge, Yabridgectl
- **Containerization**: Podman (for future phases)

### Performance Targets
- **Audio Latency**: <=10ms round-trip (PipeWire quantum=128)
- **Transformation Time**: <5 minutes on modern hardware
- **Brew Installation**: <2 minutes for typical VST3 plugins

### Compatibility
- **Hardware**: x86_64 with >=4GB RAM, >=20GB storage
- **Audio Interfaces**: All ALSA-compatible devices
- **Graphics**: Intel/AMD/NVIDIA with Vulkan support
- **Networking**: Ethernet and WiFi for package installation

---

## 🚀 Implementation Roadmap

### Week 1: Foundation & Branding ✅ Done
- Implement `syntropia transform` script
- Create `/etc/os-release` customization
- Design ASCII logo and shell prompt
- Configure PipeWire low-latency settings
- Deploy CLI binary

### Week 2: Brew System & Engine ✅ Done
- Write `.brew` TOML parser (`brew.py`)
- Implement `syntropia install <brew>` with Wine overrides
- Add Winetricks automation
- Create Nidavellir local registry + shared GitHub registry
- Build CLI commands (install, list, search, info, save, remove, submit)

### Week 3: Target Applications 🔨 In Progress
- Test and finalize DAW brews with real installers
- Test and finalize VST brews (Serum, Vital, Surge)
- Create custom Plymouth boot animation
- Validate on transformed CachyOS system

### Week 4: Distribution & Polish 🔜 Remaining
- Build AUR PKGBUILD (`yay -S syntropia`)
- Add `syntropia update` subcommand
- Build `syn` git butler script
- Write user documentation

---

## 🛡️ Quality Assurance

### Testing Strategy
- **Unit Tests**: All Python modules, 166 tests all passing ✅
- **Integration Tests**: Full brew installation workflow (pending real installer test)
- **System Tests**: Complete transform → brew install → DAW launch (pending)
- **Performance Tests**: Audio latency measurements (pending)
- **Compatibility Tests**: Multiple hardware configurations (pending)

### Exit Criteria
- [x] `syntropia transform` works on clean CachyOS installation
- [ ] `syntropia install` proves end-to-end with a real Windows installer
- [ ] VST3 runs in a DAW with <=10ms round-trip latency
- [ ] AUR package real and installable (`makepkg -si` succeeds)
- [ ] `syntropia update` subcommand works
- [ ] Custom Plymouth boot animation

---

## 🔄 Phase Transition

### Entry to Phase 2 Requirements
Phase 1 must be **fully shipped and stable** before Phase 2 begins:
- [ ] AUR package real and installable (`makepkg -si` succeeds)
- [ ] Real users have successfully used it
- [ ] No critical bugs in core functionality
- [ ] Documentation complete and usable

### Phase 1 → Phase 2 Handoff
Phase 1 establishes the foundation that Phase 2 will inhabit:
- **System Identity**: Syntropia OS as stable base (via AUR + transform)
- **Brew Ecosystem**: Working application installation for Windows VSTs
- **CLI Foundation**: Command structure for future expansion
- **ISO Pipeline**: Battle-tested, ready when needed

---

## 📝 Documentation Requirements

### User Documentation
- Installation guide: "stock CachyOS → yay -S syntropia → syntropia transform --yes"
- Brew creation tutorial
- Troubleshooting common issues
- Performance tuning guide

### Developer Documentation
- Brew specification reference
- CLI extension guide
- Transformation script internals
- Contribution guidelines

---

**Status**: 🔨 ~70% complete — engine, CLI, and branding done; AUR package, real DAW testing, and custom Plymouth animation remain
**Theme**: *"We start by building the temple. Then we pray for a god to inhabit it."*
