# 🤖 Agent Rules

**To every agent — Freebuff, Hermes, subagents, and the future swarm:**

> **READ EVERY FILE IN THIS FOLDER AT THE START OF EVERY SESSION, BEFORE DOING ANY WORK.**

These rules are binding. They exist so the swarm makes consistent decisions without asking
the Final Boss the same questions twice. 😈

## Protocol

1. **Read all** `.md` files in this folder before the first task of a session.
2. **Apply them** to every task, even small ones. When a rule applies, cite it.
3. **Ambiguity** → ask the Final Boss (L5). Never guess when a rule could be interpreted two ways.
4. **Precedence:** explicit Final Boss instructions > these rules > habit. The Final Boss can override anything, but expect a follow-up question about why.
5. **Evolution:** rules are added here as the project learns. If a decision pattern repeats, it becomes a rule.

## Rules index

| File | What it decides |
|------|-----------------|
| [`software-inclusion-policy.md`](software-inclusion-policy.md) | Whether a package ships with Syntropia (base vs. tooling vs. opt-in) |
| [`git-hygiene.md`](git-hygiene.md) | When agents may commit, push, or rewrite history — and when to ask first |
| [`transform-safety.md`](transform-safety.md) | Running `syntropia transform`: snapshot first, dry-run always, test systems only, rollback |
| [`code-quality.md`](code-quality.md) | How code is written: modular, maintainable, battle-tested OSS first, Rust where practical |
| *(more rules to come — security boundary…)* |

## Skills (how-to guides — read when the workflow applies)

Rules decide **what** to do; skills explain **how**. Skills live in
`.agents/skills/<name>/SKILL.md` (Claude Code mirrors most via symlinks in
`.claude/skills/`). **Always check `.agents/skills/` before starting a recurring
workflow — the iso-builder one exists precisely because agents didn't know it was there.**

| Skill | Origin | Maintain? |
|-------|--------|-----------|
| `iso-builder` | **homegrown** — Syntropia-specific | ✅ YES — update in the same commit as any `iso/build.sh` / install-flow change |
| `cachyos-linux-assistant` | vendored (`purplem0n/linux-assistants`) | no — read-only |
| `arch-linux-triage` | vendored (`github/awesome-copilot`) | no — read-only |
| `cli-developer` | vendored (`jeffallan/claude-skills`) | no — read-only |

Vendored skills are pinned by hash in `skills-lock.json` — treat them as third-party
material. `iso-builder` is ours, lives under `.agents/skills/`, and is mirrored into
`.claude/skills/` via symlink; keep it in sync with reality.

## Note to agents

These rules apply to decisions about the **Syntropia product and repo**. When in doubt,
remember the constitution: *"Trust the mutation. Never trust the boundary."*

## Reference docs (read when relevant)

| Doc | When to read |
|-----|--------------|
| [`iso/README.md`](../iso/README.md) | **ISO build or VM test work.** Contains testing gotchas learned the hard way: Calamares must run as **root** (non-root launch → "Boost.Python error in job mount"), VM disk ≥ 8 GiB, slideshow only plays during the Install step, and how to verify the amended slides are in the ISO. Update it whenever the ISO build/test pipeline surfaces a new bug. |
| [`phase1/brews/README.md`](../phase1/brews/README.md) | **Any brew work** — adding, editing, testing, or submitting a `.brew` manifest. The 6-step add-a-brew flow, the registry/save/install/submit/update system map, and the pitfalls (jammed commands, stale registry copies, bundle layout, isolated prefixes). |
