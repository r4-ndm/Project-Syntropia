# 😈 Syntropia

*"From chaos, order. From order, life."*

Syntropia is a **laptop-friendly everyday Linux for the Final Boss and music
producers**: a CachyOS re-skin (the same relationship Linux Mint has to Ubuntu)
with Syntropia branding, a first-boot apps wizard, and an audio-production layer
(Wine + yabridge VST3 workflow) on top.

- Base and packages: CachyOS repos. Long-term goal is a full fork; **not yet**.
- Identity (freedesktop derivative pattern):
  `ID=cachyos`, `VARIANT_ID=syntropia`, `PRETTY_NAME="CachyOS Syntropia"`.
- Desktop: **Hyprland (UWSM) + Noctalia only** — Plasma is not supported.
- Bootloader: **Limine**, both UEFI and BIOS.

## 🚀 Two ways to get Syntropia

**1. Install the ISO** (the shipped product, `iso/`): TUI installer on tty1,
keyboard → network → one password → LUKS2 + Btrfs → Limine → Hyprland.

**2. Transform an existing CachyOS** in place:

```bash
curl -fsSL https://raw.githubusercontent.com/r4-ndm/Project-Syntropia/main/install-syntropia.sh | bash
```

It verifies CachyOS, builds a Python venv, shows the full
`syntropia transform --check` plan, snapshots (when snapper is available), and
applies branding + audio stack after confirmation. Dry run: `./install-syntropia.sh --check`.
Read `agent-rules/transform-safety.md` before running it anywhere.

## 🧭 Repo map

```
AGENTS.md               agent entry point — read this first
NEXT_SESSION.md         mission + what is true + what is next (single source of truth)
agent-rules/            binding rules for every agent
.agents/skills/         how-to skills (iso-builder, aur-audit — Syntropia's own)
docs/                   HISTORY.md (past session evidence), GLOSSARY.md (project language)
phase1/                 the product
  cli/                    three Python packages: core CLI, brews (Wine engine), transform
  brews/                  bundled .brew manifests (Ableton, FL Studio, Serum, Vital, Surge)
  aur/                    the three AUR PKGBUILDs
  wizard/apps.list        first-boot app catalog (consumed by iso/build.sh)
  services/  tools/  tests/
iso/                    ISO pipeline
  build.sh                mkarchiso (phase 1) + squashfs remaster (phase 2)
  installer/              TUI installer source (syntropia-install, -runner, -dashboard, lib/)
  profiles/hyprland/      Syntropia overlay on stock CachyOS Hyprland/Noctalia
  hook-scripts/  lib/  vendor/  tests/
Branding/               logo, wallpaper, Calamares slides, Plymouth frames
install-syntropia.sh    one-line in-place installer
```

Future-phase planning (`phase2/`–`phase4/`, `phase1/raw/`) is gitignored and
local-only; it is not part of the repo.

## 🛠️ Common commands

```bash
python -m pytest -q phase1/tests iso/tests     # whole suite (~436 tests, ~10s)
./iso/installer/syntropia-install --dry-run    # preview the installer, touch nothing
sudo ./iso/build.sh                            # build the ISO (~15 min, see iso/README.md)
syntropia transform --check                    # branding diff, no changes
```

## 📚 Where to read next

| Need | Read |
|------|------|
| Session start, always | `AGENTS.md` → `agent-rules/` → `NEXT_SESSION.md` |
| ISO build, remaster, VM testing, boot pitfalls | `iso/README.md` + `.agents/skills/iso-builder/SKILL.md` |
| Adding or editing a `.brew` manifest | `phase1/brews/README.md` |
| Why a past decision was made | `docs/HISTORY.md` |
| What a project word means | `docs/GLOSSARY.md` |
| Why Syntropia exists at all | `big-picture/requirements.md` |

*Trust the mutation. Never trust the boundary.* 😈
