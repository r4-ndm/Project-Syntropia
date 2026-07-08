# 🌀 Project Syntropia: Implementation & Community Plan

> **"Computing Beyond Quantum. Infinity Intelligence."**
>
> Syntropia is a prototype of a **living computer**—a general-purpose computing environment built not from static instructions, but from a self-assembling swarm of simple, specialized, and evolving AI/rule-based agents.

This document merges the core conceptual roadmap with the community onboarding structure, detailing our immediate next steps, folder layouts, and P2P torrent-based Edge AI syncing design.

---

## 🌌 The Vision: Torrent-Powered Swarm Intelligence

Instead of hosting heavy model files on centralized servers, Syntropia uses **P2P Torrent Swarms** to distribute agent logic and model weights.

### 🌐 How It Works
1. **Weight Distribution**: Lightweight models (e.g., Qwen-2.5-0.5B-Instruct at ~950MB) are distributed via magnet links. This is too big for standard GitHub repositories but perfect for BitTorrent.
2. **BitTorrent Integration**:
   - The CLI client contains a background BitTorrent engine (using Python `libtorrent` or wrapping a Node/CLI daemon inspired by Thor Hammer).
   - When a node needs a specialized agent, it checks if the model weights (.gguf format) are present locally. If not, it pulls them from the torrent swarm.
   - Once downloaded, the node automatically seeds to others, making the global network more resilient as new peers join.
3. **Agent Manifests**: A decentralized registry tracks magnet links for each model type.

---

## 📂 Planned Repository Structure

We will lay out the repository to make it clean, modular, and easy for new developers to drop in their own agent designs:

```text
Project-Syntropia/
├── .github/
│   └── ISSUE_TEMPLATE/          # Bug reports, feature requests, new agent proposals
│       ├── bug_report.md
│       ├── feature_request.md
│       └── new_agent_proposal.md
├── agents/                      # Contributor-submitted agent definitions
│   ├── math/                    # Arithmetic agents
│   │   ├── add/
│   │   │   ├── manifest.json    # Defines role, timeout, model=null
│   │   │   └── agent.py         # Pure-logic summation code
│   │   ├── multiply/
│   │   └── divide/
│   ├── memory/                  # Key-value storage agents
│   ├── reasoning/               # Edge LLM prompt templates (Qwen, OLMo)
│   │   └── qwen_0.5b/
│   │       ├── manifest.json    # Magnet link, timeout, role definition
│   │       └── prompt.py        # Prompt structure and output parsing
│   └── network/                 # P2P communication agents
├── src/
│   ├── syntropia/
│   │   ├── __init__.py
│   │   ├── engine.py            # Tick engine, system clock
│   │   ├── orchestrator.py      # Router, heartbeat supervisor, fallback logic
│   │   ├── thor_hammer.py       # BitTorrent downloader/seeder wrapper
│   │   ├── registry.py          # Agent discovery and manifest management
│   │   └── evolution.py         # Fitness scoring, replication, pruning
│   └── main.py                  # Interactive CLI / onboarding tool
├── tests/                       # Unit and integration tests
├── docs/                        # Whitepaper, architecture, roadmap
├── README.md                    # The front door / recruiter pitch
├── CONTRIBUTING.md              # Contributor guidelines
├── CODE_OF_CONDUCT.md           # Contributor Covenant
├── LICENSE                      # MIT license file
└── pyproject.toml               # Package dependencies (libtorrent, llama-cpp)
```

---

## 🛠️ Onboarding Plan (Join the Swarm in 3 Steps)

1. **Clone and install**:
   ```bash
   git clone https://github.com/[your-username]/Project-Syntropia.git
   cd Project-Syntropia
   pip install -r requirements.txt
   ```
2. **Start Node**: `python src/main.py --start-node`. The client initializes, checks local GGUF models, and uses Thor Hammer to fetch any missing models via magnet links.
3. **Submit an Agent**: Create a new folder in `agents/`, write a Python class, define `manifest.json`, and open a Pull Request.

---

## 🎯 Immediate Implementation Tasks

### 1. Repository Core Configuration Files
- Create the **README.md** incorporating the Syntropia Manifesto and quick start instructions.
- Create the **CONTRIBUTING.md** defining agent standards, coding style (PEP8/Black), and pull request instructions.
- Create the **CODE_OF_CONDUCT.md** using the Contributor Covenant standard.
- Create the **LICENSE** (MIT).

### 2. GitHub Issue Templates
Write file templates in `.github/ISSUE_TEMPLATE/` to guide community feedback:
- `bug_report.md`
- `feature_request.md`
- `new_agent_proposal.md`

### 3. Proof of Concept Agent
Create a basic arithmetic agent (`agents/math/add/agent.py`) and its `manifest.json` as a template for contributors:
```python
class AdditionAgent:
    def __init__(self):
        self.role = "addition"
        self.timeout = 2  # ticks
    
    def execute(self, inputs):
        return sum(inputs)
```
```json
{
  "role": "addition",
  "timeout": 2,
  "model": null,
  "description": "Adds two or more numbers together"
}
```

### 4. Code Skeleton
Initialize the package structure under `src/` to prepare for coding the tick engine, orchestrator, and P2P torrent client.
