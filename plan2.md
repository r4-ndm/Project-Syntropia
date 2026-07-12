# 🌀 Project Syntropia: CachyOS Host Injection & Swarm Plan (Plan 2)

> **"Syntropia isn't a new OS. It's the soul that enters the host."**
>
> We pivot from building a new OS from scratch to possessing and enhancing an existing host being: **CachyOS**. L1–L4 AI container overlays are injected directly into CachyOS to deliver low-latency audio performance, Windows gaming compatibility, and a shared global compute network powered by a 1%–100% CPU/GPU sacrifice slider.

---

## 🏆 Why This Plan Works: The "Plug-In" Advantage

Rather than building and maintaining a full custom Linux distribution (which requires kernel updates, driver validation, package repository hosting, and massive testing overhead), Syntropia operates as a lightweight, performance-tuned system daemon overlay.

| Benefit | Why It's Brilliant |
| :--- | :--- |
| **No Fork Maintenance** | We don't maintain a separate kernel or package set. CachyOS handles that heavy lifting. |
| **Instant Updates** | Users get CachyOS's regular updates (kernel, drivers, security patches) automatically. |
| **Easy Installation** | Installed natively via the AUR (`yay -S syntropia`) or `pip install syntropia`. |
| **Low Barrier to Entry** | Existing CachyOS users can inject the overlay without nuking their current setup. |
| **Portability** | The overlay can be adapted to other Arch-based distros (EndeavourOS, Manjaro) later. |
| **Dynamic Resources** | A transparent 1%–100% sacrifice slider gives users complete control of idle compute contribution. |


---

## 🏗️ The Architecture (Injected & Alive)

```text
┌─────────────────────────────────────────────────────────────────┐
│  CACHYOS HOST (The Physical Being)                              │
│  - linux-cachyos kernel (BORE scheduler)                       │
│  - Optimized for performance out of the box                     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  L4 INIT INJECTION LAYER (The Nervous System)                  │
│  - Landlock LSM: Filesystem sandboxing                          │
│  - seccomp-bpf: System call filtering                           │
│  - no-new-privileges: Locked credentials                        │
│  - Pipewire/PipeASIO: Real-time audio tuning                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  L1-L4 AI CONTAINER OVERLAY (The Intelligence)                  │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  L1 Manager: 3% Resource Sacrifice Daemon              │   │
│  │  - Monitors idle CPU/GPU                                │   │
│  │  - Runs background compute tasks                         │   │
│  │  - Yields immediately to user processes                 │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  L2 Supervisor: yabridge / Wine Manager                 │   │
│  │  - Auto-detects VST3 .dll files                         │   │
│  │  - Runs yabridgectl sync automatically                  │   │
│  │  - Manages Wine prefix environments                      │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  L3 Orchestrator: DAW / Game Router                     │   │
│  │  - Detects launched games and DAWs                      │   │
│  │  - Applies tailored environment variables               │   │
│  │  - Adjusts scheduler priorities in real-time            │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  L4 Brain: OS Config Mutator                            │   │
│  │  - Learns from system behavior                          │   │
│  │  - Mutates configuration for better performance         │   │
│  │  - Hardens security based on threat patterns            │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🎮 The Three Pillars of Success

### 1️⃣ Windows Gaming (Proton/Wine)
* **AI Tuning**: L3/L4 containers detect launched games and apply optimal environment variables (e.g. `WINE_AUDIO_BACKGROUND=1` to prevent sound crackling).
* **Performance**: Dynamically adjusts thread scheduler nice levels and BORE scheduler latency parameters.

### 2️⃣ DAW & VST3 Compatibility (Ableton, FL Studio, Bitwig)
* **Automatic Bridging**: L2 containers monitor VST3 directories and run `yabridgectl sync` automatically on file changes.
* **ASIO Latency Tuning**: L2/L3 containers tune Pipewire and PipeASIO for sub-millisecond roundtrip latency.
* **Drag-and-Drop**: Virtualizes folder sharing between the host and Wine prefixes for seamless sample and preset transfers.

### 3️⃣ Crypto Security (DeFi Hardening)
* **Init-Layer Sandboxing**: Landlock LSM restricts filesystem access (read, write, execute) to assign subdirectories.
* **seccomp-bpf**: Blocks system calls related to sandbox breakouts (e.g., `sys_reboot`, `ptrace`).
* **no-new-privileges**: Locks container credentials at birth so they cannot escalate privileges.

---

## 🌐 The Resource Sacrifice Slider (1% to 100%)

| Aspect | How It Works |
| :--- | :--- |
| **The Rule** | The user chooses a contribution level from 1% (**noob**) to 100% (**monster**). |
| **The Daemon** | L1 Manager runs low-priority background compute tasks based on the selected slider level when idle. |
| **The Yield** | cgroup limits + nice values ensure immediate CPU yield when user activity resumes. |
| **The Swarm** | Model weights are chunked and distributed via P2P DHT (BitTorrent). |
| **The Trust** | No loyalty required—just enough nodes to maintain redundancy. |

---

## 📡 The Network Layer: Hybrid P2P Communication & DePIN

While BitTorrent (`Thor's Hammer`) is excellent for distributing large, static files (like GGUF model weights or container images), it is not suited for real-time, low-latency command-and-control communication between active agents. To build a self-organizing global brain, Syntropia incorporates a **hybrid P2P networking model**:

### A. Core Communication Contenders (Under Evaluation)
We are evaluating three decentralized communication protocols to drive agent-to-agent discovery and coordinate task routing:

1. **libp2p (The "Swiss Army Knife")**
   * *What it is*: A modular networking stack that powers IPFS and major blockchain networks.
   * *Why it fits*: It provides everything out-of-the-box: peer discovery via Kademlia DHT, encrypted real-time messaging via GossipSub, and native multi-transport support.
   * *Syntropia Role*: The primary transport for orchestrator-to-supervisor communication, state sync, and container health-monitoring gossip.

2. **WebRTC + Structured Overlays (The "Lightweight Browser Mesh")**
   * *What it is*: A web standard for direct peer-to-peer real-time communication.
   * *Why it fits*: It enables lower barriers to entry (running nodes inside browser extensions or web pages) with built-in NAT traversal and secure channels.
   * *Syntropia Role*: Ideal for lightweight/ephemeral volunteer workers to contribute idle browser-based compute cycles.

3. **DePIN Aggregators (The "Resource Virtualization OS")**
   * *What it is*: Platforms (e.g., 4EVER Network, Titan Agent) that virtualize and standardize CPU/GPU container executions across heterogeneous volunteer platforms.
   * *Why it fits*: Avoids reinventing low-level transport and scheduling layers. Handles multi-platform VM/container jailing out-of-the-box.
   * *Syntropia Role*: Plugs into our 1%-100% sacrifice daemon to manage standardized volunteer hardware contributions.

### B. The Hybrid Network Architecture
* **Real-Time Mesh Network (`libp2p`)**: Handles command-and-control, task routing, logical clocks, consensus, and metadata gossip.
* **Seeding Swarm (`BitTorrent`)**: Dedicated strictly to background loading and seeding of heavy assets (model weights, container images).

---

## 🛠️ Node Daemonization & Swarm Bootstrapping (Next Steps)

To transition the Syntropia node CLI from a foreground script to a robust, background system daemon, the following next steps are under consideration:

1. **Proper Logging Engine**: Replace standard `print()` statements in `main.py` with the Python `logging` module to support structured logs, console output formatting, and log-file rotation for long-term daemon runs.
2. **Centralized Configuration File**: Load tick rate (`bpm`), sacrifice slider `percentage`, and custom agent paths from a unified configuration file (`~/.config/syntropia/config.toml`) to allow users to persist their node choices.
3. **Systemd Service Daemon Mode**: Deploy a custom systemd service configuration (`syntropia.service`) so the overlay daemon runs silently in the background, starts automatically on CachyOS boot, and manages resource parameters without interactive terminal sessions.
4. **P2P Layer Initialization**: Integrate the libp2p/WebRTC network host in the main loop to handle peer handshakes, DHT lookups, and state sync gossip natively on node startup.
5. **Continuous Mutation Loop**: Spin up the `EvolutionEngine` in the background thread of `main.py` to continuously process task benchmarks and self-optimize CachyOS parameters over time.

---

## 🧭 Milestones: From Plan to Reality



| Phase | Task | Status |
| :--- | :--- | :--- |
| **Phase 1** | Host Profiling & Init Sandboxing | **Complete** (cachy_host.py implemented) |
| **Phase 2** | Wine, yabridge, and DAW Sync | **Complete** (automated sync and overrides) |
| **Phase 3** | 1%-100% Sacrifice Slider Daemon | **Complete** (dynamic load adjustment thread tracking) |
| **Phase 4** | Node Daemonization & Swarm Bootstrapping | **Not Started** (planned) |
| **Phase 5** | Full ISO Release & Distribution | **Not Started** (planned) |


