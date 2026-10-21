#!/bin/bash
# Shared terminal helpers for the Syntropia live installer scripts.
# -----------------------------------------------------------------
# Sourced by syntropia-install and syntropia-install-dashboard so the palette,
# geometry detection and centring maths live in ONE place: the live ISO has no
# terminfo guarantee beyond `stty`/`tput`, and a second copy of this logic
# drifted the last time it existed.
#
# Sourcing is idempotent — a lib may source another lib (network.sh needs the
# palette) without redefining anything.
[[ -n "${SYNTROPIA_COMMON_SH:-}" ]] && return 0
SYNTROPIA_COMMON_SH=1

CSI=$'\033['
RESET="${CSI}0m"
DIM="${CSI}2m"
BOLD="${CSI}1m"
HIDE_CURSOR="${CSI}?25l"
SHOW_CURSOR="${CSI}?25h"
CLEAR="${CSI}2J${CSI}H"
CLEAR_LINE="${CSI}2K"
RED="${CSI}31m"
GREEN="${CSI}32m"
YELLOW="${CSI}33m"
MAGENTA="${CSI}35m"
CYAN="${CSI}36m"
WHITE="${CSI}37m"
DARK="${CSI}90m"
BRIGHT_MAGENTA="${CSI}95m"
BRIGHT_CYAN="${CSI}96m"

# The ASCII-art logo shipped at /usr/share/syntropia/logo.txt by build.sh.
SYNTROPIA_LOGO="${SYNTROPIA_LOGO:-/usr/share/syntropia/logo.txt}"

# Width of every centred frame (the setup TUI and the progress dashboard both
# draw 58-column content).
SYNTROPIA_FRAME_WIDTH=58

# $LINES/$COLUMNS first (bash exports them after a SIGWINCH), then stty, then
# tput, then Python's shutil — the last two cover the case where the script is
# started with stdin redirected away from the terminal.
term_size() {
    shopt -s checkwinsize 2>/dev/null || true
    (:;:) 2>/dev/null || true
    if [[ -n "${LINES:-}" && -n "${COLUMNS:-}" && "$LINES" -gt 0 && "$COLUMNS" -gt 0 ]]; then
        echo "$LINES $COLUMNS"
        return
    fi
    local sz=""
    sz=$(stty size 2>/dev/null || stty size < /dev/tty 2>/dev/null || true)
    if [[ -n "$sz" ]]; then
        echo "$sz"
        return
    fi
    if command -v tput >/dev/null 2>&1; then
        local l c
        l=$(tput lines 2>/dev/null || true)
        c=$(tput cols 2>/dev/null || true)
        if [[ -n "$l" && -n "$c" && "$l" -gt 0 && "$c" -gt 0 ]]; then
            echo "$l $c"
            return
        fi
    fi
    if command -v python3 >/dev/null 2>&1; then
        sz=$(python3 -c 'import shutil; s=shutil.get_terminal_size((80, 24)); print(f"{s.lines} {s.columns}")' 2>/dev/null || true)
        if [[ -n "$sz" ]]; then
            echo "$sz"
            return
        fi
    fi
    echo "24 80"
}

repeat() {
    local char="$1" count="$2" out="" i
    for ((i = 0; i < count; i++)); do out+="$char"; done
    printf '%s' "$out"
}

# Set INDENT (left padding) and TOP_PAD (vertical padding) so a frame of
# SYNTROPIA_FRAME_WIDTH columns is centred. Shows the full logo only when the
# terminal can hold it. Pass the number of rows the frame needs to force a
# compact layout (the setup TUI does this for its long forms).
calc_margins() {
    local req_h="${1:-0}"
    local size term_h term_w content_h i
    size="$(term_size)"
    term_h="${size% *}"
    term_w="${size#* }"
    term_h="${term_h:-24}"
    term_w="${term_w:-80}"

    if ((req_h > 0)); then
        content_h="$req_h"
        SHOW_FULL_LOGO=0
    elif ((term_h >= 36)) && [[ -f "$SYNTROPIA_LOGO" ]]; then
        content_h=32
        SHOW_FULL_LOGO=1
    else
        content_h=14
        SHOW_FULL_LOGO=0
    fi

    pad_left=$(((term_w > SYNTROPIA_FRAME_WIDTH) ? (term_w - SYNTROPIA_FRAME_WIDTH) / 2 : 2))
    pad_top=$(((term_h > content_h) ? (term_h - content_h) / 2 : 0))
    INDENT="$(repeat " " "$pad_left")"
    TOP_PAD=""
    for ((i = 0; i < pad_top; i++)); do TOP_PAD+=$'\n'; done
}

# Print the triangle logo when it fits, otherwise the compact two-line mark.
print_logo() {
    if ((${SHOW_FULL_LOGO:-0} == 1)) && [[ -f "$SYNTROPIA_LOGO" ]]; then
        {
            printf '%s' "$BRIGHT_MAGENTA"
            while IFS= read -r __logo_line; do
                printf '%s%s\n' "$INDENT" "$__logo_line"
            done <"$SYNTROPIA_LOGO"
            printf '%s\n' "$RESET"
        }
    else
        printf '%s%s       *4*                          *4*%s\n' "$INDENT" "$BRIGHT_MAGENTA" "$RESET"
        printf '%s%s        ***4444  ▲ SYNTROPIA OS ▲ 444****%s\n' "$INDENT" "$BRIGHT_MAGENTA" "$RESET"
        printf '%s%s         4444444**4  ( 😈 )  4**4444444%s\n' "$INDENT" "$BRIGHT_MAGENTA" "$RESET"
        printf '%s%s    Trust the mutation. Never trust the boundary.%s\n\n' "$INDENT" "$DIM" "$RESET"
    fi
}

# A horizontal rule plus a title, e.g. `section_rule "Network"` — the visual
# separator every step in the setup TUI starts with.
section_rule() {
    local title="$1"
    printf '%s%s── %s %s%s\n' "$INDENT" "$BRIGHT_MAGENTA" "$title" \
        "$(repeat "─" $((SYNTROPIA_FRAME_WIDTH - ${#title} - 5)))" "$RESET"
}

# Two-column "label / value" line for summaries.
field_line() {
    local label="$1" value="$2"
    printf '%s  %s%-16s%s %s\n' "$INDENT" "$DIM" "$label" "$RESET" "$value"
}

# Print a warning or error line in the installer's voice.
note() {
    local color="$1" mark="$2"
    shift 2
    printf '%s  %s%s%s %s\n' "$INDENT" "$color" "$mark" "$RESET" "$*"
}

# Ask a free-text question with a default. Sets $2 to the answer.
ask_line() {
    local prompt="$1" __var="$2" __default="${3:-}" __answer=""
    printf '%s  %s%s%s%s ' "$INDENT" "$BOLD" "$prompt" "${__default:+ (default: ${__default})}" "$RESET"
    IFS= read -r __answer || { printf '\n'; return 1; }
    [[ -n "$__answer" ]] || __answer="$__default"
    printf -v "$__var" '%s' "$__answer"
}
