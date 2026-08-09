#!/usr/bin/env bash
# 😈 Syntropia Apps Wizard — first-boot "pick your favorites" installer
#
# Shows a zenity checklist built from a favorites catalog, then installs the
# checked packages with paru (which handles both official-repo and AUR
# packages) and shows the live output in a terminal window.
#
# The catalog is a plain-text list — see apps.list next to this script.
# Users can override the system catalog with their own copy at
# ~/.config/syntropia/apps.list. The wizard prefers, in order:
#   1. --config FILE
#   2. ~/.config/syntropia/apps.list   (user override)
#   3. /etc/syntropia/apps.list        (system default)
#   4. apps.list next to this script   (bundled fallback)
#
# Modes:
#   (no args)             run the interactive wizard
#   --once                run, but exit quietly if already completed
#   --check               non-interactive sanity check (exit 0 = all good)
#   --list                print the resolved catalog
#   --config FILE         use FILE as the catalog
#   --dialog TOOL         force a specific dialog tool (kdialog|zenity)
#   --setup               seed ~/.config/syntropia/apps.list (editable copy),
#                         install the one-shot autostart entry
#   --install-autostart   install the one-shot autostart entry
#   --remove-autostart    remove the autostart entry
#
# Dependencies: kdialog (native KDE/Plasma look — CachyOS default desktop)
# or zenity (fallback), paru (installs; bootstrapped if missing), a terminal
# emulator (live install output). Nothing else.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
AUTOSTART_DIR="$CONFIG_HOME/autostart"
DONE_MARKER="$CONFIG_HOME/syntropia/apps-wizard.done"
BUNDLED_CATALOG="$SCRIPT_DIR/apps.list"
DESKTOP_TEMPLATE="$SCRIPT_DIR/syntropia-apps.desktop"

MODE="interactive"
CATALOG=""
DIALOG_TOOL=""

die() { echo "😈 error: $*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

mark_done() {
    mkdir -p "$(dirname "$DONE_MARKER")"
    touch "$DONE_MARKER"
}

# ---------- helpers ----------

dialog_geometry() {
    # Fixed size, centered on the screen when the resolution is known — so
    # every category dialog opens in the same place instead of the window
    # manager cascade-placing each new window elsewhere.
    local size="${1:-600x420}"
    local line w h
    line="$(xrandr --current 2>/dev/null | grep -m1 'current ')" || { echo "$size"; return; }
    w="$(sed -n 's/.*current \([0-9]*\) x \([0-9]*\).*/\1/p' <<< "$line")"
    h="$(sed -n 's/.*current \([0-9]*\) x \([0-9]*\).*/\2/p' <<< "$line")"
    [[ -n "$w" && -n "$h" ]] || { echo "$size"; return; }
    local dw="${size%%x*}" dh="${size#*x}" px py
    px=$(( (w - dw) / 2 ))
    py=$(( (h - dh) / 3 ))
    (( px < 0 )) && px=0
    (( py < 0 )) && py=0
    echo "${size}+${px}+${py}"
}

# ---------- web apps ----------

web_launcher_path() {
    # ~/.local/share/applications/syntropia-<slug>.desktop
    local slug
    slug="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | tr -cs '[:alnum:]' '-' | sed 's/^-*//; s/-*$//')"
    echo "${XDG_DATA_HOME:-$HOME/.local/share}/applications/syntropia-$slug.desktop"
}

create_web_launcher() {
    local name="$1" url="$2" launcher exec_line
    launcher="$(web_launcher_path "$name")"
    # Dedicated app window: chromium-family --app=URL; firefox falls back to
    # a normal window; xdg-open as last resort.
    if have brave; then
        exec_line="brave --app=$url"
    elif have chromium; then
        exec_line="chromium --app=$url"
    elif have firefox; then
        exec_line="firefox --new-window $url"
    else
        exec_line="xdg-open $url"
    fi
    mkdir -p "$(dirname "$launcher")"
    cat > "$launcher" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=$name (Web)
Comment=Web app: $url
Exec=$exec_line
Icon=applications-internet
Terminal=false
Categories=Network;
X-Syntropia-WebApp=true
EOF
    echo "  ✅ $name  →  $launcher"
}

# kdialog is the native Plasma dialog (renders with the CachyOS/Breeze
# theme); zenity is the GTK fallback for non-KDE desktops.
find_dialog() {
    if [[ -n "$DIALOG_TOOL" ]]; then
        have "$DIALOG_TOOL" || die "dialog tool not found: $DIALOG_TOOL (use kdialog or zenity)"
        echo "$DIALOG_TOOL"
        return
    fi
    have kdialog && { echo "kdialog"; return; }
    have zenity && { echo "zenity"; return; }
    return 1
}

usage() {
    sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
}

# ---------- catalog ----------

resolve_catalog() {
    if [[ -n "$CATALOG" ]]; then
        [[ -f "$CATALOG" ]] || die "catalog not found: $CATALOG"
        echo "$CATALOG"
        return
    fi
    local user_catalog="$CONFIG_HOME/syntropia/apps.list"
    if [[ -f "$user_catalog" ]]; then echo "$user_catalog"; return; fi
    if [[ -f /etc/syntropia/apps.list ]]; then echo "/etc/syntropia/apps.list"; return; fi
    echo "$BUNDLED_CATALOG"
}

# Loads the catalog into the parallel arrays names/pkgs/cats and sets CAT_FILE.
load_catalog() {
    CAT_FILE="$(resolve_catalog)"
    [[ -f "$CAT_FILE" ]] || die "no catalog found (looked for: $CAT_FILE)"
    names=(); pkgs=(); cats=()
    local line cat name pkg desc
    while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line%%#*}"                 # strip comments
        [[ -z "${line//[[:space:]]/}" ]] && continue
        IFS='|' read -r cat name pkg desc <<< "$line"
        [[ -z "$pkg" ]] && continue
        names+=("$name"); pkgs+=("$pkg"); cats+=("$cat")
    done < "$CAT_FILE"
    [[ ${#names[@]} -gt 0 ]] || die "catalog '$CAT_FILE' has no app entries"
}

# ---------- prerequisites ----------

find_terminal() {
    [[ -n "${TERMINAL:-}" ]] && have "$TERMINAL" && { echo "$TERMINAL"; return; }
    local t
    for t in konsole gnome-terminal xfce4-terminal kitty alacritty xterm; do
        have "$t" && { echo "$t"; return; }
    done
    return 1
}

launch_terminal() {
    # $1 = shell command string to run inside the terminal
    local term cmd
    term="$(find_terminal)" || return 1
    case "$term" in
        konsole)        cmd=("konsole" "-e" "bash" "-c" "$1") ;;
        gnome-terminal) cmd=("gnome-terminal" "--" "bash" "-c" "$1") ;;
        xfce4-terminal) cmd=("xfce4-terminal" "-x" "bash" "-c" "$1") ;;
        kitty)          cmd=("kitty" "bash" "-c" "$1") ;;
        alacritty)      cmd=("alacritty" "-e" "bash" "-c" "$1") ;;
        xterm)          cmd=("xterm" "-e" "bash" "-c" "$1") ;;
        *)
            # custom terminal via $TERMINAL — assume the common -e convention
            [[ -n "${TERMINAL:-}" ]] || return 1
            cmd=("$term" "-e" "bash" "-c" "$1") ;;
    esac
    nohup "${cmd[@]}" >/dev/null 2>&1 &
}

ensure_paru() {
    local dialog="$1"
    have paru && return 0
    echo "paru (the AUR helper) is not installed."
    if [[ "$MODE" == "check" ]]; then return 1; fi
    if [[ "$dialog" == "kdialog" ]]; then
        kdialog --title "😈 Syntropia" \
            --yesno "paru (the AUR helper) is not installed yet.\n\nInstall it first? (a password prompt will appear)" \
            --yes-label "Install paru" --no-label "Cancel"
    else
        zenity --question --title="😈 Syntropia" \
            --text="paru (the AUR helper) is not installed yet.\n\nInstall it first? (a password prompt will appear)" \
            --ok-label="Install paru" --cancel-label="Cancel"
    fi
    if [[ $? -eq 0 ]]; then
        pkexec pacman -S --noconfirm paru
    fi
    have paru || die "paru is required to install apps"
}

# ---------- modes ----------

list_mode() {
    load_catalog
    echo "Catalog: $CAT_FILE"
    local i
    for i in "${!names[@]}"; do
        local pkg_display="${pkgs[$i]}"
        [[ "$pkg_display" == http* ]] && pkg_display="web: $pkg_display"
        printf '  %-28s %-28s %s\n' "${names[$i]}" "$pkg_display" "${cats[$i]}"
    done
}

check_mode() {
    load_catalog
    echo "😈 Syntropia Apps Wizard — check"
    echo "  catalog:     $CAT_FILE ($((${#names[@]})) apps)"
    echo
    local i missing=0 cur=""
    for i in "${!names[@]}"; do
        if [[ "${cats[$i]}" != "$cur" ]]; then
            cur="${cats[$i]}"
            echo "  [$cur]"
        fi
        if [[ "${pkgs[$i]}" == http* ]]; then
            if [[ -f "$(web_launcher_path "${names[$i]}")" ]]; then
                printf '    [launcher]    %-26s %s\n' "${names[$i]}" "${pkgs[$i]}"
            else
                printf '    [add launcher] %-24s %s\n' "${names[$i]}" "${pkgs[$i]}"
            fi
        elif pacman -Q "${pkgs[$i]}" >/dev/null 2>&1; then
            printf '    [installed] %-28s %s\n' "${names[$i]}" "${pkgs[$i]}"
        else
            printf '    [available] %-28s %s\n' "${names[$i]}" "${pkgs[$i]}"
        fi
    done
    echo
    echo "  toolchain:"
    printf '    dialog    %s\n' "$(find_dialog || echo MISSING)"
    printf '    paru      %s\n' "$(have paru && echo ok || echo MISSING)"
    printf '    terminal  %s\n' "$(find_terminal || echo MISSING)"
    echo
    find_dialog >/dev/null || missing=1
    have paru || missing=1
    find_terminal >/dev/null || missing=1
    [[ $missing -eq 0 ]] && echo "✅ all prerequisites present" || echo "❌ install the missing pieces above"
    return $missing
}

run_dialog() {
    local dialog
    dialog="$(find_dialog)" || die "neither kdialog nor zenity is installed — the wizard needs one (sudo pacman -S kdialog zenity)"
    ensure_paru "$dialog"

    # Force the Breeze widget style for kdialog on non-Plasma desktops so
    # checkboxes render with the KDE look (their GTK platform theme paints
    # them invisibly). On a Plasma session the native style is already active.
    if [[ "$dialog" == "kdialog" && -z "${KDE_FULL_SESSION:-}" ]]; then
        export QT_STYLE_OVERRIDE=breeze
    fi

    # Unique categories, in catalog order — one checklist dialog per category
    # (kdialog checklists are flat lists; a dialog per category is the native
    # way to show sections).
    local cat_order=() c cc seen i idx args out row name
    for i in "${!names[@]}"; do
        c="${cats[$i]}"
        seen=0
        for cc in "${cat_order[@]}"; do
            [[ "$cc" == "$c" ]] && seen=1 && break
        done
        (( seen )) || cat_order+=("$c")
    done

    local selected=()
    for c in "${cat_order[@]}"; do
        idx=()
        for i in "${!names[@]}"; do
            [[ "${cats[$i]}" == "$c" ]] && idx+=("$i")
        done
        (( ${#idx[@]} )) || continue

        if [[ "$dialog" == "kdialog" ]]; then
            # per item: tag (returned), label (displayed), state —
            # so tag=package, label=display name
            args=(kdialog --title "😈 Syntropia — $c" --geometry "$(dialog_geometry 600x420)" --separate-output
                --checklist "Pick your $c apps.\nCancel skips this category.")
            for i in "${idx[@]}"; do
                args+=("${pkgs[$i]}" "${names[$i]}" on)
            done
        else
            args=(zenity --list --checklist --separator='|'
                --title="😈 Syntropia — $c"
                --text="Pick your $c apps.\nCancel skips this category."
                --geometry="$(dialog_geometry 520x400)"
                --column="Install" --column="App")
            for i in "${idx[@]}"; do
                args+=(TRUE "${names[$i]}")
            done
        fi

        if ! out="$("${args[@]}")"; then
            continue   # cancelled this category — move to the next
        fi

        while IFS= read -r row; do
            [[ -z "$row" ]] && continue
            if [[ "$dialog" == "kdialog" ]]; then
                # each returned line is the package tag directly
                selected+=("$row")
            else
                # zenity: strip the checkbox state, then map name → package
                [[ "$row" == TRUE\|* || "$row" == FALSE\|* ]] && row="${row#*|}"
                name="${row%%|*}"
                for i in "${!names[@]}"; do
                    if [[ "${names[$i]}" == "$name" ]]; then
                        selected+=("${pkgs[$i]}")
                        break
                    fi
                done
            fi
        done <<< "$out"
    done

    if [[ ${#selected[@]} -eq 0 ]]; then
        echo "Nothing selected — nothing installed."
        if [[ "$MODE" == "once" ]]; then mark_done; fi
        exit 0
    fi

    # split picks into native packages and web-app URLs
    local native=() web_names=() web_urls=() pkg idx
    for pkg in "${selected[@]}"; do
        if [[ "$pkg" == http* ]]; then
            idx=-1
            for i in "${!pkgs[@]}"; do
                [[ "${pkgs[$i]}" == "$pkg" ]] && idx=$i && break
            done
            if (( idx >= 0 )); then
                web_names+=("${names[$idx]}")
                web_urls+=("$pkg")
            fi
        else
            native+=("$pkg")
        fi
    done

    if [[ ${#native[@]} -gt 0 ]]; then
        echo "Installing packages: ${native[*]}"
        local inner="paru -S --noconfirm ${native[*]}; rc=\$?; echo; if [ \$rc -eq 0 ]; then echo '✅ Done — press Enter to close'; else echo '❌ paru exited with \$rc — press Enter to close'; fi; read -r _"
        if launch_terminal "$inner"; then
            echo "Install running in a terminal window."
        else
            echo "No terminal emulator found — run this in a terminal instead:"
            echo "  paru -S --noconfirm ${native[*]}"
        fi
    fi
    if [[ ${#web_urls[@]} -gt 0 ]]; then
        echo "Creating web app launchers:"
        for i in "${!web_urls[@]}"; do
            create_web_launcher "${web_names[$i]}" "${web_urls[$i]}"
        done
    fi
    if [[ "$MODE" == "once" ]]; then mark_done; fi
}

install_autostart() {
    [[ -f "$DESKTOP_TEMPLATE" ]] || die "desktop template not found: $DESKTOP_TEMPLATE"
    mkdir -p "$AUTOSTART_DIR"
    sed "s|@SCRIPT@|$SCRIPT_DIR/syntropia-apps-wizard.sh|" "$DESKTOP_TEMPLATE" > "$AUTOSTART_DIR/syntropia-apps.desktop"
    echo "Autostart entry installed: $AUTOSTART_DIR/syntropia-apps.desktop"
    echo "It will run once on your next login."
}

remove_autostart() {
    rm -f "$AUTOSTART_DIR/syntropia-apps.desktop"
    echo "Autostart entry removed."
}

setup_mode() {
    # Seed the user's editable catalog from the best available default
    # (system default, else bundled) — never from the user copy itself.
    mkdir -p "$CONFIG_HOME/syntropia"
    local user_catalog="$CONFIG_HOME/syntropia/apps.list"
    local source=""
    if [[ -f /etc/syntropia/apps.list ]]; then
        source="/etc/syntropia/apps.list"
    elif [[ -f "$BUNDLED_CATALOG" ]]; then
        source="$BUNDLED_CATALOG"
    fi
    [[ -n "$source" ]] || die "no default catalog found to seed from"

    if [[ -f "$user_catalog" ]]; then
        echo "Your editable catalog already exists — leaving it untouched:"
        echo "  $user_catalog"
    else
        cp "$source" "$user_catalog"
        echo "Seeded your editable catalog:"
        echo "  $user_catalog"
    fi

    install_autostart

    echo
    echo "To add apps, edit the catalog — one line per app:"
    echo "  category|display name|package|description"
    echo "Then run: $SCRIPT_DIR/syntropia-apps-wizard.sh"
    echo "The wizard picks up your copy automatically. Delete"
    echo "  $DONE_MARKER"
    echo "to show the dialog again."
}

# ---------- main ----------

while [[ $# -gt 0 ]]; do
    case "$1" in
        --check) MODE="check"; shift ;;
        --list)  MODE="list"; shift ;;
        --once)  MODE="once"; shift ;;
        --config) [[ $# -ge 2 ]] || die "--config needs a file argument"; CATALOG="$2"; shift 2 ;;
        --install-autostart) MODE="install-autostart"; shift ;;
        --remove-autostart)  MODE="remove-autostart"; shift ;;
        --setup) MODE="setup"; shift ;;
        --dialog) [[ $# -ge 2 ]] || die "--dialog needs an argument (kdialog|zenity)"; DIALOG_TOOL="$2"; shift 2 ;;
        -h|--help) usage ;;
        *) die "unknown option: $1 (try --help)" ;;
    esac
done

case "$MODE" in
    check) check_mode ;;
    list)  list_mode ;;
    setup) setup_mode ;;
    install-autostart) install_autostart ;;
    remove-autostart)  remove_autostart ;;
    *)
        if [[ "$MODE" == "once" && -f "$DONE_MARKER" ]]; then
            echo "Already completed — remove $DONE_MARKER to run again."
            exit 0
        fi
        load_catalog
        run_dialog
        ;;
esac
