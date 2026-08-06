#!/usr/bin/env bash
#
# Syntropia one-liner installer
# -----------------------------
# Turns an existing CachyOS system into Syntropia OS: clones the repo,
# builds a venv, then runs `syntropia transform --snapshot --yes` with
# the branding assets from the repo.
#
#   curl -fsSL https://raw.githubusercontent.com/r4-ndm/Project-Syntropia/main/install-syntropia.sh | bash
#
# The repo is private right now — until it goes public, fetch the script
# from a clone you already have (or `gh repo clone r4-ndm/Project-Syntropia`
# and run ./install-syntropia.sh inside it).
#
# Safety (matches agent-rules/transform-safety.md):
#   * `--check` prints the full plan and changes nothing.
#   * The real run prints the plan, asks for confirmation, snapshots
#     (when snapper is available), and only then applies.
#   * `SYNTROPIA_YES=1` skips the confirmation prompt.
#   * `FORCE=1` skips the CachyOS distribution check.
#
# Env overrides:
#   SYNTROPIA_SRC      where to clone/expect the repo  (default ~/syntropia)
#   SYNTROPIA_REPO_URL git URL to clone                 (default the GitHub repo)
#   SYNTROPIA_BRANCH   branch to clone                  (default main)
#   SYNTROPIA_YES=1    skip confirmation
#   FORCE=1            skip the distribution check
#
set -euo pipefail

REPO_URL="${SYNTROPIA_REPO_URL:-https://github.com/r4-ndm/Project-Syntropia}"
BRANCH="${SYNTROPIA_BRANCH:-main}"
SRC="${SYNTROPIA_SRC:-$HOME/syntropia}"
MODE="${1:---install}"   # --check | --install

P="\033[1;36m[syntropia]\033[0m"

say() { printf "%b %s\n" "$P" "$*"; }
die() { printf "%b \033[1;31merror:\033[0m %s\n" "$P" "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1; }

# -- 1. distribution guard ----------------------------------------------
if [[ "${FORCE:-0}" != "1" ]]; then
    # Accept a plain CachyOS box or one already branded by a previous
    # transform (which rewrites /etc/os-release to ID=syntropia).
    if [[ ! -f /etc/os-release ]] \
        || ! grep -qE '^ID=(cachyos|syntropia)' /etc/os-release; then
        die "this looks like it is not CachyOS — transform targets CachyOS. Re-run with FORCE=1 to override (at your own risk)."
    fi
    say "CachyOS/Syntropia detected ✓"
else
    say "distribution check skipped (FORCE=1)"
fi

# -- 2. tool requirements ------------------------------------------------
MISSING=()
need git          || MISSING+=(git)
need python3      || MISSING+=(python)
if need python3; then
    python3 -c 'import venv, ensurepip' 2>/dev/null || MISSING+=(python-virtualenv)
fi
if [[ ${#MISSING[@]} -gt 0 ]]; then
    say "installing missing tools: ${MISSING[*]}"
    if [[ "${MODE}" == "--check" ]]; then
        say "[--check] would install: ${MISSING[*]}"
    else
        # No bare `sudo -v` here: it demands a terminal even when NOPASSWD
        # is configured. Let pacman itself prompt (or use NOPASSWD).
        sudo -n true 2>/dev/null || say "sudo will prompt for your password"
        sudo pacman -S --noconfirm --needed "${MISSING[@]}"
    fi
fi

python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
    || die "Python 3.11+ is required"

# -- 3. obtain the source ------------------------------------------------
if [[ -d "$SRC/.git" ]]; then
    say "repo already at $SRC — updating"
    if ! git -C "$SRC" fetch --quiet origin "$BRANCH" 2>/dev/null; then
        say "warning: could not fetch updates for $SRC (offline or private?) — using the existing checkout"
    else
        git -C "$SRC" checkout --quiet "$BRANCH" 2>/dev/null || true
        git -C "$SRC" pull --quiet --ff-only origin "$BRANCH" 2>/dev/null || true
    fi
elif [[ -f "$SRC/phase1/cli/pyproject.toml" ]]; then
    say "using existing source at $SRC (not a git checkout)"
else
    if [[ "${MODE}" == "--check" ]]; then
        say "[--check] would clone $REPO_URL -> $SRC"
    else
        say "cloning $REPO_URL -> $SRC"
        git clone --quiet --branch "$BRANCH" "$REPO_URL" "$SRC"
    fi
fi
[[ -f "$SRC/phase1/cli/pyproject.toml" ]] || die "no syntropia package found in $SRC"

# -- 4. venv + install ----------------------------------------------------
VENV="$SRC/.venv"
if [[ ! -x "$VENV/bin/syntropia" ]]; then
    say "building venv"
    if [[ "${MODE}" == "--check" ]]; then
        say "[--check] would create $VENV and pip install -e $SRC/phase1/cli"
    else
        python3 -m venv "$VENV"
        "$VENV/bin/pip" install --quiet --upgrade pip
        "$VENV/bin/pip" install --quiet -e "$SRC/phase1/cli"
    fi
fi
[[ -x "$VENV/bin/syntropia" ]] || die "venv build did not produce syntropia — run the installer without --check first, then re-run with --check for the plan"

BRANDING="$SRC/Branding/syntropia"

# -- 5. plan --------------------------------------------------------------
say "transform plan (--check):"
sudo -n true 2>/dev/null && SUDO_HINT="" || SUDO_HINT="(sudo will prompt)"
if [[ "${SUDO_HINT}" ]]; then say "note: ${SUDO_HINT}"; fi
"$VENV/bin/syntropia" transform --check --branding-dir "$BRANDING"

if [[ "${MODE}" == "--check" ]]; then
    say "dry-run complete — nothing was changed."
    say "to apply for real, run the installer again without --check (SYNTROPIA_YES=1 skips the confirmation)"
    exit 0
fi

# -- 6. snapshot capability ----------------------------------------------
# Gate on the snapper root config, not just the binary: a non-btrfs box can
# have snapper installed but no working config — better to skip than to let
# the transform hard-fail on the snapshot.
SNAP_ARGS=()
if need snapper && [[ -f /etc/snapper/configs/root ]]; then
    SNAP_ARGS=(--snapshot "one-liner-$(date +%Y%m%d-%H%M%S)")
    say "snapper found — will snapshot before applying"
else
    say "warning: no working snapper root config (non-btrfs?) — skipping the pre-transform snapshot"
fi

# -- 6b. brew registry (AUR-style, best-effort) ---------------------------
# Make the wrap-up hint true: install-by-name needs the shared registry
# cloned. Best-effort — the repo is private right now, so warn on failure.
REGISTRY_DIR="$HOME/.config/syntropia/brews"
if [[ ! -d "$REGISTRY_DIR/.git" ]]; then
    if [[ "${MODE}" == "--check" ]]; then
        say "[--check] would clone the shared brew registry -> $REGISTRY_DIR"
    elif git clone --quiet https://github.com/r4-ndm/syntropia-brews.git "$REGISTRY_DIR" 2>/dev/null; then
        say "brew registry ready: $REGISTRY_DIR"
    else
        say "warning: could not clone the brew registry — run 'git clone https://github.com/r4-ndm/syntropia-brews.git $REGISTRY_DIR' later"
    fi
fi

# -- 7. confirmation ------------------------------------------------------
if [[ "${SYNTROPIA_YES:-0}" != "1" ]]; then
    say "This will modify your system (packages, branding, prompt, PipeWire)."
    printf "%b Type 'yes' to continue: " "$P"
    if ! read -r answer < /dev/tty; then
        die "no terminal for confirmation — re-run with SYNTROPIA_YES=1 to skip"
    fi
    [[ "$answer" == "yes" ]] || die "aborted (expected 'yes')"
fi

# -- 8. apply --------------------------------------------------------------
say "applying (sudo): syntropia transform --yes ..."
sudo -n true 2>/dev/null || say "sudo will prompt for your password"
# Keep the venv on PATH so `syntropia` resolves for the CLI deploy step.
sudo env "PATH=$PATH:$VENV/bin" "$VENV/bin/syntropia" \
    transform --yes "${SNAP_ARGS[@]}" --branding-dir "$BRANDING"

# -- 9. wrap-up ------------------------------------------------------------
say "✅ done — this system is now Syntropia OS. 🌀"
say "try:  syntropia install surge --check   (from the shared brew registry)"
say "log out and back in to see the new prompt."
