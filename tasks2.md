# Project Syntropia: CachyOS Overlay Task Board (Tasks 2) 🌀

This board tracks the concrete implementation tasks and status for Syntropia's CachyOS host integration, low-latency audio setups, and shared computing network.

---

## 🚀 Immediate Next Steps & Milestones

### 📋 Phase 1: Host Profiler
* **Goal**: Detect kernel configuration, scheduler status, and compatibility environments.
* [x] **CachyOS kernel detection** (`src/syntropia/cachy_host.py` -> `detect_host_environment`)
* [x] **BORE scheduler verification**
* [x] **Wine and yabridge installation detection**
* [x] **Pipewire system status probe**
* [x] **Unit tests for OS profiler** (`tests/test_cachy_host.py` -> `test_detect_cachyos_environment`)

### 🔒 Phase 2: Init Sandbox
* **Goal**: Harness system initialization to restrict container permissions and optimize scheduling parameters.
* [x] **Landlock LSM simulation** (`src/syntropia/cachy_host.py` -> `init_harden_security`)
* [x] **seccomp-bpf filter jailing**
* [x] **no-new-privileges enforcement**
* [x] **Unit tests for security hardening** (`tests/test_cachy_host.py` -> `test_init_harden_security`)

### 🎛️ Phase 3: VST3 Auto-Sync Daemon
* **Goal**: Seamlessly synchronize and run Windows VST3 plugins on Linux.
* [x] **Auto-detect VST3 dll additions** (`src/syntropia/cachy_host.py` -> `configure_wine_yabridge`)
* [x] **yabridgectl sync execution**
* [x] **Low-latency Wine audio configuration variables** (`WINE_AUDIO_BACKGROUND=1`)
* [x] **Unit tests for VST sync** (`tests/test_cachy_host.py` -> `test_configure_wine_yabridge`)

### 🌐 Phase 4: The 0%-100% Sacrifice Slider Daemon
* **Goal**: Safely harvest 0% (chicken) to 100% (monster) idle system resources without impacting active DAW or gaming sessions.
* [x] **Idle monitor checks** (`src/syntropia/cachy_host.py` -> `start_resource_sacrifice`)
* [x] **cgroup nice scheduling restrictions**
* [x] **Unit tests for resource sacrifice thread** (`tests/test_cachy_host.py` -> `test_resource_sacrifice`)


### 🛠️ Phase 5: Node Daemonization & Swarm Bootstrapping
* **Goal**: Build out robust logging, configurations, P2P network startup, and systemd integration.
* [x] **Proper Logging Engine**: Replace print statements in `main.py` with the standard `logging` module.
* [x] **Centralized Configuration**: Load `--bpm` and `resource_percentage` from `~/.config/syntropia/config.toml` (Draft template `config.toml.example` created).
* [x] **Systemd Service Integration**: Create and test `systemd/syntropia.service` (Draft template `systemd/syntropia.service` created).
* [x] **P2P Layer Initialization**: Hook libp2p/WebRTC mesh host startup into `main.py`.
* [x] **Continuous Mutation Loop**: Integrate background evolution testing in `main.py`.

### 💿 Phase 6: Full ISO Release & Distribution
* **Goal**: Build and distribute a ready-to-use CachyOS-Syntropia ISO.
* [ ] **Automated install script**: Transform a standard CachyOS installation.
* [ ] **Custom ISO build configuration**: Include pre-configured yabridge, PipeASIO, and the Syntropia daemon.

