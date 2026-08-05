# Phase 1: Syntropia Core Requirements

## 🎯 Mission Statement
> *"First, we build the womb. Then, we grow the god."*

Phase 1 delivers an installable, rebranded CachyOS-based operating system ("Syntropia OS") with native Wine/yabridge VST3 plugin management driven by a simple CLI (`syntropia install <brew>`).

**Core Philosophy**: Phase 1 ships **without Hermes**, without safety gates, and without self-mutating AI daemons. It focuses entirely on developer/musician UX, system identity, and smooth Windows audio plugin execution on CachyOS.

---

## 🧬 Development Strategy

### Bootstrap Approach
```
1. Rapid Local Dev via `syntropia transform`
   (In-place branding, configs, wine & yabridge setup)
   │
   ▼
2. Test DAWs & VST3 Brews (Ableton, FL Studio, Serum)
   │
   ▼
3. Bake verified transform configs into Seed ISO v0.1
   (Using Archiso / CachyOS build profiles)
   │
   ▼
4. Install Seed ISO on target hardware & self-host
```

### Key Insight
We prioritize **rapid local development** using `syntropia transform` before building ISO images. This allows for iterative testing and refinement without constant reinstallation.

---

## 📦 Core Deliverables

### 1. Transformation Script (PRIORITY #1)
**`syntropia transform`**: Safe, non-destructive, idempotent script that turns any running CachyOS system into Syntropia OS:

- **System Branding**: Custom `/etc/os-release` & `/usr/share/syntropia/logo.txt`
- **Shell Identity**: `😈 \u@\h \W $ ` prompt in `~/.bashrc` & `~/.zshrc`
- **Audio Stack**: Automated installation of `wine-staging`, `winetricks`, `yabridge`, `pipewire`, `pipewire-pulse`, `wireplumber`
- **Directory Structure**: Creates `~/.config/syntropia/brews/`, `~/.local/share/syntropia/prefixes/`, `~/.vst3/Syntropia/`
- **CLI Deployment**: Installs `/usr/local/bin/syntropia` executable
- **Audio Optimization**: Applies PipeWire low-latency configuration (`quantum=128`)

### 2. Visual Rebranding Kit
- **OS Identity**: Custom `/etc/os-release` metadata identifying as "Syntropia OS (powered by CachyOS)"
- **Terminal Experience**: Fastfetch ASCII logo banner and `😈 user@host` prompt prefix
- **Boot Experience**: Dark cosmic GRUB theme and animated Plymouth splash

### 3. The `.brew` System
Application and plugin manifests called **brews** (`.brew` TOML format) targeting primary DAWs and VST3 plugins:

- **Target DAWs**: Ableton Live 12, FL Studio
- **Target VSTs**: Xfer Serum, Vital Wavetable Synth
- **Registry**: Local directory index at `~/.config/syntropia/brews/` (Nidavellir Registry)

### 4. Syntropia CLI & VST3 Engine
- **`syntropia install <brew>`**: Parses `.brew` specs, provisions Wine prefixes, applies DLL overrides, runs `winetricks`, registers VST3 DLLs
- **`syntropia list-brews`**: Lists available local brews
- **`syntropia search`**: Searches brew repository

### 5. ISO & Distribution
- **`syntropia download-iso`**: Discovers, downloads, verifies, and flashes official Syntropia ISO images
- **Seed ISO v0.1**: CachyOS `archiso` profile pre-packaged with Syntropia branding and audio environment

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

### Key Features
- **DLL Override Automation**: Automatic `winecfg` DLL overrides for common issues
- **Winetricks Integration**: Automated installation of required Windows components
- **Yabridge Sync**: Automatic VST3 registration with `yabridgectl`
- **Isolated Prefixes**: Each brew gets its own Wine prefix for stability

---

## 🗂️ Repository Structure

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
│       └── services.py       # Systemd service management
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

## 🔧 Technical Requirements

### System Dependencies
- **Base OS**: CachyOS (Arch Linux derivative)
- **Python**: 3.11+ with `toml` library
- **Audio Stack**: PipeWire, WirePlumber
- **Windows Compatibility**: Wine-staging, Winetricks, Yabridge
- **Containerization**: Podman (for future phases)

### Performance Targets
- **Audio Latency**: ≤10ms round-trip (PipeWire quantum=128)
- **Transformation Time**: <5 minutes on modern hardware
- **Brew Installation**: <2 minutes for typical VST3 plugins
- **ISO Boot Time**: <30 seconds to desktop

### Compatibility
- **Hardware**: x86_64 with ≥4GB RAM, ≥20GB storage
- **Audio Interfaces**: All ALSA-compatible devices
- **Graphics**: Intel/AMD/NVIDIA with Vulkan support
- **Networking**: Ethernet and WiFi for package installation

---

## 🚀 Implementation Roadmap

### Week 1: Foundation & Branding
- Implement `syntropia transform` script
- Create `/etc/os-release` customization
- Design Fastfetch ASCII logo and shell prompt
- Configure PipeWire low-latency settings
- Deploy CLI binary

### Week 2: Brew System & Engine
- Write `.brew` TOML parser (`brew.py`)
- Implement `syntropia install <brew>` with Wine overrides
- Add Winetricks automation
- Create Nidavellir local registry
- Build basic CLI commands

### Week 3: Target Applications
- Test and finalize DAW brews (Ableton Live 12, FL Studio)
- Test and finalize VST brews (Serum, Vital)
- Validate on transformed CachyOS system
- Performance and stability testing

### Week 4: Distribution & Testing
- Package transform configs into Archiso profile
- Build `cachyos-syntropia-v0.1.iso`
- VM boot testing (QEMU/KVM)
- Hardware installation validation
- Bootstrap loop verification

---

## 🛡️ Quality Assurance

### Testing Strategy
- **Unit Tests**: All Python modules with ≥80% coverage
- **Integration Tests**: Full brew installation workflow
- **System Tests**: Complete transform → brew install → DAW launch
- **Performance Tests**: Audio latency measurements
- **Compatibility Tests**: Multiple hardware configurations

### Exit Criteria
- [ ] `syntropia transform` works on clean CachyOS installation
- [ ] `syntropia install serum.brew` successfully installs Serum VST3
- [ ] Serum runs in tested DAW with ≤10ms latency
- [ ] Seed ISO boots and self-hosts successfully
- [ ] Git Butler (`syn` script) functional for development workflow

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
- **System Identity**: Syntropia OS as stable base
- **Brew Ecosystem**: Working application installation
- **CLI Foundation**: Command structure for future expansion
- **User Base**: Community for Phase 2 testing

---

## 📝 Documentation Requirements

### User Documentation
- Installation guide (transform vs ISO)
- Brew creation tutorial
- Troubleshooting common issues
- Performance tuning guide

### Developer Documentation
- Brew specification reference
- CLI extension guide
- Transformation script internals
- Contribution guidelines

### System Documentation
- Architecture overview
- Component relationships
- Security model (Phase 2 prep)
- Future evolution path

---

**Status**: ❌ Not started  
**Theme**: *"We start by building the temple. Then we pray for a god to inhabit it."*