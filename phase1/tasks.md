# 😈 Phase 1: Task Board

**Delivery model**: Package-first (AUR). User installs stock CachyOS → `yay -S syntropia` → `syntropia transform --yes`. The Seed ISO is sidelined (working pipeline in `iso/`, deferred to Phase 2 polish).

This board tracks concrete implementation tasks for **Phase 1: Syntropia Core** (Re-branding, `.brew` system, Wine/yabridge VST3 helper, AUR packaging).

---

## 🛠️ Phase 1.1: `syntropia transform` Script (PRIORITY #1)

### System Branding Injection
- [x] **Write `/etc/os-release` customization** - Update OS identification to "Syntropia OS"
- [x] **Create `/usr/share/syntropia/logo.txt`** - Triangle ASCII art logo
- [x] **Implement transformation safety checks** - Verify system is CachyOS, snapshot before applying, `--check` dry-run

### Shell & User Experience
- [x] **Configure shell prompt hooks** - Add `😈 \u@\h \W $ ` to `~/.bashrc` and `~/.zshrc`
- [x] **Create Fastfetch configuration** - Default Fastfetch display with Syntropia branding and color map
- [ ] **Implement `syntropia fetch` command** - Standalone CLI subcommand for system info display

### Audio Package Installation
- [x] **Automate audio stack installation** - `pacman -S --needed` for `wine-staging`, `winetricks`, `yabridge`, `yabridgectl`
- [x] **Install PipeWire stack** - `pipewire`, `pipewire-pulse`, `wireplumber` with optimized configuration
- [x] **Add dependency verification** - Check for required packages before transformation

### Directory Structure Setup
- [x] **Create user directories** - `~/.config/syntropia/brews/`, `~/.local/share/syntropia/prefixes/`
- [x] **Setup VST3 directory** - `~/.vst3/Syntropia/` for bridged plugins
- [x] **Create downloads cache** - `~/.local/share/syntropia/downloads/` for brew assets

### CLI Deployment
- [x] **Create `/usr/local/bin/syntropia` wrapper** - Main CLI entry point
- [x] **Implement command dispatch** - Route to `install`, `transform`, `save`, `remove`, `list-brews`, `search`, `info`, `submit`
- [x] **Add help and version commands** - `--help`, `--version` support

### Audio Optimization
- [x] **Write PipeWire configuration** - `~/.config/pipewire/pipewire.conf.d/99-syntropia.conf` with quantum=128
- [x] **Configure low-latency settings** - Sample rate 48000, buffer sizes 32-512
- [ ] **Add audio diagnostics** - Check user `audio` group membership, verify `yabridgectl` installation

### Health Checks
- [x] **Implement pre-flight checks** - Verify system compatibility before transformation
- [x] **Add rollback capability** - snapper snapshot before transform (safety rule)
- [x] **Create validation tests** - 122 pytest tests all passing

---

## 🎨 Phase 1.2: System Re-branding & Visual Identity

### Terminal Branding
- [x] **Design Fastfetch ASCII logo** - Triangle logo with `*`/`4` characters, color-mapped
- [x] **Configure default Fastfetch config** - Pre-configured display with 6-color palette
- [ ] **Test terminal display on fish** - Prompt hook targets bash/zsh; fish uses fastfetch greeting only

### Boot Experience
- [x] **Design GRUB theme** - Dark cosmic theme splash installed by transform
- [ ] **Create custom Plymouth animation** - 36 frames exist but are **stock CachyOS**. Need Syntropia-themed infinity swarm assembling animation.
- [x] **Package boot assets** - GRUB splash, Plymouth theme, wallpaper all in `Branding/syntropia/`

### System Identity
- [x] **Create desktop wallpaper** - Syntropia-themed background
- [ ] **Design icon set** - Custom icons for Syntropia applications (deferred to Phase 2)
- [x] **Prepare branding assets** - All assets live in `Branding/syntropia/` (single source of truth)

---

## 🍺 Phase 1.3: Brew System & CLI (`syntropia install <brew>`)

### Brew Parser Implementation
- [x] **Write `.brew` TOML parser** - Implemented in `phase1/cli/syntropia/brew.py`
- [x] **Create schema validator** - Validate brew files against specification
- [x] **Add error handling** - Clear error messages for malformed brews

### Wine Configuration
- [x] **Implement `[wine.overrides]` support** - Automatic `winecfg` DLL overrides
- [x] **Create prefix management** - Isolated Wine prefixes per brew
- [x] **Add architecture detection** - Support for win32/win64 as needed

### Winetricks Integration
- [x] **Automate `winetricks` package installation** - Install required DLLs and components
- [ ] **Create package cache** - Cache downloaded winetricks packages
- [ ] **Add progress reporting** - Show installation progress to user

### Registry System (AUR-style)
- [x] **Implement Nidavellir local registry** - Directory storage at `~/.config/syntropia/brews/` (your personal AUR checkout)
- [x] **Add brew discovery** - Scan and index available brew files
- [x] **Create registry management** - `syntropia save <file>` (validate + copy in), `syntropia remove <name>` (delete), save overwrites = update
- [x] **Seed registry from repo** - `syntropia save` the bundled brews into the local registry
- [x] **Shared GitHub registry** - Public repo [r4-ndm/syntropia-brews](https://github.com/r4-ndm/syntropia-brews) as the community "AUR"
- [x] **`syntropia submit <name>`** - gh-based PR flow: feature branch → commit only the brew → push → `gh pr create`

### CLI Commands
- [x] **Implement `syntropia install <brew>`** - Parse brew specs and execute installation; accepts a file path or a bare registry name
- [x] **Create `syntropia list-brews`** - List available local brews
- [x] **Add `syntropia search <term>`** - Search brew names and descriptions
- [x] **Implement `syntropia info <brew>`** - Show detailed brew information
- [x] **Add `syntropia save` / `remove`** - Write ops for the local registry
- [x] **Add `syntropia submit`** - Push a local brew to the shared GitHub registry as a PR
- [ ] **Add `syntropia update`** - Pull brews registry + check AUR + re-run transform (the `yay -Syu` equivalent)
- [ ] **Add `syntropia fetch`** - Standalone system info display subcommand

### Target Brew Definitions
- [x] **Create `surge.brew`** - Surge XT VST3 (free, good test candidate)
- [x] **Create `template.brew`** - Comprehensive template with all options
- [x] **Create `serum.brew`** - Xfer Serum VST3 with `d2d1` & `gdiplus` fixes
- [x] **Create `vital.brew`** - Vital Wavetable Synth VST3 installation
- [x] **Create `ableton-live-12.brew`** - Ableton Live 12 Suite installation
- [x] **Create `fl-studio.brew`** - Image-Line FL Studio installation
- [ ] **Prove a brew end-to-end with a real installer** - Test `syntropia install vital` or `serum` against the actual .exe

---

## 🎛️ Phase 1.4: Wine & yabridge VST3 Helper Engine

### Wine Prefix Management
- [x] **Automate prefix initialization** - Create optimized Wine prefixes with low-latency flags
- [x] **Implement environment configuration** - Set `WINE_AUDIO_BACKGROUND=1` and other optimizations
- [ ] **Add prefix cleanup** - Remove orphaned or corrupted prefixes

### VST3 Directory Management
- [x] **Ensure VST3 directory creation** - Auto-create `~/.vst3/Syntropia` if missing
- [ ] **Implement plugin scanning** - Detect installed VST3 plugins
- [ ] **Add directory verification** - Check permissions and accessibility

### Yabridge Integration
- [x] **Integrate `yabridgectl` commands** - Automate `yabridgectl add` and `yabridgectl sync`
- [ ] **Create bridge management** - Add, remove, update bridged plugins
- [ ] **Add bridge status reporting** - Show which plugins are successfully bridged

### Audio Verification
- [x] **Implement PipeWire diagnostics** - Verify host PipeWire sample rate & buffer configuration
- [ ] **Add latency testing** - Measure and report audio round-trip latency
- [ ] **Create audio troubleshooting** - Common issue detection and resolution

### Performance Optimization
- [ ] **Implement caching system** - Cache downloaded installers and components
- [ ] **Add parallel processing** - Install multiple components concurrently where safe
- [ ] **Create progress indicators** - Show installation progress and estimated time

---

## 📦 Phase 1.5: AUR Package & Distribution (was ISO — reprioritised)

### AUR Package
- [ ] **Create `PKGBUILD`** - Wrap `phase1/cli/` with setuptools, install to `/usr/`
- [ ] **Test `makepkg -si`** - Verify the PKGBUILD builds and installs correctly
- [ ] **Submit to AUR** - Push the PKGBUILD to the AUR so `yay -S syntropia` works
- [ ] **Add `syntropia update` subcommand** - Pull brews, check AUR, re-run transform

### One-liner Installer
- [x] **Create `install-syntropia.sh`** - `curl | bash` fallback, clones repo + builds venv + runs transform
- [x] **Test `install-syntropia.sh`** - Verified on a fresh CachyOS VM install, transform applied successfully

### ISO Pipeline (SIDELINED — deferred to Phase 2)
- [x] **ISO build pipeline** - mkarchiso in `iso/build.sh`, fully working and reproducible
- [x] **VM boot testing** - Verified in QEMU/KVM, ISO boots and Calamares runs
- [x] **Calamares slides** - 6 slides baked in, single source of truth in `Branding/syntropia/calamares/slides/`
- [ ] `syntropia download-iso` - CLI command for ISO discovery (deferred)
- [ ] SHA256 checksums - For release distribution (deferred)

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

### Testing & Refinement
- [ ] **Test all Git operations** - Verify push, pull, sync, undo work correctly
- [ ] **Add error handling** - Graceful failure for Git errors

---

## 🧪 Phase 1.7: Testing & Quality Assurance

### Unit Testing
- [x] **Write tests for brew parser** - Verify TOML parsing and validation
- [x] **Test transformation script** - Verify system modification safety
- [x] **Test CLI commands** - Verify all commands work as expected
- [x] **Test branding install** - Plymouth, GRUB, wallpaper, fastfetch
- [x] **Test registry ops** - Save, remove, submit, validation
- [x] **Test PNG-to-ASCII** - Logo conversion pipeline
- [x] **Test wine helper** - Env building, prefix provisioning, dry-run, toolchain checks
- **Result**: 122 tests, all passing ✅

### Integration Testing
- [ ] **Test complete brew installation** - End-to-end test of `syntropia install` with real installer
- [ ] **Verify audio stack integration** - Test PipeWire + Wine + yabridge combination
- [ ] **Test AUR package install** - Verify `yay -S syntropia` on a clean CachyOS

### Performance Testing
- [ ] **Measure transformation time** - Benchmark on different hardware
- [ ] **Test audio latency** - Verify <=10ms round-trip latency
- [ ] **Measure brew installation speed** - Optimize for typical use cases

### Documentation
- [ ] **Write user documentation** - Installation guide (stock CachyOS → yay → transform)
- [ ] **Create brew creation tutorial** - How to write and submit a .brew
- [ ] **Write developer documentation** - Code structure, extension guide

---

## 📊 Progress Tracking

### Completed (Week 1-2 equiv.)
- [x] Phase 1.1: `syntropia transform` complete (os-release, logo, audio packages, PipeWire config, directories, CLI)
- [x] Phase 1.2: Branding assets complete (GRUB, Plymouth frames, wallpaper, ASCII logo, fastfetch config)
- [x] Phase 1.3: Brew system complete (parser, registry, install/list/search/info/save/remove/submit)
- [x] Phase 1.4: Wine engine complete (prefix provisioning, overrides, winetricks, yabridge sync, dry-run)

### In Progress (Week 3 equiv.)
- [ ] Phase 1.3: Prove a brew end-to-end with a real Windows installer
- [ ] Phase 1.2: Custom Plymouth animation (replace stock CachyOS frames)

### Remaining (Week 4 equiv.)
- [ ] Phase 1.5: AUR PKGBUILD + `syntropia update` subcommand
- [ ] Phase 1.6: Git Butler `syn` script
- [ ] Phase 1.7: Integration testing, documentation

---

**Last Updated**: Package-first strategy refocus — AUR delivery, ISO sidelined, Plymouth custom animation needed
