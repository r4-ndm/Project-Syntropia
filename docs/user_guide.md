# 🌀 Syntropia User Guide & Architecture Overview

> **"From one command to a living swarm."**

Welcome to Syntropia, a performance-tuned AI container overlay daemon for CachyOS and Arch Linux. Syntropia possesses the host system, injecting sub-millisecond audio tuning, sandboxed security, cgroup resource sacrifice limits, and a self-evolving AI swarm.

---

## 🧠 The Swarm Architecture (L0 to L4 Hierarchy)

To optimize resource usage across thousands of containers, Syntropia implements a tiered hierarchy of Hermes AI instances and deterministic script workers:

```
┌─────────────────────────────────────────────────────────┐
│  L4 BRAIN: Constitution + Blockchain                  │
│  - Unbreakable Rules (1–14)                             │
│  - sqlite3-based Bulletin Chain for mutations & reaps  │
└─────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────┐
│  L3 ORCHESTRATOR: Routing + Evolution + Healing        │
│  - Routes tasks to primary/fallback agents             │
│  - Spawns Healer Agents on failures                     │
│  - Triggers Resurrection if healing fails              │
└─────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────┐
│  L2 SUPERVISORS: Hermes (3B) + Specialized Agents     │
│  - Healer Agents (fix scripts)                        │
│  - yabridge/Wine managers                             │
│  - Audio optimizers                                    │
└─────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────┐
│  L1 MANAGERS: Hermes (0.5B)                           │
│  - Manage 1,000+ L0 worker scripts                     │
└─────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────┐
│  L0 WORKERS: Deterministic Scripts                     │
│  - Vaporized from AI traces (Rules 13 & 14)             │
│  - Fast, cheap, running without LLM overhead           │
└─────────────────────────────────────────────────────────┘
```

---

## 🛠️ Installation & Swarm Setup

Syntropia is packaged for Arch-based distributions (optimized for CachyOS). You can deploy the entire daemon node using the unified installer.

### 1. Automated Installation
Run the root-level installer:
```bash
git clone https://github.com/your-username/Project-Syntropia.git
cd Project-Syntropia
sudo ./install.sh
```

The installer performs the following actions:
1. Verifies the Arch-based host environment.
2. Installs dependencies (`python`, `psutil`, `pydantic`, `cryptography`, `toml`).
3. Creates an isolated system user `syntropia`.
4. Copies the codebase to `/opt/syntropia/` and configures defaults in `/etc/syntropia/config.toml`.
5. Registers and enables two systemd services:
   - `syntropia.service` (Core node daemon)
   - `syntropia-reaper.service` (Physical container reap daemon)

### 2. Manual Systemd Management
To inspect, start, or stop the services manually:
```bash
# Start/Restart services
sudo systemctl restart syntropia.service syntropia-reaper.service

# Check service status
sudo systemctl status syntropia.service
sudo systemctl status syntropia-reaper.service

# Live-tail logs
sudo journalctl -u syntropia.service -f
```

---

## 🔄 The Self-Healing Lifecycle (Rules 13 & 14)

Syntropia nodes reverse-age and optimize over time by compiling dynamic AI traces into fast, deterministic worker scripts, while protecting those scripts from decay.

```
AI Solves Task ──(Vaporization)──> Script Worker ──(Decay/Failure)──> Healer Agent
     ^                                                                   │
     │                                                              (Heal Successful)
     │                                                                   │
(Resurrect Fallback) <─────────────────── (Heal Fails) <─────────────────v
```

### Rule 13: Vaporization Protocol
When an active AI container successfully solves a task, the `VaporizationEngine` compiles the execution path into a static Python script. The script is:
1. Checked for compatibility against the Constitution.
2. Dry-run validated in a sandboxed namespace.
3. Cryptographically signed.
4. Broadcasted via the `P2PScriptRegistry` gossip network.
5. The container is physical reaped to free resources.

### Rule 14: Phoenix Resurrection Protocol
If a worker script breaks due to API changes or dependency drift:
1. **Failure Threshold**: After 3 failures, `HealerEngine` spawns a Healer Agent.
2. **Patching**: The Healer attempts to patch the script's syntax or imports in a sandbox.
3. **Phoenix Resurrection**: If healing fails or times out, the original AI agent is resurrected from the blockchain's vaporization records back into active routing, restoring the learning loop.

---

## 🧪 Developer Guide & Testing

All modules include extensive unit and integration tests covering the scheduler, yabridge synchronization, cgroups resource monitor, evolution engine, vaporization compilation, and the resurrection loops.

To run the complete test suite:
```bash
PYTHONPATH=src python -m unittest discover tests
```

To create a new agent:
1. Define your class inside `src/syntropia/` or the `agents/` directory.
2. Implement `execute(self, inputs)` and `name`/`role` attributes.
3. Register the agent in the `AgentRegistry` and verify that tests pass.
