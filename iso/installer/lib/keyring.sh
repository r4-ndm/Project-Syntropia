#!/bin/bash
# Keyring auto-unlock for the installed system (KWallet).
# ------------------------------------------------------
# The image ships KWallet (kwalletd6 + ksecretd) and no gnome-keyring, so KWallet
# is the wallet Plasma and its apps use. Without a PAM module KWallet has no
# password to work with at first login and asks the user to *create a wallet
# password* — the "new keyring password" prompt the 2026-10-21 laptop install
# hit. Omarchy avoids the same prompt for gnome-keyring by seeding the keyring
# and wiring PAM; for KWallet the equivalent is:
#
#   * kwallet-pam in the image (pam_kwallet5.so + pam_kwallet_init),
#   * `auth/session optional pam_kwallet5.so` in the display manager's PAM
#     stack, tied to the login password,
#   * for autologin, `pam_systemd_loadkey` (the LUKS passphrase is the account
#     password) plus KeyringMode=inherit on the login-manager service,
#   * the Secret Service bridge enabled so libsecret apps (Chromium, Electron)
#     use the same wallet instead of creating another one.
#
# When the wallet does not exist yet, ksecretd's PAM path creates it with the
# login password (KSecretD::pamOpen → brandNew), so no prompt is ever shown.
# Reference: https://wiki.archlinux.org/title/KDE_Wallet
#
# All functions take the target root as their first argument and touch only that
# tree, so they can be driven against a fake root in tests.

[[ -n "${SYNTROPIA_KEYRING_SH:-}" ]] && return 0
SYNTROPIA_KEYRING_SH=1

# PAM files for the display managers the image can ship, plus tty login. The
# autologin variants only receive a password through pam_systemd_loadkey.
KEYRING_PAM_FILES=(plasmalogin sddm login)
KEYRING_AUTOLOGIN_PAM_FILES=(plasmalogin-autologin sddm-autologin)

KEYRING_PACKAGES=(kwallet-pam socat)

# The KWallet PAM module is still called pam_kwallet5.so for Plasma 6 (kwalletd=
# points it at ksecretd). Accept pam_kwallet6.so too so a future rename does not
# silently disable auto-unlock.
keyring_pam_module() {
    local target="$1" module
    for module in pam_kwallet5.so pam_kwallet6.so; do
        if [[ -f "$target/usr/lib/security/$module" ]]; then
            printf '%s' "$module"
            return 0
        fi
    done
    return 1
}

# The daemon the PAM module launches: ksecretd on Plasma 6, kwalletd6 on Plasma 5.
keyring_daemon() {
    local target="$1" daemon
    for daemon in /usr/bin/ksecretd /usr/bin/kwalletd6 /usr/bin/kwalletd5; do
        if [[ -x "$target$daemon" ]]; then
            printf '%s' "$daemon"
            return 0
        fi
    done
    return 1
}

keyring_has_loadkey() {
    [[ -f "$1/usr/lib/security/pam_systemd_loadkey.so" ]]
}

# Autologin types no password, so PAM can only feed the wallet when it can
# recover the LUKS passphrase (which the installer sets to the account
# password). Both halves of that chain have to exist in the target.
keyring_can_feed_autologin() {
    local target="$1"
    keyring_pam_module "$target" >/dev/null && keyring_has_loadkey "$target"
}

# Install the packages the unlock chain needs when the image predates them (or
# when a user installed from an older ISO). Best effort: offline installs only
# get the warning, never a stalled pacman.
keyring_install_packages() {
    local target="$1" online="${2:-false}"
    local -a missing=() pkg

    keyring_pam_module "$target" >/dev/null || missing+=(kwallet-pam)
    [[ -x "$target/usr/bin/socat" ]] || missing+=(socat)
    ((${#missing[@]} == 0)) && return 0

    if [[ "$online" != "true" ]]; then
        echo "keyring: ${missing[*]} missing from the image and this install is offline —" >&2
        echo "keyring: the wallet will ask to be created on first login; install ${missing[*]} and re-login." >&2
        return 1
    fi

    if [[ -f "$target/etc/resolv.conf" ]]; then
        : # the rsync already carried a working resolver
    elif [[ -f /run/systemd/resolve/stub-resolv.conf ]]; then
        install -Dm644 /run/systemd/resolve/stub-resolv.conf "$target/etc/resolv.conf"
    fi
    echo "keyring: installing ${missing[*]} into the target..."
    arch-chroot "$target" pacman -Sy --noconfirm --needed "${missing[@]}"
}

# Resolve a PAM service file inside the target. /etc/pam.d wins; otherwise the
# vendor file in /usr/lib/pam.d is copied into /etc/pam.d so it can be edited
# (the Arch-prescribed way to override a login manager's PAM stack).
keyring_pam_path() {
    local target="$1" name="$2"
    if [[ -f "$target/etc/pam.d/$name" ]]; then
        printf '%s' "$target/etc/pam.d/$name"
        return 0
    fi
    if [[ -f "$target/usr/lib/pam.d/$name" ]]; then
        mkdir -p "$target/etc/pam.d"
        cp "$target/usr/lib/pam.d/$name" "$target/etc/pam.d/$name"
        printf '%s' "$target/etc/pam.d/$name"
        return 0
    fi
    return 1
}

# The pam_kwallet session line that starts the daemon. `force_run` is required
# for tty logins (no display manager to autostart pam_kwallet_init).
keyring_session_line() {
    local module="$1" daemon="$2" force_run="${3:-0}"
    printf 'session optional %s auto_start' "$module"
    ((force_run)) && printf ' force_run'
    [[ -n "$daemon" ]] && printf ' kwalletd=%s' "$daemon"
    printf '\n'
}

# pam_systemd_loadkey must run *before* pam_kwallet: it is what puts the LUKS
# key in the auth token pam_kwallet hashes. Insert it above the existing line
# rather than appending, which would run it too late.
keyring_insert_loadkey() {
    local file="$1"
    grep -q 'pam_systemd_loadkey\.so' "$file" && return 0
    sed -i -E '/^[[:space:]]*-?auth[[:space:]]+optional[[:space:]]+pam_kwallet[56]\.so/i -auth optional pam_systemd_loadkey.so' "$file"
}

# Add/normalise the auth + session lines in one PAM file, idempotently.
# Login managers ship pam_kwallet lines already (plasmalogin does), but without
# `kwalletd=` they start the default daemon instead of Plasma 6's ksecretd — the
# Secret Service bridge the session actually uses.
keyring_pam_ensure() {
    local file="$1" module="$2" daemon="$3" autologin="${4:-0}" force_run="${5:-0}"

    [[ -f "$file" ]] || return 0

    local has_auth='^[[:space:]]*-?auth[[:space:]]+optional[[:space:]]+pam_kwallet[56]\.so'
    local has_session='^[[:space:]]*-?session[[:space:]]+optional[[:space:]]+pam_kwallet[56]\.so'

    if grep -qE "$has_auth" "$file"; then
        ((autologin)) && keyring_insert_loadkey "$file"
    else
        if ((autologin)); then
            printf -- '-auth optional pam_systemd_loadkey.so\n' >>"$file"
        fi
        printf 'auth optional %s\n' "$module" >>"$file"
    fi

    if grep -qE "$has_session" "$file"; then
        # Point an existing line at ksecretd when it does not ask for one.
        if [[ -n "$daemon" ]] && ! grep -q 'kwalletd=' "$file"; then
            sed -i -E "s#^([[:space:]]*-?session[[:space:]]+optional[[:space:]]+pam_kwallet[56]\\.so[[:space:]]+auto_start[[:space:]]*)\$#\\1 kwalletd=$daemon#" "$file"
        fi
    else
        keyring_session_line "$module" "$daemon" "$force_run" >>"$file"
    fi
}

# Let pam_systemd_loadkey read the LUKS volume key from the login manager.
keyring_keyringmode_dropin() {
    local target="$1" service="$2" dir
    dir="$target/etc/systemd/system/$service.service.d"
    mkdir -p "$dir"
    cat >"$dir/keyringmode.conf" <<'EOF'
[Service]
# Syntropia: pam_systemd_loadkey can only hand the LUKS passphrase to pam_kwallet
# when the login manager inherits the system keyring (autologin keyring unlock).
KeyringMode=inherit
EOF
}

# Wire every PAM file that exists in the target.
#   keyring_configure_pam <target> <autologin:0|1>
keyring_configure_pam() {
    local target="$1" autologin="${2:-0}"
    local module daemon file configured=0

    if ! module="$(keyring_pam_module "$target")"; then
        echo "keyring: pam_kwallet5.so is not in the target — wallet auto-unlock disabled" >&2
        return 1
    fi
    daemon="$(keyring_daemon "$target")" || daemon=""

    local path
    for file in "${KEYRING_PAM_FILES[@]}"; do
        path="$(keyring_pam_path "$target" "$file")" || continue
        keyring_pam_ensure "$path" "$module" "$daemon" 0 \
            "$([[ "$file" == "login" ]] && echo 1 || echo 0)"
        configured=1
    done

    for file in "${KEYRING_AUTOLOGIN_PAM_FILES[@]}"; do
        path="$(keyring_pam_path "$target" "$file")" || continue
        keyring_pam_ensure "$path" "$module" "$daemon" 1 1
        # Only the service behind an enabled autologin needs the keyring mode.
        ((autologin)) && keyring_keyringmode_dropin "$target" "${file%-autologin}"
        configured=1
    done

    if ((configured == 0)); then
        echo "keyring: no display-manager PAM file in the target — wallet auto-unlock disabled" >&2
        return 1
    fi
    return 0
}

# Enable KWallet's Secret Service bridge in the user's config so libsecret apps
# use the wallet that PAM already unlocked instead of prompting for a new one.
keyring_write_user_config() {
    local home="$1"
    local rc="$home/.config/kwalletrc"
    mkdir -p "$home/.config"
    if [[ ! -f "$rc" ]]; then
        printf '[org.freedesktop.secrets]\napiEnabled=true\n' >"$rc"
    elif ! grep -q '^apiEnabled=true' "$rc"; then
        if grep -q '^\[org.freedesktop.secrets\]' "$rc"; then
            sed -i '/^\[org.freedesktop.secrets\]/a apiEnabled=true' "$rc"
        else
            printf '\n[org.freedesktop.secrets]\napiEnabled=true\n' >>"$rc"
        fi
    fi
    chmod 644 "$rc"
}

# One call for the runner: packages, PAM, user config.
#   keyring_configure_target <target> <user> <online> <autologin:0|1>
keyring_configure_target() {
    local target="$1" user="$2" online="${3:-false}" autologin="${4:-0}"
    local status=0

    keyring_install_packages "$target" "$online" || status=1
    keyring_configure_pam "$target" "$autologin" || status=1
    keyring_write_user_config "$target/home/$user" || status=1
    # New accounts copy /etc/skel, so seed the same setting there.
    if [[ -d "$target/etc/skel" ]]; then
        keyring_write_user_config "$target/etc/skel" || true
    fi
    return "$status"
}
