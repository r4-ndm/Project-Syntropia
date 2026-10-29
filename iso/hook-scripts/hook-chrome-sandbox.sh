#!/bin/bash
# Make the Chromium-family sandbox helper a root-owned setuid binary.
# ==================================================================
# Brave (and Chromium, and google-chrome) ship a `chrome-sandbox` helper that
# the browser hard-requires: it must be owner root, group root and mode 4755.
# Installed by pacman/AUR without that, the browser exits at startup (or renders
# a blank window) with "The SUID sandbox helper binary was found, but is not
# configured correctly" — the 2026-10-25 laptop install hit exactly that after
# the apps wizard installed brave-bin. The upstream fix is this permission, NOT
# a --no-sandbox wrapper: --no-sandbox turns off the process sandbox for the
# whole browser, which is a security regression, not a fix.
#
# Runs as a pacman hook (PostTransaction, root) whenever a package installs a
# chrome-sandbox, so Brave is usable the moment the wizard finishes, and by hand
# as `syntropia-fix-chrome-sandbox [path...]`. Idempotent: an already-correct
# helper is left untouched.
#
# AUR brave-bin installs under /opt/brave-bin (the wizard's pick) or
# /opt/brave.com depending on the PKGBUILD revision, the repo brave package
# under /usr/lib/brave; every known path (plus chromium's and Chrome's) is
# checked, so a repack that drops the setuid bit cannot escape the hook.

set -euo pipefail

SANDBOX_PATHS=(
    /opt/brave-bin/chrome-sandbox
    /opt/brave.com/brave/chrome-sandbox
    /usr/lib/brave/chrome-sandbox
    /usr/lib/brave-bin/chrome-sandbox
    /opt/google/chrome/chrome-sandbox
    /usr/lib/chromium/chrome-sandbox
)

# Explicit args win (manual use); otherwise use the known install locations.
if (($# > 0)); then
    paths=("$@")
else
    paths=("${SANDBOX_PATHS[@]}")
fi

for path in "${paths[@]}"; do
    [[ -f "$path" ]] || continue
    current="$(stat -c '%U:%G %a' "$path")"
    if [[ "$current" == "root:root 4755" ]]; then
        continue
    fi
    chown root:root "$path"
    chmod 4755 "$path"
    echo "chrome-sandbox: $path fixed to root:root 4755 (was $current)"
done
