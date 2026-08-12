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
#   --dialog TOOL         force a specific dialog tool (tui|qt|kdialog|zenity)
#   --setup               seed ~/.config/syntropia/apps.list (editable copy),
#                         install the one-shot autostart entry
#   --install-autostart   install the one-shot autostart entry
#   --remove-autostart    remove the autostart entry
#
# Dependencies: the preferred dialog is the TUI (dialog/syntropia-apps-tui)
# — a Bubble Tea (Charm ecosystem) glamour UI with zero runtime deps (static
# binary). Built from source on demand when go is available, or shipped by
# the syntropia package/ISO. Runs inside a terminal — the same place the
# install output lands. Fallbacks: the PySide6 qt grid if installed, else
# kdialog (native KDE/Plasma look — CachyOS default desktop) or zenity
# (GTK). Plus paru (installs; bootstrapped if missing) and a terminal
# emulator.

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

# The TUI dialog (dialog/syntropia-apps-tui) is the tier-1 dialog: a
# Bubble Tea (Charm ecosystem) glamour UI — category groups, checkbox list,
# dark purple/pink theme. It is a static binary with zero runtime deps. The
# PKGBUILD builds it (makedepends: go); the wizard also builds it on demand
# from dialog/main.go when the Go toolchain is present, and falls back to
# the other dialogs when neither is available.
TUI_BIN="$SCRIPT_DIR/dialog/syntropia-apps-tui"
have_tui_dialog() {
    [[ -x "$TUI_BIN" ]] && return 0
    have syntropia-apps-tui || [[ -x /usr/bin/syntropia-apps-tui ]]
}

ensure_tui_binary() {
    have_tui_dialog && return 0
    if have go && [[ -f "$SCRIPT_DIR/dialog/main.go" ]]; then
        echo "Building the Syntropia TUI dialog (one-time, needs go)..."
        ( cd "$SCRIPT_DIR/dialog" && go build -o syntropia-apps-tui . ) || return 1
        return 0
    fi
    return 1
}

# kdialog is the native Plasma dialog (renders with the CachyOS/Breeze
# theme); zenity is the GTK fallback for non-KDE desktops.
have_qt_dialog() {
    # the native grid dialog needs python3 + PySide6
    have python3 || return 1
    python3 -c "import PySide6" 2>/dev/null
}

find_dialog() {
    if [[ -n "$DIALOG_TOOL" ]]; then
        case "$DIALOG_TOOL" in
            tui)
                ensure_tui_binary || die "tui dialog not found — build it with: cd $SCRIPT_DIR/dialog && go build -o syntropia-apps-tui ."
                echo "tui"; return
                ;;
            qt)
                have_qt_dialog || die "qt dialog needs python3 + PySide6 (sudo pacman -S pyside6)"
                echo "qt"; return
                ;;
            kdialog|zenity)
                have "$DIALOG_TOOL" || die "dialog tool not found: $DIALOG_TOOL (use tui, web, qt, kdialog or zenity)"
                echo "$DIALOG_TOOL"; return
                ;;
            *) die "unknown dialog tool: $DIALOG_TOOL (use tui, web, qt, kdialog or zenity)" ;;
        esac
    fi
    if [[ -z "${SKIP_TUI:-}" ]]; then
        ensure_tui_binary && { echo "tui"; return; }
    fi
    have_qt_dialog && { echo "qt"; return; }
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
    if [[ "$dialog" == "tui" ]]; then
        # The TUI runs in a terminal — bootstrap paru inline with sudo.
        echo "Installing paru (sudo will ask for your password)..."
        sudo pacman -S --noconfirm paru || die "paru is required to install apps"
    fi
    # kdialog/qt/zenity dialogs: prompt for the bootstrap with whatever GUI
    # toolkit exists — and fail with a clear message instead of a cryptic
    # "zenity: command not found" when neither is installed.
    local ask
    if have kdialog; then
        kdialog --title "😈 Syntropia" \
            --yesno "paru (the AUR helper) is not installed yet.\n\nInstall it first? (a password prompt will appear)" \
            --yes-label "Install paru" --no-label "Cancel"
        ask=$?
    elif have zenity; then
        zenity --question --title="😈 Syntropia" \
            --text="paru (the AUR helper) is not installed yet.\n\nInstall it first? (a password prompt will appear)" \
            --ok-label="Install paru" --cancel-label="Cancel"
        ask=$?
    else
        echo "😈 Install paru first, then re-run the wizard:" >&2
        echo "    sudo pacman -S paru" >&2
        return 1
    fi
    if [[ $ask -eq 0 ]]; then
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
    dialog="$(find_dialog)" || die "no dialog available — install one of: tui (needs go or the syntropia package), pyside6 (qt grid), kdialog, or zenity"
    if [[ "$dialog" == "tui" && ! -t 0 ]]; then
        # The TUI needs a real terminal. Relaunch inside one; the inner run
        # then has a TTY and installs inline in that same terminal.
        local relaunch=("$0" "--dialog" "tui")
        [[ "$MODE" == "once" ]] && relaunch+=("--once")
        [[ -n "$CATALOG" ]] && relaunch+=(--config "$CATALOG")
        local q
        q="$(printf '%q ' "${relaunch[@]}")"
        if launch_terminal "$q"; then
            exit 0
        fi
        # no terminal emulator — fall through to a GUI dialog
        SKIP_TUI=1 dialog="$(find_dialog)" || die "no dialog available — install one of: pyside6 (qt grid), kdialog, or zenity"
    fi
    ensure_paru "$dialog"

    # Force the Breeze widget style for the Qt dialogs (qt grid + kdialog) on
    # non-Plasma desktops so checkboxes render with the KDE look (their GTK
    # platform theme paints them invisibly). On a Plasma session the native
    # style is already active.
    if [[ "$dialog" == "qt" || "$dialog" == "kdialog" ]] && [[ -z "${KDE_FULL_SESSION:-}" ]]; then
        export QT_STYLE_OVERRIDE=breeze
    fi

    # Unique categories, in catalog order — all shown in ONE grouped dialog:
    # category separator rows (unchecked, tags prefixed __hdr__) between the
    # app rows, so there is no window respawn between categories.
    local cat_order=() c cc seen i args out row name
    for i in "${!names[@]}"; do
        c="${cats[$i]}"
        seen=0
        for cc in "${cat_order[@]}"; do
            [[ "$cc" == "$c" ]] && seen=1 && break
        done
        (( seen )) || cat_order+=("$c")
    done

    if [[ "$dialog" == "tui" ]]; then
        # TUI dialog — Bubble Tea glamour UI in the current terminal; prints
        # checked package tags (one per line) like kdialog --separate-output
        args=("$TUI_BIN" "$CAT_FILE")
    elif [[ "$dialog" == "qt" ]]; then
        # native grid dialog — reads the catalog itself, prints checked
        # package tags (one per line) like kdialog --separate-output
        args=(python3 "$SCRIPT_DIR/syntropia-apps-dialog.py" "$CAT_FILE")
    elif [[ "$dialog" == "kdialog" ]]; then
        # per item: tag (returned), label (displayed), state —
        # so tag=package, label=display name
        args=(kdialog --title "😈 Syntropia — Pick your apps"
            --geometry "$(dialog_geometry 640x560)" --separate-output
            --checklist "Check the apps to install — everything installs together.\nCancel skips this permanently.")
        for c in "${cat_order[@]}"; do
            args+=("__hdr__$c" "— $c —" off)
            for i in "${!names[@]}"; do
                [[ "${cats[$i]}" == "$c" ]] && args+=("${pkgs[$i]}" "${names[$i]}" on)
            done
        done
    else
        args=(zenity --list --checklist --separator='|'
            --title="😈 Syntropia — Pick your apps"
            --text="Check the apps to install — everything installs together.\nCancel skips this permanently."
            --width=640 --height=560
            --column="Install" --column="App")
        for c in "${cat_order[@]}"; do
            args+=(FALSE "__hdr__$c")
            for i in "${!names[@]}"; do
                [[ "${cats[$i]}" == "$c" ]] && args+=(TRUE "${names[$i]}")
            done
        done
    fi

    local selected=()
    if ! out="$("${args[@]}")"; then
        # user cancelled — treat as "skip permanently" in --once mode
        if [[ "$MODE" == "once" ]]; then mark_done; fi
        echo "Skipped — nothing installed."
        exit 0
    fi

    while IFS= read -r row; do
        [[ -z "$row" ]] && continue
        if [[ "$dialog" == "qt" || "$dialog" == "kdialog" ]]; then
            # each returned line is the package tag directly
            [[ "$dialog" == "kdialog" && "$row" == __hdr__* ]] && continue  # skip category separators
            selected+=("$row")
        else
            # zenity: strip the checkbox state, then map display name → package
            [[ "$row" == TRUE\|* || "$row" == FALSE\|* ]] && row="${row#*|}"
            name="${row%%|*}"
            [[ "$name" == __hdr__* ]] && continue   # skip category separators
            for i in "${!names[@]}"; do
                if [[ "${names[$i]}" == "$name" ]]; then
                    selected+=("${pkgs[$i]}")
                    break
                fi
            done
        fi
    done <<< "$out"

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
        if [[ -t 0 ]]; then
            # already in a terminal (the TUI path) — install inline with live
            # output, then hand back to the same terminal. In --once mode
            # (the autostart relaunch) hold the window open so the result
            # is visible before the terminal closes.
            echo
            paru -S --noconfirm "${native[@]}" || echo "paru exited with $? — continuing"
            echo
            if [[ "$MODE" == "once" ]]; then
                echo "Done — press Enter to close this window."
                read -r _
            fi
        else
            local inner="paru -S --noconfirm ${native[*]}; rc=\$?; echo; if [ \$rc -eq 0 ]; then echo '✅ Done — press Enter to close'; else echo '❌ paru exited with \$rc — press Enter to close'; fi; read -r _"
            if launch_terminal "$inner"; then
                echo "Install running in a terminal window."
            else
                echo "No terminal emulator found — run this in a terminal instead:"
                echo "  paru -S --noconfirm ${native[*]}"
            fi
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
