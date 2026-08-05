# Phase 1 — Services (reference)

Systemd units salvaged from the pre-rebuild planning docs (`old-docs/`, since removed)
to serve as a starting reference for this phase's `services.py` work.

**⚠️ Verify before shipping** — these predate the rebuild and reference a
`syntropia registry sync` command that does not exist yet. Use them as a shape to
follow, not as ready-to-ship units.

- `syntropia-registry-sync.service` — oneshot, read-only fetch of the recipe registry
- `syntropia-registry-sync.timer` — runs the sync daily

*Retrieved 2026-08-05.*
