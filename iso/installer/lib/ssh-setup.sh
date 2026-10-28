#!/bin/bash
# One-command SSH setup helper for fresh Syntropia installs.
# ----------------------------------------------------------
# Shipped to /usr/local/bin/syntropia-ssh-setup (and carried in
# /usr/local/lib/syntropia-installer/ssh-setup.sh) by iso/build.sh,
# syntropia-install-runner, and hook-branding-users.sh.
#
# Per agent-rules/software-inclusion-policy.md, openssh is Tier 2 / opt-in:
# fresh music-production installs do not run sshd until the user asks for it
# (either from the first-boot wizard's "SSH Setup" pick or by running
# `syntropia-ssh-setup` in a terminal).
#
# Behavior:
#   1. Re-exec via `sudo -E` when invoked interactively (TTY stdin+stdout) as a
#      non-root user and `sudo` is available (unless SYNTROPIA_SSH_NO_SUDO is
#      set); fall back to printing instructions when unprivileged.
#   2. Resolve the real target user and home directory first (under sudo, use
#      SUDO_USER's passwd entry rather than /root).
#   3. Install openssh via pacman and enable/start sshd when root.
#   4. Generate an ed25519 keypair in <target-home>/.ssh/id_ed25519 (supporting
#      SYNTROPIA_SSH_KEY_PASSPHRASE, warning explicitly when passphrase-less,
#      and chowning .ssh to the target user when running as root).
#   5. When root and <target-home>/.ssh/authorized_keys exists, write
#      /etc/ssh/sshd_config.d/50-syntropia-ssh.conf (644, root:root), validate
#      with `sshd -t` (removing the drop-in on failure), and restart sshd.
#   6. Print LAN IPv4 addresses and a ready-to-run `ssh-copy-id` hint.

set -euo pipefail

ssh_setup_is_root() {
    local euid="${SYNTROPIA_EUID:-${EUID:-$(id -u)}}"
    [[ "$euid" -eq 0 ]]
}

ssh_setup_target_user() {
    if ssh_setup_is_root && [[ -n "${SUDO_USER:-}" ]]; then
        printf '%s\n' "$SUDO_USER"
    else
        printf '%s\n' "${SUDO_USER:-${USER:-$(id -un 2>/dev/null || echo syntropia)}}"
    fi
}

ssh_setup_target_home() {
    local sudo_home=""
    if ssh_setup_is_root && [[ -n "${SUDO_USER:-}" ]]; then
        sudo_home="$(getent passwd "$SUDO_USER" | cut -d: -f6)"
        if [[ -n "$sudo_home" ]]; then
            printf '%s\n' "$sudo_home"
            return 0
        fi
    fi
    if [[ -n "${HOME:-}" ]]; then
        printf '%s\n' "$HOME"
        return 0
    fi
    getent passwd "$(ssh_setup_target_user)" 2>/dev/null | cut -d: -f6 || true
}

ssh_setup_has_openssh() {
    if command -v pacman >/dev/null 2>&1; then
        pacman -Q openssh >/dev/null 2>&1
        return $?
    fi
    command -v sshd >/dev/null 2>&1
}

ssh_setup_ensure_openssh() {
    if ssh_setup_has_openssh; then
        echo "openssh: already installed"
        return 0
    fi
    if ssh_setup_is_root; then
        echo "openssh: installing via pacman..."
        pacman -S --noconfirm --needed openssh
    else
        echo "openssh: not installed — run as root to install:"
        echo "  sudo pacman -S --needed openssh"
    fi
}

ssh_setup_enable_sshd() {
    if ssh_setup_is_root; then
        echo "sshd: enabling and starting sshd..."
        systemctl enable --now sshd
    else
        echo "sshd: not root — skipping service activation. Run:"
        echo "  sudo systemctl enable --now sshd"
    fi
}

ssh_setup_ensure_keypair() {
    local home_dir="${1:-}"
    local owner="${2:-}"
    if [[ -z "$owner" ]]; then
        owner="$(ssh_setup_target_user)"
    fi
    if [[ -z "$home_dir" ]]; then
        home_dir="$(ssh_setup_target_home)"
    fi
    [[ -n "$home_dir" ]] || return 0

    local ssh_dir="$home_dir/.ssh"
    local key_file="$ssh_dir/id_ed25519"
    local passphrase="${SYNTROPIA_SSH_KEY_PASSPHRASE:-}"

    mkdir -p "$ssh_dir"
    chmod 700 "$ssh_dir"

    if [[ -f "$key_file" ]]; then
        if ssh_setup_is_root && [[ -n "$owner" ]]; then
            chown -R "$owner:" "$ssh_dir"
        fi
        echo "ssh-keygen: keypair already exists at $key_file"
        return 0
    fi

    if ! command -v ssh-keygen >/dev/null 2>&1; then
        if ssh_setup_is_root && [[ -n "$owner" ]]; then
            chown -R "$owner:" "$ssh_dir"
        fi
        echo "ssh-keygen: not found (install openssh first to generate $key_file)"
        return 0
    fi

    ssh-keygen -t ed25519 -f "$key_file" -N "$passphrase" -q
    if ssh_setup_is_root && [[ -n "$owner" ]]; then
        chown -R "$owner:" "$ssh_dir"
    fi
    echo "ssh-keygen: generated ed25519 keypair at $key_file"
    if [[ -z "$passphrase" ]]; then
        echo "WARNING: key created WITHOUT a passphrase — anyone who reads ~/.ssh/id_ed25519 owns every host you copy it to"
    fi
}

ssh_setup_harden_sshd() {
    local home_dir="${1:-}"
    local target_user="${2:-}"
    if [[ -z "$target_user" ]]; then
        target_user="$(ssh_setup_target_user)"
    fi
    if [[ -z "$home_dir" ]]; then
        home_dir="$(ssh_setup_target_home)"
    fi

    if ! ssh_setup_is_root; then
        return 0
    fi

    if [[ -z "$home_dir" || ! -f "$home_dir/.ssh/id_ed25519" ]]; then
        return 0
    fi

    local auth_keys="$home_dir/.ssh/authorized_keys"
    if [[ ! -f "$auth_keys" ]]; then
        echo "sshd hardening: key-copy not done yet ($auth_keys missing), hardening skipped, rerun after ssh-copy-id"
        return 0
    fi

    local dropin_dir="${SYNTROPIA_SSHD_CONFIG_D:-${SYNTROPIA_ROOT:-}/etc/ssh/sshd_config.d}"
    local dropin_file="$dropin_dir/50-syntropia-ssh.conf"

    mkdir -p "$dropin_dir"
    cat > "$dropin_file" <<EOF
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
AllowUsers $target_user
EOF
    chmod 644 "$dropin_file"
    chown root:root "$dropin_file"

    if ! sshd -t; then
        rm -f "$dropin_file"
        echo "ERROR: sshd -t validation failed — removed $dropin_file"
        echo "ERROR: sshd -t validation failed — removed $dropin_file" >&2
        return 1
    fi

    echo "sshd hardening: applied $dropin_file"
    systemctl restart sshd
}

ssh_setup_lan_ipv4() {
    command -v ip >/dev/null 2>&1 || return 0
    ip -4 addr 2>/dev/null | awk '
        /^[0-9]+:/ {
            iface = $2
            sub(/:$/, "", iface)
            sub(/@.*/, "", iface)
        }
        /inet / {
            addr = ""
            line_iface = iface
            for (i = 1; i <= NF; i++) {
                if ($i == "inet") {
                    addr = $(i + 1)
                    sub(/\/.*/, "", addr)
                    break
                }
            }
            if (line_iface == "") {
                line_iface = $NF
            }
            if (line_iface ~ /^(lo|docker[0-9a-z_-]*|veth[0-9a-z_-]*|br-[0-9a-z_-]*|virbr[0-9a-z_-]*)$/) next
            if (addr ~ /^(127\.|169\.254\.|172\.(1[7-9]|2[0-9]|3[0-1])\.)/) next
            if (addr != "" && !seen[addr]++) print addr
        }
    '
}

ssh_setup_main() {
    if ! ssh_setup_is_root && [[ -z "${SYNTROPIA_SSH_NO_SUDO:-}" ]] && [[ -t 0 && -t 1 ]]; then
        if command -v sudo >/dev/null 2>&1; then
            echo "syntropia-ssh-setup: root privileges are needed to install openssh and enable sshd."
            echo "Re-running via sudo (enter your account password if prompted)..."
            exec sudo -E "${BASH_SOURCE[0]}" "$@"
        fi
    fi

    local target_user target_home
    local -a ips=()
    local ip_addr=""

    target_user="$(ssh_setup_target_user)"
    target_home="$(ssh_setup_target_home)"

    ssh_setup_ensure_openssh
    ssh_setup_enable_sshd
    ssh_setup_ensure_keypair "$target_home" "$target_user"
    ssh_setup_harden_sshd "$target_home" "$target_user"

    mapfile -t ips < <(ssh_setup_lan_ipv4)
    if ((${#ips[@]} > 0)); then
        echo "LAN IPv4 addresses:"
        for ip_addr in "${ips[@]}"; do
            echo "  $ip_addr"
        done
        echo "Copy your key from another machine with:"
        echo "  ssh-copy-id ${target_user}@${ips[0]}"
    else
        echo "LAN IPv4 addresses: none detected"
        echo "Copy your key from another machine once connected:"
        echo "  ssh-copy-id ${target_user}@<LAN-IP>"
    fi
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    ssh_setup_main "$@"
fi
