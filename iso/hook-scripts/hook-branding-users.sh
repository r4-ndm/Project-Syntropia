#!/bin/bash
# hook-branding-users.sh — copy the terminal branding (fastfetch config + fish
# greeting) into the EXISTING target user homes during a Calamares install.
#
# Calamares creates the first user BEFORE the syntropia_branding shellprocess
# hook runs, so skel-only writes never reach that user (observed: fresh
# install had /etc/skel/.config/fastfetch but an empty ~/.config/fastfetch).
#
# WHY A SCRIPT? The Calamares shellprocess module expands every command string
# through KWordMacroExpander('$'), which treats BARE $word (not just ${word})
# as a macro. Shell variables like $h/$u are NOT in its dictionary, so a
# command containing them fails with "Missing variables: h,u" BEFORE anything
# runs — the branding hook silently did nothing and aborted the install.
# Script files are NOT macro-expanded, so all shell logic lives here.
#
# Runs in the LIVE env (the hook has dontChroot: true); $1 = ROOT = the
# target's mount point. The target's /etc/passwd is read for numeric uid/gid
# because the target user does not exist in the live env (chown by name would
# fail).
set -u
ROOT="${1:-/}"

for h in "$ROOT"/home/*; do
    [ -d "$h" ] || continue
    u="$(basename "$h")"

    mkdir -p "$h/.config/fastfetch" "$h/.config/fish"
    cp -a "$ROOT/etc/skel/.config/fastfetch/config.jsonc" "$h/.config/fastfetch/" 2>/dev/null
    cp -a "$ROOT/etc/skel/.config/fish/config.fish" "$h/.config/fish/" 2>/dev/null || true

    # chown numerically from the TARGET's passwd (the user exists there, not
    # in the live env); fall back to root if the user can't be resolved.
    uid="$(awk -F: -v u="$u" '$1==u{print $3; exit}' "$ROOT/etc/passwd" 2>/dev/null)"
    gid="$(awk -F: -v u="$u" '$1==u{print $4; exit}' "$ROOT/etc/passwd" 2>/dev/null)"
    if [ -n "${uid:-}" ] && [ -n "${gid:-}" ]; then
        chown -R "$uid:$gid" "$h/.config/fastfetch" "$h/.config/fish" 2>/dev/null || true
    fi
done

exit 0
