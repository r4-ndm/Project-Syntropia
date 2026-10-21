#!/bin/bash
# hook-branding-users.sh — install Syntropia branding into the EXISTING target
# user homes and the target rootfs during a Calamares install.
#
# Scope: fastfetch/fish terminal branding, the Plasma start-menu icon + KSplash
# theme, the Plymouth triangle boot animation, and the limine OS-entry identity
# sync. GRUB/bootloader theming is deliberately left vanilla CachyOS (limine) —
# the only boot changes are the Syntropia name and the Plymouth theme (matching
# `syntropia transform`, which leaves GRUB untouched).
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
    cp -a "$ROOT/etc/skel/.config/fastfetch/config.jsonc" "$h/.config/fastfetch/" 2>/dev/null || true
    cp -a "$ROOT/etc/skel/.config/fish/config.fish" "$h/.config/fish/" 2>/dev/null || true

    # Deploy Noctalia and Hyprland Syntropia profile overlays
    if [[ -d "$ROOT/etc/syntropia/profiles/hyprland/.config" ]]; then
        mkdir -p "$ROOT/etc/skel/.config" "$h/.config"
        cp -r "$ROOT/etc/syntropia/profiles/hyprland/.config/"* "$ROOT/etc/skel/.config/" 2>/dev/null || true
        cp -r "$ROOT/etc/syntropia/profiles/hyprland/.config/"* "$h/.config/" 2>/dev/null || true
    fi

    # chown numerically from the TARGET's passwd (the user exists there, not
    # in the live env); fall back to root if the user can't be resolved.
    uid="$(awk -F: -v u="$u" '$1==u{print $3; exit}' "$ROOT/etc/passwd" 2>/dev/null)"
    gid="$(awk -F: -v u="$u" '$1==u{print $4; exit}' "$ROOT/etc/passwd" 2>/dev/null)"
    if [ -n "${uid:-}" ] && [ -n "${gid:-}" ]; then
        chown -R "$uid:$gid" "$h/.config" 2>/dev/null || true
    fi
done

# Deploy Hyprland / Noctalia profile helper tools to /usr/local/bin
if [[ -d "$ROOT/etc/syntropia/profiles/hyprland/bin" ]]; then
    mkdir -p "$ROOT/usr/local/bin"
    cp -a "$ROOT/etc/syntropia/profiles/hyprland/bin/"* "$ROOT/usr/local/bin/" 2>/dev/null || true
    chmod +x "$ROOT/usr/local/bin"/syntropia-* 2>/dev/null || true
fi

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

# --- KSplash theme (pure triangle mark) ---
# Install the Syntropia splash into the target's look-and-feel and point
# ksplashrc at it, for BOTH /etc/skel (future users), each EXISTING target user home,
# and the system-wide cachyos theme fallback.
splash_src="$ROOT/usr/share/syntropia/branding/splash"
if [[ -d "$splash_src" ]]; then
    # Overwrite system-wide look-and-feel fallback themes
    mkdir -p "$ROOT/usr/share/plasma/look-and-feel/cachyos/contents/splash" "$ROOT/usr/share/plasma/look-and-feel/org.syntropia.desktop/contents/splash"
    cp -a "$splash_src/." "$ROOT/usr/share/plasma/look-and-feel/cachyos/contents/splash/"
    cp -a "$splash_src/." "$ROOT/usr/share/plasma/look-and-feel/org.syntropia.desktop/contents/splash/"
    for h in "$ROOT/etc/skel" "$ROOT"/home/*; do
        [ -d "$h" ] || continue
        theme_dir="$h/.local/share/plasma/look-and-feel/org.syntropia.desktop/contents/splash"
        mkdir -p "$(dirname "$theme_dir")"
        rm -rf "$theme_dir"
        cp -a "$splash_src" "$theme_dir"
        printf '[KSplash]\nEngine=none\nTheme=None\n' > "$h/.config/ksplashrc"
        # chown numerically from the TARGET passwd (see fastfetch loop above).
        u="$(basename "$h")"
        uid="$(awk -F: -v u="$u" '$1==u{print $3; exit}' "$ROOT/etc/passwd" 2>/dev/null)"
        gid="$(awk -F: -v u="$u" '$1==u{print $4; exit}' "$ROOT/etc/passwd" 2>/dev/null)"
        if [ -n "${uid:-}" ] && [ -n "${gid:-}" ]; then
            chown -R "$uid:$gid" "$h/.local/share/plasma/look-and-feel/org.syntropia.desktop" "$h/.config/ksplashrc" 2>/dev/null || true
        fi
    done
fi

# --- Plymouth boot animation (triangle particle swarm) ---
# Install the Syntropia boot-animation theme into the target and make it the
# active Plymouth theme (overriding CachyOS's cachyos-bootanimation, which a
# CachyOS package installs and selects at install time). Calamares' initramfs
# step runs after this hook and rebuilds the initramfs, so the theme is picked
# up and the animation actually plays at boot.
plymouth_src="$ROOT/usr/share/syntropia/branding/plymouth"
if [[ -d "$plymouth_src" ]]; then
    plymouth_dst="$ROOT/usr/share/plymouth/themes/syntropia"
    rm -rf "$plymouth_dst"
    mkdir -p "$(dirname "$plymouth_dst")"
    cp -a "$plymouth_src" "$plymouth_dst"
    # Also overwrite cachyos theme directory directly as a safety override
    cachyos_plymouth="$ROOT/usr/share/plymouth/themes/cachyos"
    if [[ -d "$cachyos_plymouth" ]]; then
        rm -rf "$cachyos_plymouth"/*
        cp -a "$plymouth_src/." "$cachyos_plymouth/"
    fi
    mkdir -p "$ROOT/etc/plymouth"
    printf '[Daemon]\nTheme=syntropia\n' > "$ROOT/etc/plymouth/plymouthd.conf"
fi

# --- Identity & theme sync: limine bootloader ---
# limine-snapper-sync matches limine.conf's OS entry name against os-release
# PRETTY_NAME (or TARGET_OS_NAME in /etc/default/limine); a mismatch warns on
# every boot. The two installers name the entry differently — CachyOS' own
# installer writes `/+CachyOS`, our runner writes `/+CachyOS Syntropia`, and
# Calamares' limine module takes the name from branding.desc
# (`bootloaderEntryName: Syntropia`) — so normalise every known spelling:
#   1) limine.conf's OS entry -> `/+CachyOS Syntropia` (= PRETTY_NAME)
#   2) TARGET_OS_NAME in /etc/default/limine, so the match never depends on
#      PRETTY_NAME/NAME drifting
#   3) Skin limine interface with Syntropia branding & dark palette
# Every step is idempotent: the hook runs on every install, and rewriting an
# already-correct entry must be a no-op.
for limine_cfg in "$ROOT/boot/limine.conf" "$ROOT/boot/limine/limine.conf" "$ROOT/boot/efi/limine.conf"; do
    if [[ -f "$limine_cfg" ]]; then
        # `#` as the delimiter: the pattern itself contains `|` alternation.
        sed -i -E \
            's#^/(\+)?(CachyOS|Syntropia|Syntropia OS|CachyOS Syntropia)[[:space:]]*$#/+CachyOS Syntropia#' \
            "$limine_cfg"
        if ! grep -q 'interface_branding:' "$limine_cfg"; then
            sed -i '1s|^|interface_branding: Syntropia Bootloader\ninterface_branding_color: bd93f9\nterm_background: 0f1017\n\n|' "$limine_cfg"
        fi
    fi
done

# Create the file when the limine package did not ship one: an explicit
# TARGET_OS_NAME beats relying on the os-release parse.
mkdir -p "$ROOT/etc/default"
if ! grep -q '^TARGET_OS_NAME' "$ROOT/etc/default/limine" 2>/dev/null; then
    printf 'TARGET_OS_NAME="CachyOS Syntropia"\n' >> "$ROOT/etc/default/limine"
fi

# --- USB Removal Notification ---
# Notify the user on the live desktop that installation is complete and they must remove the USB stick before rebooting.
if command -v kdialog >/dev/null 2>&1; then
    kdialog --title "Syntropia OS Installation Complete" --msgbox "Installation of Syntropia OS is complete!

Please REMOVE your USB installation flash drive before restarting your computer." 2>/dev/null &
elif command -v notify-send >/dev/null 2>&1; then
    notify-send -u critical "Syntropia OS Installation Complete" "Please REMOVE your USB installation flash drive before restarting your computer." 2>/dev/null || true
fi

exit 0
