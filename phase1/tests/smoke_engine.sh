#!/usr/bin/env bash
# Engine smoke test — proves the syntropia install pipeline end to end on
# ANY machine with the toolchain installed (wine, winetricks, yabridgectl).
#
# What it does, against an isolated scratch prefix that it deletes on exit:
#   1. --check dry-run reaches the full plan (all pipeline steps present)
#   2. --yes real run: wineboot provisions the prefix, overrides are
#      persisted to the registry, and the brew's install commands run
#   3. verifies the artifacts (system.reg, DLL overrides, marker file)
#
# Offline-friendly: the smoke brew downloads nothing. To also exercise the
# winetricks step, uncomment [winetricks] in engine-smoke.brew first.
#
# Usage (from anywhere):
#   phase1/tests/smoke_engine.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BREW="$REPO_ROOT/phase1/tests/engine-smoke.brew"
PREFIX="$HOME/.local/share/syntropia/prefixes/engine-smoke-test"
CLI=(env PYTHONPATH="$REPO_ROOT/phase1/cli" python3 -m syntropia.cli)
PTY_TS="$(mktemp)"

# Run the CLI under a PTY (via `script`) so the spinner animates on a real
# terminal, while still capturing the full session for verification.
# Without the PTY, `2>&1` pipes would make the CLI's stderr.isatty() False
# and it would fall back to static lines — no animation.
#
# `script` echoes the live session to its stdout (the user's terminal sees
# it), and logs the same bytes to the typescript file.  We must NOT capture
# script's stdout in $() — that would swallow the live view.  Instead read
# the typescript file after the run for verification.
run_cli_pty() {
    # SHELL=/bin/sh avoids sourcing the user's login profile (which would
    # print noise like version-manager banners) into the session.
    SHELL=/bin/sh script -qec "$1" "$PTY_TS" || true
}

cleanup() {
    # Kill any wineserver for the scratch prefix, then remove it.
    if [[ -d "$PREFIX" ]]; then
        WINEPREFIX="$PREFIX" wineserver -k 2>/dev/null || true
        sleep 1
        rm -rf "$PREFIX"
    fi
    rm -f "$PTY_TS"
}
trap cleanup EXIT

echo "==> smoke_engine: ${BREW#*phase1/}"

# ── 0. Toolchain pre-check (fail fast with a helpful message) ──────────
missing=()
for tool in wine winetricks yabridgectl script; do
    command -v "$tool" >/dev/null 2>&1 || missing+=("$tool")
done
if ((${#missing[@]})); then
    echo "ERROR: missing toolchain: ${missing[*]} — run 'sudo syntropia transform' first" >&2
    exit 1
fi
echo "    toolchain: wine, winetricks, yabridgectl present"

# ── 1. Dry-run: the plan must cover every pipeline step ────────────────
# The PTY run streams the CLI's own progress to the terminal (spinner and
# step order visible live) while still capturing for verification.
echo "==> dry-run (--check)"
run_cli_pty "${CLI[*]} install '$BREW' --check"
plan="$(cat "$PTY_TS")" || true
if ! grep -q "Dry-run complete" <<<"$plan"; then
    echo "ERROR: dry-run did not produce an install plan:" >&2
    echo "$plan" >&2
    exit 1
fi
for step in Toolchain Prefix Overrides Winetricks Yabridge Source Install Vendor Sync; do
    grep -q "$step" <<<"$plan" || { echo "ERROR: dry-run plan missing step '$step'" >&2; exit 1; }
done
echo "    plan covers all 9 pipeline steps"

# ── 2. Real run ────────────────────────────────────────────────────────
echo "==> real run (--yes) — wineboot + overrides + install commands"
if [[ -e "$PREFIX" ]]; then
    echo "ERROR: scratch prefix already exists: $PREFIX (remove it first)" >&2
    exit 1
fi
run_cli_pty "${CLI[*]} install '$BREW' --yes"
out="$(cat "$PTY_TS")" || true
if ! grep -q "installed into" <<<"$out"; then
    echo "ERROR: install did not complete:" >&2
    exit 1
fi
echo "    install completed"

# ── 3. Verify artifacts ────────────────────────────────────────────────
echo "==> verifying artifacts"
[[ -f "$PREFIX/system.reg" ]] || { echo "ERROR: system.reg missing — prefix not provisioned" >&2; exit 1; }
grep -q '"d2d1"="builtin"' "$PREFIX/user.reg" || { echo "ERROR: d2d1 override not persisted" >&2; exit 1; }
grep -q '"winemenubuilder.exe"="d"' "$PREFIX/user.reg" || { echo "ERROR: winemenubuilder override not persisted" >&2; exit 1; }
[[ "$(cat "$PREFIX/smoke/marker.txt" 2>/dev/null)" == "engine works" ]] || { echo "ERROR: install marker missing or wrong" >&2; exit 1; }
echo "    prefix provisioned (system.reg present)"
echo "    DLL overrides persisted (d2d1, winemenubuilder.exe)"
echo "    install commands ran (marker: $(cat "$PREFIX/smoke/marker.txt"))"

echo ""
echo "✅ ENGINE SMOKE TEST PASSED"
