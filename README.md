# 😈 Syntropia: The Living Computer

> *"From chaos, order. From order, life. From life, infinity .From infinity...... Gods of Syntropia 🐸."*

## ⚡ Install on an existing CachyOS

Turn any running CachyOS system into Syntropia OS in one line:

```bash
curl -fsSL https://raw.githubusercontent.com/r4-ndm/Project-Syntropia/main/install-syntropia.sh | bash
```

What it does: verifies CachyOS, clones this repo (and the shared brew registry,
best-effort), builds a Python venv, shows the full `syntropia transform --check`
plan, snapshots (when a snapper root config is available), and applies branding
+ audio stack with your confirmation.

> ⚠️ The repo is **private** right now, so the curl one-liner will not work for
> others until it goes public. Until then, run it from a clone you already have:
> `./install-syntropia.sh` (add `--check` for a dry run, `SYNTROPIA_YES=1` to
> skip the confirmation).

## 🧭 Navigation Guide for Agents

### **Quick Start**
- **Start Here**: `requirements.md` - Project vision and philosophy
- **Current Focus**: `phase1/` - Foundation being built by humans
- **Future Work**: `phase2/`, `phase3/` - AI integration and swarm evolution
- **Brainstorming**: `big-picture/` and `*/raw/` folders for ideas

### **Project Structure**
```
📁 Project-Syntropia/
├── 📄 requirements.md          # Core vision & philosophy
├── 📁 big-picture/            # Zoomed-out concepts & diagrams
├── 📁 phase1/                 # Human-built foundation (current)
│   ├── phase1-requirements.md # Technical specs
│   ├── plan.md               # Implementation strategy  
│   ├── tasks.md              # Concrete steps
│   ├── raw/                  # Brainstormed nuggets → requirements
│   └── [cli/, brews/, ...]   # Implementation directories
├── 📁 phase2/                 # AI integration (next)
│   ├── raw/                  # Ideas for AI protocols
│   └── README.md
├── 📁 phase3/                 # Swarm evolution (future)
│   ├── raw/                  # Future concepts
│   └── README.md
├── 📁 phase4/                 # Divine machine (vision)
│   └── raw/                  # Pure brainstorming
│       ├── bulletin-chain.md # Immutable ledger concept
│       └── ephemeral-storage.md # Distributed storage
```

### **Workflow for Agents**
1. **Check `requirements.md`** - Understand the Syntropia philosophy
2. **Review `big-picture/`** - See overall vision and connections  
3. **Work in current phase** (`phase1/` for now) - Follow plan.md and tasks.md
4. **Add ideas to `raw/`** - Brainstorm nuggets for future requirements
5. **When ready** - Compile `raw/` ideas into formal requirements

### **Core Principles**
- **"Trust the mutation. Never trust the boundary."** - Security model
- **Phase-based evolution** - Each phase builds on the last
- **Self-referential** - Syntropia will eventually build itself
- **OS-agnostic** - Starts with CachyOS, evolves to run anywhere

### **Current Status**
- **Phase 1**: ❌ Not started (human implementation)
- **Phase 2**: ✅ Prep done (awaiting Phase 1)
- **Phase 3**: ❌ Not started (brainstorming phase)
- **Phase 4**: 🌌 Vision phase (Bulletin Chain concepts in raw/)

### **Need Help?**
- Check `requirements.md` for philosophical questions
- Check `phase1/plan.md` for implementation strategy
- Add ideas to relevant `raw/` folder for future consideration

---

**Remember**: We're building a computer that grows, not just software that runs. 513😈
