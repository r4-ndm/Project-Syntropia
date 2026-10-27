#!/bin/bash
# Keyring auto-unlock for the installed system (KWallet).
# ------------------------------------------------------
# KWallet (kwalletd6 + ksecretd) is the wallet Syntropia's apps use. Without a
# PAM module KWallet has no password to work with at first login and asks the
# user to *create a wallet password* — the "new keyring password" prompt the
# 2026-10-21 laptop install hit. Omarchy avoids the same prompt for gnome-keyring
# by seeding the keyring and wiring PAM; for KWallet the equivalent is:
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
# The image also ships gnome-keyring (the CachyOS package set pulls it in) and
# SDDM's stock PAM stack carries pam_gnome_keyring lines — plasmalogin's did not,
# which is why the 2026-10-21 VM test was clean and the 2026-10-25 laptop install
# prompted again. Two locked-by-default wallets on one login cannot both be
# fed: pam_gnome_keyring runs before pam_systemd_loadkey can supply the
# autologin password, so the gnome login keyring stays locked, and gnome-keyring
# owns org.freedesktop.secrets through its D-Bus activation file. KWallet is the
# wallet here, so this library (a) wires the full auth/password/session stack
# into every display-manager PAM file in the target, (b) comments the competing
# pam_gnome_keyring lines out, and (c) parks gnome-keyring's Secret Service
# activation files so libsecret apps reach the wallet PAM unlocked.
#
# All functions take the target root as their first argument and touch only that
# tree, so they can be driven against a fake root in tests.

[[ -n "${SYNTROPIA_KEYRING_SH:-}" ]] && return 0
SYNTROPIA_KEYRING_SH=1

# PAM files for the display managers the image can ship, plus tty login. The
# autologin variants only receive a password through pam_systemd_loadkey.
KEYRING_PAM_FILES=(plasmalogin sddm login)
KEYRING_AUTOLOGIN_PAM_FILES=(plasmalogin-autologin sddm-autologin)

KEYRING_PACKAGES=(kwallet-pam kwallet socat)

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
# password). The module, the loadkey reader and a daemon to unlock all have to
# exist in the target.
keyring_can_feed_autologin() {
    local target="$1"
    keyring_pam_module "$target" >/dev/null \
        && keyring_has_loadkey "$target" \
        && keyring_daemon "$target" >/dev/null
}

# Install the packages the unlock chain needs when the image predates them (or
# when a user installed from an older ISO). Best effort: offline installs only
# get the warning, never a stalled pacman.
keyring_install_packages() {
    local target="$1" online="${2:-false}"
    local -a missing=() pkg

    keyring_pam_module "$target" >/dev/null || missing+=(kwallet-pam)
    # The daemon is a separate package (kwallet) that the image only carries as
    # a Plasma dependency — dropping Plasma from the package list can take it
    # with it, leaving a PAM module with nothing to unlock.
    keyring_daemon "$target" >/dev/null || missing+=(kwallet)
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
# for tty logins and non-Plasma display managers (SDDM with Hyprland has no
# Plasma session manager to autostart pam_kwallet_init).
keyring_session_line() {
    local module="$1" daemon="$2" force_run="${3:-0}"
    printf 'session optional %s auto_start' "$module"
    ((force_run)) && printf ' force_run'
    [[ -n "$daemon" ]] && printf ' kwalletd=%s' "$daemon"
    printf '\n'
}

# pam_systemd_loadkey must run *before* any keyring module: it is what puts the
# LUKS key in the auth token the wallet module hashes. Insert it above the first
# keyring auth line rather than appending, which would run it too late.
keyring_insert_loadkey() {
    local file="$1"
    grep -q 'pam_systemd_loadkey\.so' "$file" && return 0
    sed -i -E '0,/^[[:space:]]*-?auth[[:space:]]+[a-z_]+[[:space:]]+pam_(kwallet[56]|gnome_keyring)\.so/ s//-auth optional pam_systemd_loadkey.so\n&/' "$file"
}

# KWallet's password hook belongs with the display manager's own password stack
# (the Arch wiki/KDE layout: `password include system-login` followed by
# `password optional pam_kwallet5.so`), so a password change re-keys the wallet.
keyring_insert_password_line() {
    local file="$1" module="$2" tmp
    grep -qE '^[[:space:]]*-?password[[:space:]]+optional[[:space:]]+pam_kwallet[56]\.so' "$file" && return 0
    if grep -qE '^[[:space:]]*-?password[[:space:]]+include' "$file"; then
        tmp="$(mktemp)"
        awk -v wallet="$module" '
            { print }
            !placed && /^[[:space:]]*-?password[[:space:]]+include/ {
                printf "password optional %s\n", wallet
                placed = 1
            }
        ' "$file" >"$tmp" && cat "$tmp" >"$file"
        rm -f "$tmp"
    else
        printf 'password optional %s\n' "$module" >>"$file"
    fi
}

# gnome-keyring cannot be fed during autologin (its auth module runs before
# pam_systemd_loadkey supplies the passphrase) and it competes with KWallet for
# org.freedesktop.secrets, so its PAM lines are commented out of the stacks this
# library owns. Login-manager PAM files are pacman `backup=` files, so the edit
# survives a package upgrade.
keyring_disable_gnome_keyring_pam() {
    local file="$1"
    grep -q 'pam_gnome_keyring\.so' "$file" || return 0
    sed -i -E "s@^([^#].*pam_gnome_keyring\\.so.*)\$@# Syntropia: KWallet is the wallet — gnome-keyring must not lock a second one\n# \\1@" "$file"
}

# gnome-keyring's D-Bus activation files claim org.freedesktop.secrets and the
# Secret portal, so the first libsecret request (Brave, Chromium, Electron)
# starts a locked gnome-keyring instead of the ksecretd PAM just unlocked.
# Park them next to the originals: a package upgrade restores them, and the PAM
# lines above are what actually keep the prompt away.
# Also park XDG autostart files and mask systemd user socket/service so
# gnome-keyring cannot start unprompted and show "choose password for new keyring".
keyring_disable_gnome_keyring_secrets() {
    local target="$1" file path moved=0
    # Unless explicitly forced, check if target has a wallet daemon or force is enabled
    keyring_daemon "$target" >/dev/null || [[ -n "${FORCE_DISABLE_GNOME_KEYRING:-}" ]] || return 0

    # 1. Purge gnome-keyring package if pacman is usable
    if [[ -x "$target/usr/bin/pacman" ]] && [[ -d "$target/var/lib/pacman/local" ]]; then
        arch-chroot "$target" pacman -Rdd --noconfirm gnome-keyring 2>/dev/null || true
    fi

    # 2. Park D-Bus service files claiming gnome-keyring or secrets
    for file in \
        org.freedesktop.secrets.service \
        org.freedesktop.impl.portal.Secret.service \
        org.gnome.keyring.service \
        org.gnome.keyring.PrivatePrompter.service \
        org.gnome.keyring.SystemPrompter.service; do
        path="$target/usr/share/dbus-1/services/$file"
        [[ -f "$path" ]] || continue
        grep -q -E '(gnome-keyring-daemon|gnome-keyring)' "$path" || continue
        mv -f "$path" "$path.syntropia-disabled"
        moved=1
    done

    # 3. Park gnome-keyring desktop portal
    local portal="$target/usr/share/xdg-desktop-portal/portals/gnome-keyring.portal"
    if [[ -f "$portal" ]]; then
        mv -f "$portal" "$portal.syntropia-disabled"
        moved=1
    fi

    # 4. Disable XDG autostart for gnome-keyring components
    local autostart_dir="$target/etc/xdg/autostart"
    for file in gnome-keyring-secrets.desktop gnome-keyring-pkcs11.desktop gnome-keyring-ssh.desktop; do
        path="$autostart_dir/$file"
        if [[ -f "$path" ]]; then
            mv -f "$path" "$path.syntropia-disabled"
            moved=1
        fi
    done

    # 5. Mask systemd user socket and service so socket activation does not start it
    local systemd_user_dir="$target/etc/systemd/user"
    if [[ -d "$systemd_user_dir" ]] || [[ -d "$target/usr/lib/systemd/user" ]]; then
        mkdir -p "$systemd_user_dir"
        rm -f "$systemd_user_dir/sockets.target.wants/gnome-keyring-daemon.socket"
        ln -sf /dev/null "$systemd_user_dir/gnome-keyring-daemon.socket"
        ln -sf /dev/null "$systemd_user_dir/gnome-keyring-daemon.service"
    fi

    # 6. Neutralize any remaining daemon binary on the target
    if [[ -e "$target/usr/bin/gnome-keyring-daemon" ]]; then
        mv -f "$target/usr/bin/gnome-keyring-daemon" "$target/usr/bin/gnome-keyring-daemon.syntropia-disabled" 2>/dev/null || chmod 000 "$target/usr/bin/gnome-keyring-daemon" 2>/dev/null || true
        moved=1
    fi

    # 7. Ensure pam_gnome_keyring is disabled across all PAM stacks in target
    for pam_file in "$target/etc/pam.d"/* "$target/usr/lib/pam.d"/*; do
        [[ -f "$pam_file" ]] || continue
        keyring_disable_gnome_keyring_pam "$pam_file"
    done

    if ((moved)); then
        echo "keyring: gnome-keyring disabled and purged (KWallet owns the wallet)" >&2
    fi
    return 0
}

# Add/normalise the auth + session lines in one PAM file, idempotently.
# Login managers ship pam_kwallet lines already (plasmalogin does), but without
# `kwalletd=` they start the default daemon instead of Plasma 6's ksecretd — the
# Secret Service bridge the session actually uses.
keyring_pam_ensure() {
    local file="$1" module="$2" daemon="$3" autologin="${4:-0}" force_run="${5:-0}"

    [[ -f "$file" ]] || return 0

    # gnome-keyring first: its auth line would otherwise sit above the wallet's
    # and would be the one pam_systemd_loadkey is inserted in front of.
    keyring_disable_gnome_keyring_pam "$file"

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

    # The full stack, not just auth+session: the password hook is what keeps the
    # wallet in step when the login password changes.
    keyring_insert_password_line "$file" "$module"

    if grep -qE "$has_session" "$file"; then
        # Normalise existing line: ensure force_run (if requested) and kwalletd=$daemon
        if ((force_run)) && ! grep -qE "$has_session.*force_run" "$file"; then
            sed -i -E "s#^([[:space:]]*-?session[[:space:]]+optional[[:space:]]+pam_kwallet[56]\\.so[[:space:]]+auto_start)([[:space:]]|\$)#\\1 force_run\\2#" "$file"
        fi
        if [[ -n "$daemon" ]] && ! grep -q 'kwalletd=' "$file"; then
            sed -i -E "s#^([[:space:]]*-?session[[:space:]]+optional[[:space:]]+pam_kwallet[56]\\.so.*)\$#\\1 kwalletd=$daemon#" "$file"
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
    local module daemon file configured=0 missing_daemon=0

    if ! module="$(keyring_pam_module "$target")"; then
        echo "keyring: pam_kwallet5.so is not in the target — wallet auto-unlock disabled" >&2
        return 1
    fi
    daemon="$(keyring_daemon "$target")" || daemon=""
    if [[ -z "$daemon" ]]; then
        echo "keyring: no KWallet daemon (ksecretd/kwalletd6) in the target — the wallet cannot be unlocked" >&2
        missing_daemon=1
    fi

    local path
    for file in "${KEYRING_PAM_FILES[@]}"; do
        path="$(keyring_pam_path "$target" "$file")" || continue
        # SDDM on Syntropia runs Hyprland (UWSM), not Plasma. Without a Plasma
        # session to run pam_kwallet_init, pam_kwallet5.so requires force_run to
        # fork ksecretd directly. tty login also requires force_run. Only
        # plasmalogin relies on Plasma's native pam_kwallet_init.
        local force=0
        if [[ "$file" == "login" ]] || [[ "$file" == "sddm" ]]; then
            force=1
        fi
        keyring_pam_ensure "$path" "$module" "$daemon" 0 "$force"
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
    [[ "$missing_daemon" == 0 ]] || return 1
    return 0
}

# Enable KWallet's Secret Service bridge and configure default wallet in the
# user's config so libsecret apps use the wallet that PAM already unlocked
# instead of prompting for a new one.
keyring_write_user_config() {
    local home="$1"
    local rc="$home/.config/kwalletrc"
    mkdir -p "$home/.config"
    mkdir -p "$home/.local/share/kwalletd"
    if [[ ! -f "$rc" ]]; then
        cat >"$rc" <<'EOF'
[Wallet]
Default Wallet=kdewallet
First Use=false
Enabled=true

[org.freedesktop.secrets]
apiEnabled=true
EOF
    else
        # Ensure [Wallet] section with Default Wallet=kdewallet, First Use=false, Enabled=true
        if ! grep -q '^\[Wallet\]' "$rc"; then
            printf '\n[Wallet]\nDefault Wallet=kdewallet\nFirst Use=false\nEnabled=true\n' >>"$rc"
        else
            grep -q '^Default Wallet=' "$rc" || sed -i '/^\[Wallet\]/a Default Wallet=kdewallet' "$rc"
            grep -q '^First Use=' "$rc" || sed -i '/^\[Wallet\]/a First Use=false' "$rc"
            grep -q '^Enabled=' "$rc" || sed -i '/^\[Wallet\]/a Enabled=true' "$rc"
        fi
        # Ensure [org.freedesktop.secrets] section with apiEnabled=true
        if ! grep -q '^\[org.freedesktop.secrets\]' "$rc"; then
            printf '\n[org.freedesktop.secrets]\napiEnabled=true\n' >>"$rc"
        elif ! grep -q '^apiEnabled=true' "$rc"; then
            sed -i '/^\[org.freedesktop.secrets\]/a apiEnabled=true' "$rc"
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
    keyring_disable_gnome_keyring_secrets "$target" || status=1
    keyring_write_user_config "$target/home/$user" || status=1
    # New accounts copy /etc/skel, so seed the same setting there.
    if [[ -d "$target/etc/skel" ]]; then
        keyring_write_user_config "$target/etc/skel" || true
    fi
    return "$status"
}
