# 🍺 Brew Authoring Cookbook

Everything an agent needs to add, test, and ship a `.brew` manifest —
and to know where the pieces live. **Read this before touching brews.**

## The system map (how the pieces fit)

```
phase1/brews/*.brew        ← source of truth (committed to the repo)
        │  syntropia save <file.brew>
        ▼
~/.config/syntropia/brews/  ← the LOCAL registry (a git clone of the
        │                      shared r4-ndm/syntropia-brews repo)
        │  syntropia install <name>    → runs the brew (wine_helper engine)
        │  syntropia plugins sync      → bridges its VST3s into ~/.vst3/yabridge
        │  syntropia submit <name>     → PRs the brew to the shared registry
        ▼
r4-ndm/syntropia-brews     ← the shared registry (AUR-style upstream)
        │  syntropia update            → git pulls the registry + repo
        ▼
every user's ~/.config/syntropia/brews
```

| Command | What it does | Where the code lives |
|---|---|---|
| `syntropia save <file.brew>` | validate + copy a brew **verbatim** into the local registry | `brew.py` (`save_brew`) |
| `syntropia install <name> [--check] [--yes]` | run the install pipeline | `wine_helper.py` (`WineInstaller`) |
| `syntropia plugins sync` | bridge drop-folder VST3s via yabridge | `plugins.py` |
| `syntropia plugins link --data <Vendor>` | wire vendor data/registry into DAW prefixes | `vendor.py` |
| `syntropia submit <name>` | open a PR against the shared registry | `registry.py` |
| `syntropia update` | pull latest CLI + brews, re-apply transform | `update.py` |

**The registry is a byte-for-byte copy.** Editing `~/.config/syntropia/brews`
directly is a hack — edit `phase1/brews/` and re-run `syntropia save`.
`syntropia install` warns when the registry copy has drifted from the repo.

## Add a brew in 6 steps

1. **Copy the template** — `cp phase1/brews/template.brew phase1/brews/<slug>.brew`
   (slug = lowercase, hyphenated name, e.g. `serum.brew`, `fl-studio.brew`).
2. **Fill in the manifest** — `[brew]` identity, `[wine]` prefix/arch,
   `[source]` installer discovery, `[wine.overrides]` + `[winetricks]`
   (add them **only if the app needs them** — start minimal), `[install]`
   commands. One command per line, never jammed.
3. **`syntropia save phase1/brews/<slug>.brew`** — validates the manifest
   and copies it into the local registry.
4. **`syntropia install <slug> --check`** — dry-run: verifies the plan
   (toolchain, prefix, overrides, source discovery) without touching wine.
   It also surfaces lint problems early.
5. **`syntropia install <slug> --yes`** — real run. Test on a machine that
   has the installer downloaded (auto-discovered from `~/Downloads`).
6. **Verify end to end** — app launches, VST3s appear in the DAW. Then
   optionally `syntropia submit <slug>` to share it.

## Schema quick reference

Full spec with examples: **`phase1/plan.md` → “🍺 `.brew` Specification
Schema”**. The parser (`brew.py` → `_SECTION_FIELDS`) is the enforcement
point and is test-checked against the doc — keep them in sync.

```toml
[brew]           # required: name, version, category, maintainer
[source]         # optional: filename glob, url (download fallback), look_in dirs
[wine]           # required: version (see WINE_BUILD_BIN_DIRS), prefix, arch
[wine.overrides] # optional: DLL → builtin/disabled/native
[winetricks]     # optional: packages list
[yabridge]       # optional: enabled, plugin_dirs (default ~/VST3)
[environment]    # optional: free-form env vars for install + launcher
[vendor_data]    # optional: source prefix + vendors to link (Arturia-class)
[install]        # required: commands list (may be empty)
```

## Common pitfalls (learned the hard way)

- **Jammed commands** — two `"cmd one", "cmd two",` on one line fails lint.
  Split them. `test_no_jammed_install_commands` enforces this.
- **Registry staleness** — the local registry copy goes stale the moment you
  edit `phase1/brews/`. Re-run `syntropia save` or install warns.
- **Ableton wants bundles** — Live only scans `Plugin.vst3/Contents/x86_64-win/`
  layout; flat `.vst3` DLLs (Arturia, CRMBL) must be wrapped into bundles.
  Bitwig via yabridge accepts flat files.
- **Isolated prefixes** — every brew gets its own Wine prefix
  (`~/.local/share/syntropia/prefixes/<name>`). Plugins installed into one
  prefix (e.g. `~/.wine`) won't be seen by a DAW in another — that's what
  `vendor_data` / `plugins link --data` fixes.
- **Use the prefix's own wine for `reg add`** — a version-mismatched
  wineserver silently fails. `vendor.resolve_wine()` handles this.
- **Silent installers** — NSIS: `/S`, Inno: `/VERYSILENT /SUPPRESSMSGBOXES
  /NORESTART`. GUI installers hang headless — use `xvfb-run -a` if needed.
- **Empty command lists are legal** — a no-op brew (template with
  everything commented) must still parse.

## Agent checklist before committing a brew

- [ ] `python3 -m pytest tests/` passes (includes load-every-brew + lint).
- [ ] `syntropia save <slug>.brew` succeeds (validation is green).
- [ ] `syntropia install <slug> --check` shows a sensible plan.
- [ ] Real install verified on a test system, not just dry-run.
- [ ] Plan.md schema updated if you added a section/field (and the
      schema-consistency test extended).
