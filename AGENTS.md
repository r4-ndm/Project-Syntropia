# AGENTS.md

**To every AI agent working on this repo — read this at the start of every session, before any task.**

This is the Syntropia project. Before doing anything:

1. Read **`NEXT_SESSION.md`** — mission, current status, next work (single source of truth).
2. Read **`agent-rules/README.md`** and **every file** in the `agent-rules/` folder.
3. Skim **`docs/GLOSSARY.md`** — the project's own words (two of them, "brew" and
   "transform", mean something different here than you'd guess).
4. Apply those rules to all work. Cite them when they apply.
5. The human (L5 Final Boss) can override any rule, but if you're about to break one, say so first.

## Where things live

| Path | What it is |
|------|-----------|
| `phase1/cli/` | Three Python packages: core CLI, brews (Wine/VST3 engine), transform (branding) |
| `phase1/brews/` | Bundled `.brew` manifests |
| `phase1/aur/` | The three AUR PKGBUILDs |
| `phase1/tests/`, `iso/tests/` | pytest suite — 436 tests, run both |
| `iso/build.sh` | ISO build: mkarchiso (phase 1) + squashfs remaster (phase 2) |
| `iso/installer/` | TUI installer source — never move this logic into `build.sh` heredocs |
| `iso/profiles/hyprland/` | Syntropia overlay on stock Hyprland/Noctalia (no hand-rolled dotfiles) |
| `Branding/` | Logo, wallpaper, Calamares slides, Plymouth frames |
| `docs/HISTORY.md` | Past session evidence — read when you need the "why", not for instructions |

## Commands

```bash
python -m pytest -q phase1/tests iso/tests     # full suite, ~10s
./iso/installer/syntropia-install --dry-run    # preview installer, no disk changes
sudo ISO_SKIP_... ./iso/build.sh               # see iso/README.md for the real flags
syntropia transform --check                    # never --yes on the host box
```

Before any ISO or install-flow change, read `.agents/skills/iso-builder/SKILL.md`.
Before any recurring workflow, check `.agents/skills/` — it is usually already documented.

*Trust the mutation. Never trust the boundary.* 😈
