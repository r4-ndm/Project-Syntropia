---
name: aur-audit
description: Audits a CachyOS/Arch machine's AUR usage against known-compromised packages and attack windows (Atomic Arch campaign and related waves). Use when the user asks to check whether installed AUR/foreign packages are compromised, audit the system after AUR malware reports, or vet the AUR before publishing packages.
---

# AUR Security Audit

Cross-checks the machine's foreign packages (`pacman -Qm`) against the community's
known-compromised AUR package lists and flags packages installed during the
Atomic Arch attack windows. Run this when:

- The user asks "are my AUR packages safe?", "check for compromised packages", or
  "audit the AUR packages on this machine"
- A new AUR supply-chain wave is reported (Arch freezes pushes, mailing-list warnings)
- The user is about to install or publish AUR packages and wants a hygiene check
- Anything in the paru/yay build cache looks off

## Quick start

```bash
# From the Syntropia repo root:
python3 phase1/tools/aur_audit.py             # core checks (~seconds)
python3 phase1/tools/aur_audit.py --commits  # + AUR git history scan (slow, one request per package)
python3 phase1/tools/aur_audit.py --json     # machine-readable report
```

Exit codes: `0` = clean, `1` = issues found, `2` = error.

## What the script checks (in order)

1. **Foreign packages** — `pacman -Qm` (anything not from an enabled repo).
2. **Compromised-list cross-check** — pulls the four lists from
   [lenucksi/aur-malware-check](https://github.com/lenucksi/aur-malware-check)
   (`aur-infected`, `packages-extra`, `chaos-rat`, `russian-spam`) and matches
   exact names **and** suffix-stripped names (`-bin`/`-git`/`-svn`/etc.). A
   `-bin` package whose base name is on the list is a fuzzy match.
3. **Build-cache scan** — looks for the campaign's payload names in
   `~/.cache/paru/` and `~/.cache/yay/`: `linter`, `hasher`, `minifier`,
   `validator`, `assembler`, `optimizer`, `*.elf`.
4. **Install-date window check** — flags packages installed inside the known
   attack windows (Wave 1 Jun 11–12, Wave 3 late Jul, write freeze Aug 1–11,
   2026). These need manual re-check even if not on a list yet (lists lag waves).
5. **`--commits`** — pulls each package's AUR git atom feed (latest commit
   date/author/title). The attack vector was *recent commits by unexpected
   authors*, so this catches packages that were pushed maliciously without
   their name ever reaching a list. Reports "not on AUR" for CachyOS-repo or
   deleted packages (e.g. `geocode-glib-2` — a CachyOS package, not AUR).

## Interpreting results

- **Exact/fuzzy match or suspicious binary** → `🔴 ISSUES FOUND`. Do not run
  more `paru -Syu` blindly; treat a *built* flagged package as potentially
  compromised. Per the Atomic Arch guidance: rotate credentials, regenerate
  SSH keys, consider a clean reinstall for a confirmed build.
- **Window flags only** → `🟠` amber. Likely innocent (e.g. `simple-scan-git`
  installed Jul 28 with a 2020 last commit), but verify by hand.
- **Clean** → still note the caveat: the lists were last updated **July 7, 2026**
  (before Wave 3), so absence from them is not an all-clear for very recent
  installs — the commit check closes most of that gap.

## Context: the AUR crisis (as of Aug 2026)

- **Jun 11** — Wave 1: ~1,500 packages compromised via orphan adoption; payloads
  ran `npm install atomic-lockfile` during builds (Rust credential stealer).
- **Jul 13** — registration reopened with hardened rules (no disposable emails,
  24h verification token).
- **Late Jul** — Wave 3: obfuscated JS downloaders + compiled ELF binaries, a
  Tor-backed Rust infostealer with RAT/SSH-worm capabilities targeting browser
  credentials, wallets, and **SSH keys**.
- **Aug 1** — repo-wide **write freeze** (pushes disabled).
- **Aug 11** — pushes restored under review gates (aurweb v6.5.0); **new account
  registration stays closed**. Adoption now requires Package Maintainer approval.

Implications for Syntropia: we cannot push our three packages (`syntropia-cli`,
`syntropia-brews`, `syntropia`) to the AUR until registration reopens. The
release tarball + `.SRCINFO` are ready; the block is purely the account.
Watch the **aur-general mailing list** for the reopening announcement.

## Pitfalls

- **The script must be run from the repo root** (it's `phase1/tools/aur_audit.py`).
- **Never run the script as root** for the checks — `pacman -Qm` and cache scans
  work fine as a normal user. No elevated privileges are needed.
- Network hiccups degrade gracefully: if the lists can't be fetched the script
  warns and skips that step (don't read "clean" from a skipped step — re-run).
- The `--commits` scan is one HTTPS request per package; on a loaded AUR
  (Anubis anti-bot wall) some fetches may fail — those show as `(fetch failed)`.
- Keep the pure logic (`cross_check`, `flag_install_windows`, `normalize`) free
  of network/pacman calls — `phase1/tests/test_aur_audit.py` pins that contract
  so the matching can't silently regress.

## Typical workflow

1. `python3 phase1/tools/aur_audit.py` — core check; if clean, done.
2. If amber flags: run `--commits` on the flagged packages (or all) and inspect
   each latest-commit line for anomalous authors/dates.
3. Report exact matches / suspicious binaries / window flags separately —
   they have very different severities. Cite what was found, never just "clean".
4. If the user is about to publish to the AUR: mention the registration status
   and that the three PKGBUILDs are pre-verified (see `phase1/aur/`).
