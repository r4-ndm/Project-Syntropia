# ⚡ Transform Safety

**Rule:** `syntropia transform` rewrites a live system. Treat it like surgery:
snapshot first, dry-run always, and never operate on a machine you're not
allowed to break.

## Golden rules

1. **Test systems only.** Never run a transform on a daily driver, a production
   machine, or any system the Final Boss hasn't designated as disposable. The
   designated test bed is the QEMU VM (`cachyos-syntropia-test`); physical
   hardware only with explicit approval.
2. **Snapshot before every transform.** `sudo snapper -c root create -d "pre-transform-<desc>"`
   must succeed **before** anything is changed. No snapshot → no transform.
3. **Dry-run first, always.** `syntropia transform --check` (or `--dry-run`) must
   run clean before the real thing. If the dry-run reports problems, fix them
   first — never "just try it and see".
4. **Never run a transform without the Final Boss saying so.** Writing the script
   is work; running it on a live system is an operation that needs explicit
   permission.
5. **Idempotent or nothing.** A transform must be safe to run twice. If it isn't
   idempotent yet, say so instead of running it.

## The checklist

**Before**
- [ ] Target is a designated test system
- [ ] Snapshot taken (`snapper -c root create`)
- [ ] Dry-run passed clean
- [ ] Final Boss approved

**During**
- [ ] Log everything (tee/journal) — never silence output
- [ ] Stop at the first error; no "keep going anyway"

**After**
- [ ] Verify the exit gates: boot works, shell prompt is the devil, PipeWire is
      running, CLI is present
- [ ] If anything broke → rollback (below)

## Rollback procedure

```bash
sudo snapper -c root list            # find the pre-transform snapshot
sudo snapper -c root rollback <num>  # restore it
sudo reboot                          # boot the restored system
```

The pristine baseline is snapshot **#19 ("pristine-after-install")** — the
reference state for a fresh test cycle.

## Remember

The VM was built to be broken. Break it, learn, roll back, break it again.
Never break the daily driver. 😈
