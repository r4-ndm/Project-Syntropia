#!/bin/bash
# Password entry UI for the Syntropia live installer.
# ---------------------------------------------------
# One place for every password question so the flow stays consistent and
# testable: a read-only strength estimate, a masked "what you typed" view, and
# a confirmation field. The account password is the only one the flow asks for:
# root is locked by default (see ROOT_PASSWORD_MODE), exactly like an
# archinstall/Omarchy install, so the user never invents a second secret.
# `--root-password` opts back into the "same as the user"/"separate" menu.
#
# Why a hand-rolled strength estimate instead of a library: the live ISO is
# bash + python only, and the candidate OSS meters (zxcvbn, passwdqc) are not
# pip-installable from the ISO without network. This heuristic is deliberately
# simple and documented — length and character-class spread, with a deny-list
# and repeated-character guard — so nobody mistakes it for entropy estimation.
# A Rust/Python port can replace password_strength_score() without touching the
# UI: everything else calls it through that one function.

[[ -n "${SYNTROPIA_PASSWORD_SH:-}" ]] && return 0
SYNTROPIA_PASSWORD_SH=1

[[ -n "${SYNTROPIA_COMMON_SH:-}" ]] || source "$(dirname "${BASH_SOURCE[0]}")/common.sh"

PASSWORD_MIN_LENGTH=8
PASSWORD_BAR_WIDTH=12
# "locked" (default) | "same-as-user" | "separate"
#
# Locked root means sudo/polkit ask for the account password and there is no
# root password to guess, phish or forget. The runner locks the account with
# `passwd -l root`; a root password is only set when the operator asked for one.
ROOT_PASSWORD_MODE="locked"

# --- strength -------------------------------------------------------------

# Score 0 (very weak) .. 4 (very strong) on stdout.  Not an entropy figure:
# a password that scores 4 here can still be "correcthorsebatterystaple".
password_strength_score() {
    local pw="$1" score=0 classes=0

    if ((${#pw} == 0)); then
        echo 0
        return 0
    fi

    # Obvious throwaways: score 0 regardless of length.
    case "$pw" in
        password | passwd | letmein | qwerty | qwertyuiop | 12345678 | 123456789 | \
            syntropia | cachyos | admin | administrator | root | changeme)
            echo 0
            return 0
            ;;
    esac
    # A single repeated character ("aaaaaaaa").
    if [[ "$pw" == "$(printf "%${#pw}s" '' | tr ' ' "${pw:0:1}")" ]]; then
        echo 0
        return 0
    fi

    [[ "$pw" =~ [[:lower:]] ]] && classes=$((classes + 1))
    [[ "$pw" =~ [[:upper:]] ]] && classes=$((classes + 1))
    [[ "$pw" =~ [[:digit:]] ]] && classes=$((classes + 1))
    [[ "$pw" =~ [^[:alnum:]] ]] && classes=$((classes + 1))

    ((${#pw} >= 8)) && score=$((score + 1))
    ((${#pw} >= 12)) && score=$((score + 1))
    ((${#pw} >= 16)) && score=$((score + 1))
    ((classes >= 2)) && score=$((score + 1))
    ((classes >= 3)) && score=$((score + 1))

    # Short passwords never read as better than "weak", however mixed they are.
    if ((${#pw} < PASSWORD_MIN_LENGTH && score > 1)); then
        score=1
    fi
    ((score > 4)) && score=4
    echo "$score"
}

password_strength_label() {
    case "$1" in
        0) echo "very weak" ;;
        1) echo "weak" ;;
        2) echo "fair" ;;
        3) echo "strong" ;;
        *) echo "very strong" ;;
    esac
}

password_strength_color() {
    case "$1" in
        0 | 1) printf '%s' "$RED" ;;
        2) printf '%s' "$YELLOW" ;;
        3) printf '%s' "$GREEN" ;;
        *) printf '%s' "$BRIGHT_CYAN" ;;
    esac
}

# Filled segments for the strength bar. A non-empty password always lights at
# least one segment so the bar never looks broken.
password_bar() {
    local score="$1" filled=$((score * 3))
    ((filled < 1)) && filled=1
    ((filled > PASSWORD_BAR_WIDTH)) && filled=PASSWORD_BAR_WIDTH
    printf '%s%s%s%s%s' \
        "$(password_strength_color "$score")" \
        "$(repeat "█" "$filled")" \
        "$DARK" \
        "$(repeat "░" $((PASSWORD_BAR_WIDTH - filled)))" \
        "$RESET"
}

# Bullet mask so the user can see how much they typed without revealing it.
password_mask() {
    local pw="$1" shown=${#pw}
    ((shown > 24)) && shown=24
    printf '%s' "$(repeat "•" "$shown")"
}

# --- reading --------------------------------------------------------------

# True when the value contains terminal control characters. Pressing End on a
# numpad with NumLock off emits an escape sequence, which used to become part
# of the password and then fail to unlock the disk at boot.
password_has_control_chars() {
    local pw="$1"
    [[ "$pw" == *$'\e'* ]] && return 0
    printf '%s' "$pw" | LC_ALL=C grep -q '[[:cntrl:]]'
}

# Masked single-line read. Returns non-zero when stdin closes (the live tty1
# loop always has a terminal, so this only fires in scripted/dry runs).
password_read_hidden() {
    local __var="$1" __value=""
    IFS= read -rs __value || {
        printf '\n'
        return 1
    }
    printf '\n'
    printf -v "$__var" '%s' "$__value"
}

# --- rendering ------------------------------------------------------------

password_header() {
    local label="$1" hint="${2:-}"
    printf '\n'
    section_rule "$label"
    [[ -n "$hint" ]] && printf '%s  %s%s%s\n' "$INDENT" "$DIM" "$hint" "$RESET"
    printf '%s  %sCharacters stay hidden while you type.%s\n\n' "$INDENT" "$DIM" "$RESET"
}

password_row_prompt() {
    printf '%s  %-16s %s›%s ' "$INDENT" "$1" "$BOLD" "$RESET"
}

# Signal 0..4 -> filled/empty bar + label.
password_strength_row() {
    local score="$1"
    printf '%s  %-16s %s  %s%s%s\n' "$INDENT" "Strength" \
        "$(password_bar "$score")" \
        "$(password_strength_color "$score")" \
        "$(password_strength_label "$score")" "$RESET"
}

# "Meets"/"Missing" rows: what the estimate rewarded, and what it did not find.
password_feedback_rows() {
    local pw="$1" met="" missing=""

    ((${#pw} >= 8)) && met+="✓ 8+ characters   " || missing+="· 8+ characters   "
    ((${#pw} >= 12)) && met+="✓ 12+ characters   " || missing+="· 12+ characters   "
    if [[ "$pw" =~ [[:lower:]] && "$pw" =~ [[:upper:]] ]]; then
        met+="✓ mixed case   "
    else
        missing+="· mixed case   "
    fi
    [[ "$pw" =~ [[:digit:]] ]] && met+="✓ a number   " || missing+="· a number   "
    [[ "$pw" =~ [^[:alnum:]] ]] && met+="✓ a symbol   " || missing+="· a symbol   "

    printf '%s  %-16s %s%s%s\n' "$INDENT" "Meets" "$GREEN" "${met%   }" "$RESET"
    [[ -n "$missing" ]] && printf '%s  %-16s %s%s%s\n' "$INDENT" "Missing" "$DIM" "${missing%   }" "$RESET"
}

# The full post-entry report: what was typed (masked), how strong it is, why.
password_report() {
    local pw="$1" score
    score="$(password_strength_score "$pw")"
    printf '%s  %-16s %s\n' "$INDENT" "Entered" "$(password_mask "$pw")"
    password_strength_row "$score"
    password_feedback_rows "$pw"
}

# One line for the install summary: what will happen to the root account.
root_password_summary() {
    local user="$1"
    case "$ROOT_PASSWORD_MODE" in
        separate) echo "separate from $user" ;;
        same-as-user) echo "same as $user" ;;
        *) echo "locked (sudo uses your password)" ;;
    esac
}

# --- the flows ------------------------------------------------------------

# ask_new_password <label> <out-var> [hint]
# Loops until the user enters a password of at least PASSWORD_MIN_LENGTH that
# they confirm correctly. Weak-but-long passwords need an explicit "keep".
ask_new_password() {
    local label="$1" outvar="$2" hint="${3:-}"
    local pw="" confirm="" attempt=0 answer=""

    while :; do
        password_header "$label" "$hint"
        password_row_prompt "New password"
        password_read_hidden pw || return 1

        if password_has_control_chars "$pw"; then
            note "$RED" "✗" "special keys or escape codes detected (NumPad with NumLock off, arrow keys)."
            note "$DIM" " " "use the number row or enable NumLock, then try again."
            continue
        fi

        if ((${#pw} < PASSWORD_MIN_LENGTH)); then
            password_report "$pw"
            note "$RED" "✗" "too short — at least ${PASSWORD_MIN_LENGTH} characters. Try again."
            continue
        fi

        password_report "$pw"

        if (($(password_strength_score "$pw") <= 1)); then
            printf '%s  %sWeak.%s Keep it anyway? %s[k]eep / [r]etry [r]%s ' \
                "$INDENT" "$YELLOW" "$RESET" "$DIM" "$RESET"
            IFS= read -r answer || answer="r"
            if [[ ! "$answer" =~ ^[kK] ]]; then
                note "$DIM" " " "a short sentence is easier to type and much stronger than a scrambled word."
                continue
            fi
        fi

        for attempt in 1 2; do
            password_row_prompt "Repeat password"
            password_read_hidden confirm || return 1
            if [[ "$pw" == "$confirm" ]]; then
                note "$GREEN" "✓" "passwords match"
                printf -v "$outvar" '%s' "$pw"
                return 0
            fi
            note "$RED" "✗" "passwords do not match (attempt ${attempt}/2)."
        done
        note "$DIM" " " "starting password entry again."
    done
}

# ask_root_password <username> <user-password> <out-var>
# Only reached when the operator passed --root-password. The default inside the
# menu is still to reuse the account password (one thing to remember); a
# separate root password stays one keypress away, like Calamares.
# Without the flag the caller never asks: ROOT_PASSWORD_MODE stays "locked".
ask_root_password() {
    local user="$1" user_pw="$2" outvar="$3" answer=""
    local root_pw="" label="Root (administrator) password"

    printf '\n'
    section_rule "$label"
    printf '%s  %sUsed by sudo, TTY logins and rescue work. Setting it now means%s\n' "$INDENT" "$DIM" "$RESET"
    printf '%s  %snothing is asked for at first boot.%s\n\n' "$INDENT" "$DIM" "$RESET"

    printf '%s  [1] Same password as "%s"%s  (default)%s\n' "$INDENT" "$user" "$DIM" "$RESET"
    printf '%s  [2] Set a different root password\n\n' "$INDENT"
    printf '%s  %sChoose [1-2]%s [1]: ' "$INDENT" "$BOLD" "$RESET"

    IFS= read -r answer || answer=""
    if [[ "${answer:-1}" == "2" ]]; then
        ask_new_password "$label" root_pw "Type a separate password for the root account." || return 1
        printf -v "$outvar" '%s' "$root_pw"
        ROOT_PASSWORD_MODE="separate"
    else
        printf -v "$outvar" '%s' "$user_pw"
        ROOT_PASSWORD_MODE="same-as-user"
        note "$GREEN" "✓" "root will use the same password as \"$user\""
    fi
    return 0
}
