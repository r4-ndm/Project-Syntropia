# Phase 1 — Services (shipped systemd units)

Units installed by the Syntropia packages (syntropia-cli and syntropia-brews).
All are read-only / non-destructive by design.

- `syntropia-registry-sync.service` + `.timer` — daily, read-only git fetch of the
  recipe registry cache (`syntropia registry sync`). Shipped by **syntropia-brews**.
- `syntropia-aur-audit.service` + `.timer` — weekly AUR security audit
  (`/usr/bin/aur-audit`, the `phase1/tools/aur_audit.py` script): cross-checks
  foreign packages against the known-compromised lists, scans build caches, and
  flags installs inside attack windows. Exit code 1 (issues found) surfaces the
  unit via `systemctl --failed`. Shipped by **syntropia-cli**.

None of these execute recipes, install software, or touch Wine. Enable a timer
explicitly — the packages install the units but do not start them:

```bash
sudo systemctl enable --now syntropia-registry-sync.timer
sudo systemctl enable --now syntropia-aur-audit.timer
```
