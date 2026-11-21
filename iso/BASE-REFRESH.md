# CachyOS base refresh log

One line per phase-1 refresh, appended in the same commit as the build (see
`.agents/skills/iso-builder/SKILL.md` → "Base refresh policy"). Format:

```
YYYY-MM-DD  base=HEAD@<upstream-commit-short>  breakage=none  (or: what broke)
```

```
2026-11-19  base=HEAD@b0ebcae  breakage=none so far (hardware re-test pending; upstream churn was package-list only: -staging and linux-atm dropped, ghostty/kmscon terminfo added)
```
