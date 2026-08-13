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

# --- Start-menu (Kickoff) icon ---
# The stock CachyOS panel points the Kickoff applet at icon=org.cachyos.hello.
# Install our menu-icon.png into the target's hicolor theme as syntropia-menu
# and repoint the panel config — in BOTH /etc/skel (future users) and each
# EXISTING target user home (Calamares created the first user before this
# hook, so skel-only writes never reach them).
menu_src="$ROOT/usr/share/syntropia/branding/menu-icon.png"
if [[ -f "$menu_src" ]]; then
    menu_dst="$ROOT/usr/share/icons/hicolor/256x256/apps"
    mkdir -p "$menu_dst"
    cp -a "$menu_src" "$menu_dst/syntropia-menu.png"
fi
for appsrc in "$ROOT/etc/skel/.config/plasma-org.kde.plasma.desktop-appletsrc" "$ROOT"/home/*/.config/plasma-org.kde.plasma.desktop-appletsrc; do
    if [[ -f "$appsrc" ]] && grep -q 'icon=org.cachyos.hello' "$appsrc"; then
        sed -i 's/icon=org.cachyos.hello/icon=syntropia-menu/' "$appsrc"
    fi
done

# --- KSplash theme (triangle mark -> Plasma logo -> boot) ---
# Install the Syntropia splash into the target's look-and-feel and point
# ksplashrc at it, for BOTH /etc/skel (future users) and each EXISTING
# target user home (the first user is created before this hook runs).
splash_src="$ROOT/usr/share/syntropia/branding/splash"
if [[ -d "$splash_src" ]]; then
    for h in "$ROOT/etc/skel" "$ROOT"/home/*; do
        [ -d "$h" ] || continue
        theme_dir="$h/.local/share/plasma/look-and-feel/org.syntropia.desktop/contents/splash"
        mkdir -p "$(dirname "$theme_dir")"
        rm -rf "$theme_dir"
        cp -a "$splash_src" "$theme_dir"
        printf '[KSplash]\nEngine=KSplashQML\nTheme=org.syntropia.desktop\n' > "$h/.config/ksplashrc"
        # chown numerically from the TARGET passwd (see fastfetch loop above).
        u="$(basename "$h")"
        uid="$(awk -F: -v u="$u" '$1==u{print $3; exit}' "$ROOT/etc/passwd" 2>/dev/null)"
        gid="$(awk -F: -v u="$u" '$1==u{print $4; exit}' "$ROOT/etc/passwd" 2>/dev/null)"
        if [ -n "${uid:-}" ] && [ -n "${gid:-}" ]; then
            chown -R "$uid:$gid" "$h/.local/share/plasma/look-and-feel/org.syntropia.desktop" "$h/.config/ksplashrc" 2>/dev/null || true
        fi
    done
fi

# --- Identity sync: limine bootloader ---
# The bootloader was generated at install time with the CachyOS name (the
# rename to Syntropia happens at the END of install, after the bootloader
# step), so limine-snapper-sync can't match its OS entry against the renamed
# os-release and warns on every boot. Sync both sides:
#   1) limine.conf's OS entry name  /+CachyOS -> /+Syntropia OS
#   2) TARGET_OS_NAME in /etc/default/limine, so the match never depends on
#      PRETTY_NAME/NAME drifting.
if [[ -f "$ROOT/boot/limine.conf" ]] && grep -q '/+CachyOS' "$ROOT/boot/limine.conf"; then
    sed -i 's|/+CachyOS|/+Syntropia OS|' "$ROOT/boot/limine.conf"
fi
if [[ -f "$ROOT/etc/default/limine" ]] && ! grep -q '^TARGET_OS_NAME' "$ROOT/etc/default/limine"; then
    printf 'TARGET_OS_NAME="Syntropia OS"\n' >> "$ROOT/etc/default/limine"
fi

exit 0
