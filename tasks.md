# Project Syntropia: Task Board & Open Questions 🌀

This document tracks the current implementation status of Syntropia's modules, completed tasks, upcoming phases, and new open architectural problems that need to be solved by the community.

---

## ✅ Completed Tasks
- [x] **Repository Architecture Setup**: Defined the folder layouts (`agents/`, `src/syntropia/`, `docs/`, `.github/`).
- [x] **Community Foundations**:
  - `README.md` introducing the Swarm Intelligence manifesto and core Torrent concepts.
  - `CONTRIBUTING.md` outlining the environment setup and agent submission rules.
  - `CODE_OF_CONDUCT.md` using the Contributor Covenant.
  - `LICENSE` under the MIT format.
- [x] **GitHub Community Templates**: Added templates for Bug Reports, Feature Requests, and New Agent Proposals under `.github/ISSUE_TEMPLATE/`.
- [x] **Proof-of-Concept Agent**: Added `agents/math/add/` showing a simple rule-based agent structure (`manifest.json` and `agent.py`).
- [x] **MIDI Sync Architecture Spec**: Created the synchronization and sonification mapping in `docs/midi_sync.md`.
- [x] **TUI Dashboard Spec**: Designed the native terminal user interface layout in `docs/architecture/tui_dashboard.md`.
- [x] **Agent Manifest Loader (`src/syntropia/registry.py`)**: Completed dynamic agent discovery and loading from the `agents/` folder.
- [x] **Binary Analyzer Agent (`agents/binary_analyzer/`)**: Completed pure-Python ELF, PE, and Mach-O parser with RVA translations, caching, and CLI tool fallback.
- [x] **Tick Engine (`src/syntropia/engine.py`)**: Local event loop using logical clock coordination (Lamport Timestamps) syncable to a MIDI Clock pulse (24 PPQN).
- [x] **Orchestrator Heartbeat & Routing (`src/syntropia/orchestrator.py`)**: Implemented heartbeat routing pipeline (Primary -> Fallback) with automatic reputation updates and thread-safe asynchronous execution.
- [x] **Cryptographic Trust Anchor (`src/syntropia/crypto.py`)**: Implemented BIP32/SLIP10-like HD key derivation, Ed25519 signing, and verification.
- [x] **Constitution Rule Engine (`src/syntropia/constitution.py`)**: Completed a hardcoded 12-rule checking module to govern agent mutations.
- [x] **SQLite Bulletin Chain (`src/syntropia/blockchain.py`)**: Created an SQLite-based content-addressable storage (CAS) and block-chained registry log.
- [x] **Reputation Ledger (Phase 2)**: Added on-chain reputation ledger scoring and automatic adjustment triggers.

---

## 🏃 In Progress (Phase 1: Torrent & P2P Layer)

---

## 📅 Phase 1: Torrent & P2P Layer
- [ ] **DHT Peer Discovery**: Implementing Kademlia-based peer discovery (no central tracker) to find nodes hosting specific agent roles.
- [ ] **Thor's Hammer Sync Engine (`src/syntropia/thor_hammer.py`)**: Wrapping a client engine (e.g. using `libtorrent` or calling a background helper) to fetch model weights via magnet links.
- [ ] **Hardware Probe**: Automatically diagnosing RAM and CPU availability on boot to select the best model weight tier (Ultra-light, Light, Medium, Heavy).
- [ ] **Interactive TUI Dashboard**: Creating the unified console dashboard monitor inside `src/main.py`.

---

## 📅 Phase 2: Trust & Evolution
- [ ] **Consensus Verification**: 3-way redundant validation for critical computation paths.
- [ ] **Evolution Engine (`src/syntropia/evolution.py`)**: Genetic algorithms tweaking agent timeouts, reproducing high-fitness nodes, and pruning degraded ones.

---

## 🧠 New Open Questions (Community Challenge)
We need developers, systems architects, and contributors to help solve these next-level architectural challenges:

### 1. Agent Versioning & Upgrades
* *Problem*: As agents evolve and their logic is updated, different nodes might run conflicting versions.
* *Question*: How do we push updates without a central server? Should we implement Git-like semantic versioning inside `manifest.json` and a "version negotiation" protocol between requesting and executing peers?

### 2. State Persistence & Migration
* *Problem*: Some agents (e.g., storage or database agents) accumulate execution state. If their host node goes offline, that state is lost.
* *Question*: Should we implement state partitioning and active replication (similar to Kafka partitions) across peer groups, or save encrypted state snapshots directly to a DHT storage layer?

### 3. Incentive Mechanism
* *Problem*: Volunteering compute power is passion-driven, but incentivization increases network scale and stability.
* *Question*: Should we implement an optional crypto-incentive layer (like a utility token) rewarding nodes that seed models and execute tasks, or keep the network fully non-commercial?
