# 😈 Phase 1: Task Board

**Delivery model**: Package-first (AUR), split into three packages — `syntropia-cli` (core command + plugin host), `syntropia-brews` (Windows-app helper, optional), `syntropia` (the rebrand: `transform`/`update` + branding assets). User installs stock CachyOS → `paru -S syntropia` (pulls `syntropia-cli`; add `syntropia-brews` for the app helper) → `syntropia transform --yes`. The Seed ISO is sidelined (working pipeline in `iso/`, deferred to Phase 2 polish).

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
- [x] **Setup VST3 drop folder** - `~/VST3/` for bridged plugins (brew installs and manual drops both land here)
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
- [x] **Create validation tests** - 270 pytest tests all passing

---

## 🎨 Phase 1.2: System Re-branding & Visual Identity

### Terminal Branding
- [x] **Design Fastfetch ASCII logo** - Triangle logo with `*`/`4` characters, color-mapped
- [x] **Configure default Fastfetch config** - Pre-configured display with 6-color palette
- [ ] **Test terminal display on fish** - Prompt hook targets bash/zsh; fish uses fastfetch greeting only

### Boot Experience
- [x] **Design GRUB theme** - Dark cosmic theme splash installed by transform
- [x] **Create custom Plymouth animation** - 88-frame triangle particle swarm (Branding/syntropia/plymouth/, generate_bootanimation.py) replaced the stock CachyOS frames
- [x] **Package boot assets** - GRUB splash, Plymouth theme, wallpaper all in `Branding/syntropia/`

### System Identity
- [x] **Create desktop wallpaper** - Syntropia-themed background
- [ ] **Design icon set** - Custom icons for Syntropia applications (deferred to Phase 2)
- [x] **Prepare branding assets** - All assets live in `Branding/syntropia/` (single source of truth)

---

## 🍺 Phase 1.3: Brew System & CLI (`syntropia install <brew>`)

### Brew Parser Implementation
- [x] **Write `.brew` TOML parser** - Implemented in `phase1/cli/brews/syntropia_brews/brew.py`
- [x] **Create schema validator** - Validate brew files against specification
- [x] **Add error handling** - Clear error messages for malformed brews

### Wine Configuration
- [x] **Implement `[wine.overrides]` support** - Automatic `winecfg` DLL overrides
- [x] **Create prefix management** - Isolated Wine prefixes per brew
- [x] **Add architecture detection** - Support for win32/win64 as needed

### Winetricks Integration
- [x] **Automate `winetricks` package installation** - Install required DLLs and components
- [ ] **Create package cache** - Cache downloaded winetricks packages
- [x] **Add progress reporting** - Show installation progress to user (StepProgress + elapsed timer)

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
- [x] **Add `syntropia update`** - Pull brews registry + paru-update + re-run transform (the `paru -Syu` equivalent); aur source actually runs `paru -Syu` (yay fallback) so a pacman-tracked syntropia updates itself, then pulls brews, then re-applies branding via a fresh `sudo syntropia transform --yes` subprocess (new code executes; failures surface cleanly, no tracebacks)
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
- [x] **Ensure VST3 drop folder creation** - Auto-create `~/VST3` if missing (brew installs and manual drops both land here)
- [x] **Implement plugin scanning** - Detect installed VST3 plugins (inventory.py scans drop-folder + native VST3s)
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
- [x] **Create progress indicators** - Show installation progress (StepProgress/ProgressBar)

---

## 📦 Phase 1.5: AUR Packages & Distribution (was ISO — reprioritised)

### AUR Package
- [x] **Create the three `PKGBUILD`s** - `phase1/aur/{syntropia-cli,syntropia-brews,syntropia}/` each wrap their own `phase1/cli/` project (python -m build + installer, installs to `/usr/`): `syntropia-cli` ships the core command, `syntropia-brews` ships the engine + seed manifests + systemd units, `syntropia` ships the transform + branding assets + `syntropia.install` scriptlet; all three read pkgver from `phase1/cli/syntropia/__init__.py` (single source of truth)
- [x] **Test `makepkg -si`** - all three `makepkg` builds verified (0.1.0-1, correct file split: core / brews+units / branding); wheels build and entry-point plugin discovery works (core-only shows no commands, brews-only shows only brews)
- [ ] **Submit to AUR** - Push the three PKGBUILDs to the AUR so `paru -S syntropia` (rebrand) and `paru -S syntropia-brews` (app helper) work. Source tarball released + sha256sums pinned (v0.1.0); blocked only on the AUR account.
- [x] **Add `syntropia update` subcommand** - Pull brews, check AUR, re-run transform (verified with a real transform re-run on the local machine)

### One-liner Installer
- [x] **Create `install-syntropia.sh`** - `curl | bash` fallback, clones repo + builds venv + runs transform
- [x] **Test `install-syntropia.sh`** - Verified on a fresh CachyOS VM install, transform applied successfully

### ISO Pipeline (SIDELINED — deferred to Phase 2)
- [x] **ISO build pipeline** - mkarchiso in `iso/build.sh`, fully working and reproducible
- [x] **VM boot testing** - Verified in QEMU/KVM, ISO boots and Calamares runs
- [x] **Calamares slides** - 6 slides baked in, single source of truth in `Branding/syntropia/calamares/slides/`
- [ ] `syntropia download-iso` - CLI command for ISO discovery (deferred)
- [x] SHA256 checksums - Release tarball sha256 pinned in all three PKGBUILDs + .SRCINFO (v0.1.0)

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
- **Result**: 270 tests, all passing ✅

### Integration Testing
- [ ] **Test complete brew installation** - End-to-end test of `syntropia install` with real installer
- [ ] **Verify audio stack integration** - Test PipeWire + Wine + yabridge combination
- [ ] **Test AUR packages install** - Verify `paru -S syntropia` (+ optional `syntropia-brews`) on a clean CachyOS

### Performance Testing
- [ ] **Measure transformation time** - Benchmark on different hardware
- [ ] **Test audio latency** - Verify <=10ms round-trip latency
- [ ] **Measure brew installation speed** - Optimize for typical use cases

### Documentation
- [ ] **Write user documentation** - Installation guide (stock CachyOS → `paru -S syntropia` [add `syntropia-brews` for the app helper] → transform)
- [ ] **Create brew creation tutorial** - How to write and submit a .brew
- [ ] **Write developer documentation** - Code structure, extension guide

---

## 🧹 Phase 1.9: First-Boot Apps Wizard (favorites picker) 🆕

A first-boot **popup GUI with checkboxes** for popular apps (Telegram, Wezterm, Bitwig, Kiro, Freebuff…). Checking an app runs `paru -S` for it — paru handles both official-repo and AUR packages in one list, with live output in a terminal window. It's a thin wrapper around `paru`, deliberately **not** a Calamares module, baked repo, or CachyOS-packageinstaller fork (each was investigated and rejected — see `phase1/wizard/README.md`). The app list is a plain text file, so adding an app = one line.

### Implementation (phase1/wizard/)
- [x] **Write `apps.list` catalog** - Pipe-delimited `category|name|package|description`; user override at `~/.config/syntropia/apps.list`; 9 categories / 26 apps, all repo-verified: Chat (Telegram, Discord), Browser (Brave), DAW (Bitwig, Reaper), AI (Kiro, Freebuff, Ollama), Terminal (Wezterm), CLI (ripgrep, fzf, zoxide, eza, bat, yazi, btop, tmux), Video (mpv, OBS), Wallet (Electrum), Web (WhatsApp, YouTube Music, Spotify, Notion, Figma, Gmail — URL launchers); LibreWolf dropped (left AUR)
- [x] **Web app support** - URL in the package field = PWA-style launcher (Brave/Chromium `--app=URL`, else Firefox); mixed native+web installs split cleanly
- [x] **Write `syntropia-apps-wizard.sh`** - TUI-only driver (~220 lines): resolve catalog → run the Bubble Tea TUI in a terminal → one `paru -S` for all picks; `--once`/`--config`/`--install-autostart`/`--remove-autostart` modes
- [x] ~~**Write `syntropia-apps-server.py` + `syntropia-apps-dialog.html`**~~ - REMOVED (superseded by the TUI): the stdlib-only local server + Win98 browser grid was deleted when the Bubble Tea TUI became the tier-1 dialog and the ISO went vanilla
- [x] ~~**Write `syntropia-apps-dialog.py`**~~ - REMOVED (superseded by the TUI): the PySide6/qt grid, kdialog and zenity fallbacks were deleted when the TUI became the only frontend — the wizard is a thin TUI-only driver now
- [x] **Autostart-once desktop entry** - `syntropia-apps.desktop` template; `--once` self-disables via done-marker
- [x] **Ship in ISO** - `iso/build.sh` phase 2 copies wizard + `apps.list` + dialog into rootfs `/etc/syntropia/` and installs a first-boot autostart entry (`/etc/xdg/autostart/`); shipped copy resolves its bundled catalog (verified against a scratch rootfs); the `syntropia_toolchain` hook that preinstalled **brave-bin + paru** was REMOVED — the ISO stays stock CachyOS and the TUI bootstraps paru itself at first use; branding hook now also copies the fastfetch config + fish greeting into **existing** target user homes (skel is written after Calamares creates the user, so skel-only writes never reach the first user)
- [x] ~~**Ship via transform**~~ - SUPERSEDED: the wizard is the standalone app-wiz4rd repo and ships in the ISO from its release tarball (build.sh step 3.6), not via `syntropia transform`
- [x] **paru dependency solved for ISO installs** - the TUI bootstraps paru inline (`sudo pacman -S paru`) when missing; kdialog/qt/zenity paths fail with a clear message (not a crash) when no toolkit exists
- [x] ~~**Brave = default browser**~~ - REVERTED (keep CachyOS vanilla): no default-browser hack; Brave is a normal first-boot pick in the dialog like every other app
- [x] ~~**No wallet prompt over the grid**~~ - REMOVED with the browser dialog: the `kwalletrc` `[KSecretD]` hack died with the web dialog — the TUI needs no browser, so no keyring request exists to silence

---

## 🧠 Phase 1.8: Agent Skill Layer — THE LIVING COMPUTER 🆕

Every Syntropia install ships **intelligence alongside the app**: a `SKILL.md` dropped into `~/.config/syntropia/skills/<brew>/` that any AI agent reads to help with that app — stack, known issues + proven fixes, logs, uninstall. `syntropia transform` installs the machine-level skill so a transformed box knows its own constitution. This is the core Syntropia vision: *the machine becomes legible to any agent that shows up.*

### Skill Format
- [ ] **Define SKILL.md format** - Required sections (Stack, Known Issues + Fixes, Logs, Uninstall), frontmatter, naming convention
- [ ] **Write `template.SKILL.md`** - The authoring template every brew skill is based on

### Brew Schema & Engine
- [ ] **Add `[skill]` field to brew schema** - Optional `source` path to a bundled SKILL.md; auto-generate a skeleton from brew metadata when absent
- [ ] **Install per-brew skills** - `syntropia install` writes `~/.config/syntropia/skills/<brew>/SKILL.md` as an engine step (idempotent, like the rest)
- [ ] **Add machine-level skill** - `syntropia transform` installs `~/.config/syntropia/skills/syntropia/SKILL.md` (registry location, ~/VST3 convention, safety rules, update flow)
- [ ] **Auto-generate skeleton** - From brew metadata (name, wine stack, prefix, category) when no bundled skill exists

### Content — Write the Real Skills
- [ ] **Write `ableton-live-12.SKILL.md`** - From the war diary: giang17 d2d1-dcomp wine (NOT stock, NOT shibco), prefix + launchers, "serious program error" workaround, D3D env incantations, busy-prefix hang rule, newest-Live-dir log gotcha, uninstall straggler search
- [ ] **Write machine `SKILL.md`** - The Syntropia OS constitution an agent reads on any transformed box

### Validation
- [ ] **Tests for skills** - Skill install step, skeleton generation, missing-source handling, idempotent re-install
- [ ] **Wire into CLI** - `syntropia install` and `syntropia transform` both covered by the test suite

---

## 📊 Progress Tracking

### Completed (Week 1-2 equiv.)
- [x] Phase 1.1: `syntropia transform` complete (os-release, logo, audio packages, PipeWire config, directories, CLI)
- [x] Phase 1.2: Branding assets complete (GRUB, Plymouth frames, wallpaper, ASCII logo, fastfetch config)
- [x] Phase 1.3: Brew system complete (parser, registry, install/list/search/info/save/remove/submit)
- [x] Phase 1.4: Wine engine complete (prefix provisioning, overrides, winetricks, yabridge sync, dry-run)

### In Progress (Week 3 equiv.)
- [ ] Phase 1.3: Prove a brew end-to-end with a real Windows installer
- [x] Phase 1.2: Custom Plymouth animation (replace stock CachyOS frames)

### New (Agent Skill Layer)
- [ ] Phase 1.8: Per-brew `SKILL.md` installed by `syntropia install` (stack, fixes, logs, uninstall)
- [ ] Phase 1.8: Machine-level skill installed by `syntropia transform` (the OS constitution)
- [ ] Phase 1.8: Real Ableton skill written from the war diary

### New (First-Boot Apps Wizard)
- [x] Phase 1.9: Wizard built (apps.list catalog + zenity/paru script + autostart-once) in `phase1/wizard/`
- [x] Phase 1.9: Wizard shipped via ISO `/etc/syntropia/` (build.sh phase 2); transform path still open

### Remaining (Week 4 equiv.)
- [x] Phase 1.5: AUR PKGBUILD + `syntropia update` subcommand
- [ ] Phase 1.6: Git Butler `syn` script
- [ ] Phase 1.7: Integration testing, documentation

---

**Last Updated**: v0.1.0 source tarball released on GitHub (sha `5bb16239`) + pushed to origin/main; uninstall extraction, Windows Programs tab, and the shared-helper dedupe all committed. Remaining Phase 1.5 step is the AUR push (blocked on account).
