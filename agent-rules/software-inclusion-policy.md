# 📦 Software Inclusion Policy

**Rule:** Every package considered for Syntropia must run through the checklist below.
No package enters the base image without a recorded decision. This prevents scope creep
in Week 4 when the ISO starts accumulating "useful" packages. 😈

## The three tiers

Every package lives in exactly **one** tier:

| Tier | Home | Policy |
|------|------|--------|
| **1. Base** | Installed by `syntropia transform`, baked into the Seed ISO | Only what the **default user** needs out of the box |
| **2. Tooling dependency** | Declared by the Syntropia tool that needs it (`syn`, registry sync, brew engine…) | Used by Syntropia's own machinery — declared where used, not added to base casually |
| **3. Opt-in** | A brew, an optional package, or a documented one-liner | The default for anything not universally needed |

## The checklist

Run every package through all six. A single **NO** at any point is not fatal — it
just means the package moves down a tier.

1. **Default-user test** — does the *target user* (Phase 1: producer/musician) need this on day one? Not the developer — the user.
2. **Dependency test** — does Syntropia's own tooling hard-depend on it? If yes, it's Tier 2 (declare it in that tool), not necessarily Tier 1.
3. **Alternative test** — could it ship as a brew, an optional group, or a documented one-liner instead? Cheaper is better.
4. **Cost test** — size, dependency tree, attack surface, and update burden vs. actual value. Rule 2: *waste not, want not*.
5. **Context test** — is it *build-time* (ISO builder, CI) or *runtime* (the image)? Build-time tools never belong in the image.
6. **Consent test** — does it need auth/config to be useful? Preinstalled-but-unconfigured is cruft, not a feature.

## Worked examples

| Package | Verdict | Tier | Why |
|---------|---------|------|-----|
| `git` | ✅ | 1 | Infrastructure. Brew registry + `syn` helper + updates all need it. |
| `pipewire`, `wireplumber` | ✅ | 1 | The entire point of the OS — audio. |
| `wine-staging`, `yabridge`, `winetricks` | ✅ | 1 | Core of `syntropia install <brew>`; the product *is* Wine plugin management. |
| `fastfetch` | ✅ | 1 | Branding (logo banner) is a Phase 1 deliverable. |
| `gh` (GitHub CLI) | ❌ | 3 | Default user doesn't need it; tooling works with git + SSH keys. Only a future `syn publish` feature would declare it as Tier 2. |
| `openssh` | ⚠️ | 2 | Needed by dev tooling / remote work, not by the music user. Ship with the dev tooling, not base. |

## Recording decisions

When a new package is proposed, append the verdict to the table with the reasoning.
If the answer ever changes (new feature, new user segment), update the row — decisions
are living, like the constitution.
