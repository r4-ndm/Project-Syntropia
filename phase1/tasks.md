# 🌀 Phase 1: Task Board

This board tracks concrete implementation tasks for **Phase 1: Syntropia Core** (Re-branding, ISO Tooling, `.brew` system, Wine/yabridge VST3 helper).

---

## 🛠️ Phase 1.1: `syntropia transform` Script (PRIORITY #1)

### System Branding Injection
- [ ] **Write `/etc/os-release` customization** - Update OS identification to "Syntropia OS"
- [ ] **Create `/usr/share/syntropia/logo.txt`** - Design ASCII art infinity logo
- [ ] **Implement transformation safety checks** - Verify system is CachyOS, backup critical files

### Shell & User Experience
- [ ] **Configure shell prompt hooks** - Add `🌀 \u@\h \W $ ` to `~/.bashrc` and `~/.zshrc`
- [ ] **Create Fastfetch configuration** - Default Fastfetch display with Syntropia branding
- [ ] **Implement `syntropia fetch` command** - Display system info with custom branding

### Audio Package Installation
- [ ] **Automate audio stack installation** - `pacman -S --needed` for `wine-staging`, `winetricks`, `yabridge`
- [ ] **Install PipeWire stack** - `pipewire`, `pipewire-pulse`, `wireplumber` with optimized configuration
- [ ] **Add dependency verification** - Check for required packages before transformation

### Directory Structure Setup
- [ ] **Create user directories** - `~/.config/syntropia/brews/`, `~/.local/share/syntropia/prefixes/`
- [ ] **Setup VST3 directory** - `~/.vst3/Syntropia/` for bridged plugins
- [ ] **Create downloads cache** - `~/.local/share/syntropia/downloads/` for brew assets

### CLI Deployment
- [ ] **Create `/usr/local/bin/syntropia` wrapper** - Main CLI entry point
- [ ] **Implement command dispatch** - Route to `install`, `transform`, `download-iso`, `fetch`
- [ ] **Add help and version commands** - `--help`, `--version` support

### Audio Optimization
- [ ] **Write PipeWire configuration** - `~/.config/pipewire/pipewire.conf.d/99-syntropia.conf` with quantum=128
- [ ] **Configure low-latency settings** - Sample rate 48000, buffer sizes 32-512
- [ ] **Add audio diagnostics** - Check user `audio` group membership, verify `yabridgectl` installation

### Health Checks
- [ ] **Implement pre-flight checks** - Verify system compatibility before transformation
- [ ] **Add rollback capability** - Backup original configurations for safety
- [ ] **Create validation tests** - Verify transformation succeeded

---

## 🎨 Phase 1.2: System Re-branding & Visual Identity

### Terminal Branding
- [ ] **Design Fastfetch/Neofetch ASCII logo** - Create distinctive Syntropia banner
- [ ] **Configure default Fastfetch config** - Pre-configured display settings
- [ ] **Test terminal display** - Verify logo renders correctly in different terminals

### Boot Experience
- [ ] **Design GRUB theme** - Dark cosmic theme with Syntropia branding
- [ ] **Create Plymouth splash** - Animated boot splash showing assembling infinity swarm
- [ ] **Package boot assets** - Prepare themes for distribution

### System Identity
- [ ] **Create desktop wallpaper** - Syntropia-themed background images
- [ ] **Design icon set** - Custom icons for Syntropia applications
- [ ] **Prepare branding assets** - Logos, colors, fonts for consistency

---

## 🍺 Phase 1.3: Brew System & CLI (`syntropia install <brew>`)

### Brew Parser Implementation
- [ ] **Write `.brew` TOML parser** - Implement in `src/syntropia/brew.py`
- [ ] **Create schema validator** - Validate brew files against specification
- [ ] **Add error handling** - Clear error messages for malformed brews

### Wine Configuration
- [ ] **Implement `[wine.overrides]` support** - Automatic `winecfg` DLL overrides
- [ ] **Create prefix management** - Isolated Wine prefixes per brew
- [ ] **Add architecture detection** - Support for win32/win64 as needed

### Winetricks Integration
- [ ] **Automate `winetricks` package installation** - Install required DLLs and components
- [ ] **Create package cache** - Cache downloaded winetricks packages
- [ ] **Add progress reporting** - Show installation progress to user

### Registry System
- [ ] **Implement Nidavellir local registry** - Directory storage at `~/.config/syntropia/brews/`
- [ ] **Add brew discovery** - Scan and index available brew files
- [ ] **Create registry management** - Add, remove, update brews in registry

### CLI Commands
- [ ] **Implement `syntropia install <brew>`** - Parse brew specs and execute installation
- [ ] **Create `syntropia list-brews`** - List available local brews
- [ ] **Add `syntropia search <term>`** - Search brew names and descriptions
- [ ] **Implement `syntropia info <brew>`** - Show detailed brew information

### Target Brew Definitions
- [ ] **Create `ableton-live-12.brew`** - Ableton Live 12 Suite installation
- [ ] **Create `fl-studio.brew`** - Image-Line FL Studio installation
- [ ] **Create `serum.brew`** - Xfer Serum VST3 with `d2d1` & `gdiplus` fixes
- [ ] **Create `vital.brew`** - Vital Wavetable Synth VST3 installation
- [ ] **Create `template.brew`** - Comprehensive template with all options

---

## 🎛️ Phase 1.4: Wine & yabridge VST3 Helper Engine

### Wine Prefix Management
- [ ] **Automate prefix initialization** - Create optimized Wine prefixes with low-latency flags
- [ ] **Implement environment configuration** - Set `WINE_AUDIO_BACKGROUND=1` and other optimizations
- [ ] **Add prefix cleanup** - Remove orphaned or corrupted prefixes

### VST3 Directory Management
- [ ] **Ensure VST3 directory creation** - Auto-create `~/.vst3/Syntropia` if missing
- [ ] **Implement plugin scanning** - Detect installed VST3 plugins
- [ ] **Add directory verification** - Check permissions and accessibility

### Yabridge Integration
- [ ] **Integrate `yabridgectl` commands** - Automate `yabridgectl add` and `yabridgectl sync`
- [ ] **Create bridge management** - Add, remove, update bridged plugins
- [ ] **Add bridge status reporting** - Show which plugins are successfully bridged

### Audio Verification
- [ ] **Implement PipeWire diagnostics** - Verify host PipeWire sample rate & buffer configuration
- [ ] **Add latency testing** - Measure and report audio round-trip latency
- [ ] **Create audio troubleshooting** - Common issue detection and resolution

### Performance Optimization
- [ ] **Implement caching system** - Cache downloaded installers and components
- [ ] **Add parallel processing** - Install multiple components concurrently where safe
- [ ] **Create progress indicators** - Show installation progress and estimated time

---

## 💿 Phase 1.5: Seed ISO Assembly & Bootstrapping

### ISO Builder Setup
- [ ] **Create CachyOS Archiso profile fork** - Custom `archiso` build directory
- [ ] **Implement `build-iso.sh` script** - Wrap `mkarchiso` with Syntropia configuration
- [ ] **Add configuration templates** - Pre-configured system settings for ISO

### ISO Content Preparation
- [ ] **Package transformation scripts** - Include `syntropia transform` in ISO
- [ ] **Add default brews** - Include essential brew files in ISO
- [ ] **Include branding assets** - GRUB theme, Plymouth splash, wallpapers

### Testing & Validation
- [ ] **VM boot testing** - Validate generated ISO in QEMU/KVM environment
- [ ] **Hardware installation test** - Install Syntropia Seed ISO onto test machine
- [ ] **Bootstrap loop verification** - Test ISO → transform → brew install workflow

### Distribution Preparation
- [ ] **Create checksums** - Generate SHA256 checksums for ISO files
- [ ] **Implement `syntropia download-iso`** - CLI command for ISO discovery and download
- [ ] **Add flashing utilities** - Optional ISO flashing to USB devices

### Quality Assurance
- [ ] **Create installation documentation** - Step-by-step installation guide
- [ ] **Add troubleshooting guide** - Common issues and solutions
- [ ] **Implement feedback collection** - Mechanism for user bug reports

---

## 🤖 Phase 1.6: Git Butler Helper

### Script Implementation
- [ ] **Create `syn` Bash script** - Place in `~/bin/` and make executable
- [ ] **Add `~/bin` to PATH** - Ensure script is accessible
- [ ] **Implement core commands** - `syn push "msg"`, `syn pull`, `syn status`, `syn sync`, `syn undo`

### Git Operations
- [ ] **Add commit automation** - Automatic staging of modified files
- [ ] **Implement branch management** - Create, switch, merge branches
- [ ] **Add remote synchronization** - Push to and pull from remote repositories

### Hermes Integration
- [ ] **Write Hermes skill file** - `~/.hermes/skills/git-butler.md` for voice commands
- [ ] **Implement voice command support** - "Hermes, push my changes" etc.
- [ ] **Add context awareness** - Remember current branch and repository state

### Testing & Refinement
- [ ] **Test all Git operations** - Verify push, pull, sync, undo work correctly
- [ ] **Add error handling** - Graceful failure for Git errors
- [ ] **Create usage documentation** - Quick reference for `syn` commands

---

## 🧪 Phase 1.7: Testing & Quality Assurance

### Unit Testing
- [ ] **Write tests for brew parser** - Verify TOML parsing and validation
- [ ] **Test transformation script** - Verify system modification safety
- [ ] **Test CLI commands** - Verify all commands work as expected

### Integration Testing
- [ ] **Test complete brew installation** - End-to-end test of `syntropia install`
- [ ] **Verify audio stack integration** - Test PipeWire + Wine + yabridge combination
- [ ] **Test ISO build process** - Verify ISO creation and bootability

### Performance Testing
- [ ] **Measure transformation time** - Benchmark on different hardware
- [ ] **Test audio latency** - Verify ≤10ms round-trip latency
- [ ] **Measure brew installation speed** - Optimize for typical use cases

### Compatibility Testing
- [ ] **Test on different CachyOS versions** - Verify backward compatibility
- [ ] **Test hardware variations** - Different audio interfaces, GPUs, CPUs
- [ ] **Test edge cases** - Low disk space, network issues, permission problems

### Documentation
- [ ] **Write user documentation** - Installation guide, brew creation tutorial
- [ ] **Create troubleshooting guide** - Common issues and solutions
- [ ] **Write developer documentation** - Code structure, extension guide

---

## 📊 Progress Tracking

### Week 1 Status
- [ ] Phase 1.1 tasks complete
- [ ] Phase 1.2 tasks started
- [ ] Basic transformation working

### Week 2 Status  
- [ ] Phase 1.3 tasks complete
- [ ] Phase 1.4 tasks started
- [ ] Brew installation working

### Week 3 Status
- [ ] Phase 1.5 tasks complete
- [ ] Phase 1.6 tasks started
- [ ] ISO creation working

### Week 4 Status
- [ ] All Phase 1 tasks complete
- [ ] Quality assurance passed
- [ ] Ready for user testing

---

**Last Updated**: Phase 1 planning complete - ready for implementation