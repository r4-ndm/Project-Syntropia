#!/usr/bin/env bash
# 😈 Syntropia Apps Wizard — first-boot "pick your favorites" installer.
#
# The UI is the Bubble Tea TUI (dialog/syntropia-apps-tui) — the only frontend.
# This script drives it: resolve the catalog, run the TUI in a terminal, install
# the picks with paru, and (in --once mode) remember completion.
#
# Modes: (no args) run · --once · --config FILE · --install-autostart · --remove-autostart
# Catalog: category|name|package|description (package may be an https:// URL → a
# web-app launcher). Resolution: --config, ~/.config/syntropia/apps.list,
# /etc/syntropia/apps.list, apps.list next to this script.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
AUTOSTART_DIR="$CONFIG_HOME/autostart"
DONE_MARKER="$CONFIG_HOME/syntropia/apps-wizard.done"
BUNDLED_CATALOG="$SCRIPT_DIR/apps.list"
DESKTOP_TEMPLATE="$SCRIPT_DIR/syntropia-apps.desktop"
TUI_BIN="$SCRIPT_DIR/dialog/syntropia-apps-tui"

MODE="interactive"
CATALOG=""

die() { echo "😈 error: $*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

mark_done() {
    mkdir -p "$(dirname "$DONE_MARKER")"
    touch "$DONE_MARKER"
}

# Cancelled / nothing selected — don't mark done, so it can run again later.
skip_note() {
    echo "😈 Skipped — you can pick apps any time with:"
    echo "  $SCRIPT_DIR/syntropia-apps-wizard.sh"
    if [[ "$MODE" == "once" && -t 0 ]]; then
        echo; echo "Press Enter to close this window."; read -r _ || true
    fi
}

resolve_catalog() {
    [[ -n "$CATALOG" ]] && { [[ -f "$CATALOG" ]] || die "catalog not found: $CATALOG"; echo "$CATALOG"; return; }
    local user_catalog="$CONFIG_HOME/syntropia/apps.list"
    [[ -f "$user_catalog" ]] && { echo "$user_catalog"; return; }
    [[ -f /etc/syntropia/apps.list ]] && { echo "/etc/syntropia/apps.list"; return; }
    echo "$BUNDLED_CATALOG"
}

find_terminal() {
    [[ -n "${TERMINAL:-}" ]] && have "$TERMINAL" && { echo "$TERMINAL"; return; }
    local t
    for t in konsole gnome-terminal xfce4-terminal kitty alacritty xterm; do
        have "$t" && { echo "$t"; return; }
    done
    return 1
}

launch_terminal() {
    local term="$1" inner="$2" arr
    case "$term" in
        konsole)        arr=(konsole -e bash -c "$inner") ;;
        gnome-terminal) arr=(gnome-terminal -- bash -c "$inner") ;;
        xfce4-terminal) arr=(xfce4-terminal -x bash -c "$inner") ;;
        kitty)          arr=(kitty bash -c "$inner") ;;
        alacritty)      arr=(alacritty -e bash -c "$inner") ;;
        xterm)          arr=(xterm -e bash -c "$inner") ;;
        *)              [[ -n "${TERMINAL:-}" ]] || return 1
                        arr=("$term" -e bash -c "$inner") ;;
    esac
    nohup "${arr[@]}" >/dev/null 2>&1 &
}

ensure_tui() {
    [[ -x "$TUI_BIN" ]] && return 0
    if have go && [[ -f "$SCRIPT_DIR/dialog/main.go" ]]; then
        echo "Building the Syntropia TUI (one-time, needs go)..."
        ( cd "$SCRIPT_DIR/dialog" && CGO_ENABLED=0 go build -o syntropia-apps-tui . ) || return 1
        return 0
    fi
    die "TUI not found — build it: cd $SCRIPT_DIR/dialog && go build -o syntropia-apps-tui ."
}

create_web_launcher() {
    local name="$1" url="$2" slug launcher exec_line
    slug="$(printf '%s' "$name" | tr '[:upper:]' '[:lower:]' | tr -cs '[:alnum:]' '-' | sed 's/^-*//; s/-*$//')"
    launcher="${XDG_DATA_HOME:-$HOME/.local/share}/applications/syntropia-$slug.desktop"
    if have brave; then exec_line="brave --app=$url"
    elif have chromium; then exec_line="chromium --app=$url"
    elif have firefox; then exec_line="firefox --new-window $url"
    else exec_line="xdg-open $url"; fi
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

run_dialog() {
    local cat_file out_file rc row term q relaunch pkg i
    local selected=() native=() web_names=() web_urls=()
    cat_file="$(resolve_catalog)"
    [[ -f "$cat_file" ]] || die "no catalog found: $cat_file"
    ensure_tui

    # Autostart launches us detached (no TTY) — relaunch inside a terminal;
    # the inner run then installs inline in that same terminal.
    if [[ ! -t 0 ]]; then
        relaunch=("$0")
        [[ "$MODE" == "once" ]] && relaunch+=(--once)
        [[ -n "$CATALOG" ]] && relaunch+=(--config "$CATALOG")
        term="$(find_terminal)" || die "no terminal emulator found — run in a terminal instead: $0"
        q="$(printf '%q ' "${relaunch[@]}")"
        launch_terminal "$term" "$q"
        exit 0
    fi

    have paru || {
        echo "Installing paru (sudo will ask for your password)..."
        sudo pacman -S --noconfirm paru || die "paru is required to install apps"
    }

    out_file="$(mktemp)"
    rc=0
    "$TUI_BIN" "$cat_file" "$out_file" || rc=$?
    if [[ $rc -ne 0 ]]; then rm -f "$out_file"; skip_note; exit 0; fi
    while IFS= read -r row; do [[ -z "$row" ]] || selected+=("$row"); done < "$out_file"
    rm -f "$out_file"

    [[ ${#selected[@]} -gt 0 ]] || { echo "😈 Nothing selected — nothing installed."; skip_note; exit 0; }

    # Map web-app URLs back to display names (the TUI prints package tags,
    # which for web apps are the URLs).
    declare -A web_name
    while IFS= read -r row || [[ -n "$row" ]]; do
        row="$(printf '%s' "$row" | sed -E 's/(^|[[:space:]])#.*/\1/')"
        [[ -z "${row//[[:space:]]/}" ]] && continue
        IFS='|' read -r _ name pkg _ <<< "$row"
        [[ "$pkg" == http* ]] && web_name["$pkg"]="$name"
    done < "$cat_file"

    for pkg in "${selected[@]}"; do
        if [[ "$pkg" == http* ]]; then
            web_names+=("${web_name[$pkg]:-$pkg}"); web_urls+=("$pkg")
        else
            native+=("$pkg")
        fi
    done

    if [[ ${#native[@]} -gt 0 ]]; then
        echo "Installing packages: ${native[*]}"; echo
        paru -S --noconfirm "${native[@]}" || echo "paru exited with $? — continuing"
        if [[ "$MODE" == "once" ]]; then
            echo; echo "Done — press Enter to close this window."; read -r _
        fi
    fi

    if [[ ${#web_urls[@]} -gt 0 ]]; then
        echo "Creating web app launchers:"
        for i in "${!web_urls[@]}"; do
            create_web_launcher "${web_names[$i]}" "${web_urls[$i]}"
        done
    fi

    [[ "$MODE" == "once" ]] && mark_done
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

while [[ $# -gt 0 ]]; do
    case "$1" in
        --once) MODE="once"; shift ;;
        --config) [[ $# -ge 2 ]] || die "--config needs a file argument"; CATALOG="$2"; shift 2 ;;
        --install-autostart) MODE="install-autostart"; shift ;;
        --remove-autostart)  MODE="remove-autostart"; shift ;;
        -h|--help) sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) die "unknown option: $1 (try --help)" ;;
    esac
done

case "$MODE" in
    install-autostart) install_autostart ;;
    remove-autostart)  remove_autostart ;;
    *)
        # Live-env guard: the autostart entry is baked into the ISO rootfs and
        # would fire during the live session too — but the wizard must only run
        # after a real install (the live ISO ships /etc/calamares).
        if [[ -d /etc/calamares ]]; then
            echo "Live environment — first-boot wizard deferred to the installed system."
            exit 0
        fi
        if [[ "$MODE" == "once" && -f "$DONE_MARKER" ]]; then
            echo "Already completed — remove $DONE_MARKER to run again."
            exit 0
        fi
        run_dialog
        ;;
esac
