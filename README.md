# 😈 Syntropia: The Living Computer

> *"From chaos, order. From order, life. From life, infinity .From infinity...... Gods of Syntropia 🐸."*

## 🧬 Identity

Syntropia is a **CachyOS re-skin** today — the same relationship Linux Mint has
to Ubuntu. It keeps CachyOS as the base system (`ID=cachyos`,
`VARIANT_ID=syntropia`, `PRETTY_NAME="CachyOS Syntropia"`), pulls packages from
the cachyos repos, and layers Syntropia branding, the apps wizard, and the audio
stack on top. The `VARIANT_ID` pattern follows the freedesktop standard for
derivative distros (same as Fedora Silverblue). The long-term goal is a full
fork with our own repos; until then, updates and the package base stay CachyOS.

Syntropia targets CachyOS's **KDE Plasma** edition: the desktop branding
(start-menu icon, KSplash, SDDM autologin) is Plasma-only, while the boot
splash (Plymouth), GRUB, and OS identity are desktop-agnostic.

## ⚡ Install on an existing CachyOS

Turn any running CachyOS system into Syntropia OS in one line:

```bash
curl -fsSL https://raw.githubusercontent.com/r4-ndm/Project-Syntropia/main/install-syntropia.sh | bash
```

What it does: verifies CachyOS, clones this repo (and the shared brew registry,
best-effort), builds a Python venv, shows the full `syntropia transform --check`
plan, snapshots (when a snapper root config is available), and applies branding
+ audio stack with your confirmation.

> The curl one-liner installs from the public repo. For a dry run first:
> `./install-syntropia.sh --check` (or `SYNTROPIA_YES=1` to skip the
> confirmation).

## 🧭 Navigation Guide for Agents

### **Quick Start**
- **Start Here**: `requirements.md` - Project vision and philosophy
- **Binding rules**: `agent-rules/` - READ EVERY FILE at session start (git hygiene, transform safety, software inclusion)
- **How-to skills**: `.agents/skills/` - iso-builder, cachyos-linux-assistant, arch-linux-triage, cli-developer
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
