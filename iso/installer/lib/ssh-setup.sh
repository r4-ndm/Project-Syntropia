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
# Preferred use is ONE command, because it never opens password login:
#
#     sudo syntropia-ssh-setup --key "ssh-ed25519 AAAA... you@laptop"
#
# With a key supplied the order is authorize -> harden -> start sshd, so sshd
# is not reachable until passwords are already locked out. The legacy no-flag
# path still works (start sshd, ssh-copy-id, re-run to harden) but leaves
# password authentication open in between and says so loudly.
#
# Behavior:
#   0. --key/--key-file/--github install authorized_keys for the target user,
#      validating each line is a real SSH public key; duplicates are skipped.
#      With no key flag and a TTY on stdin it PROMPTS for one (Enter skips;
#      SYNTROPIA_SSH_NO_PROMPT=1 disables), so the first-boot wizard route gets
#      the same one-pass hardening.
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
#      /etc/ssh/sshd_config.d/00-syntropia-ssh.conf (644, root:root) — "00" so
#      it is read before archiso's own 10-archiso.conf, which ships
#      PasswordAuthentication/PermitRootLogin "yes" for the live session and
#      survives into the installed target. sshd uses the FIRST value it reads
#      for a keyword, so file ordering alone decides the winner; this also
#      directly neutralizes any 10-archiso.conf found in the same directory
#      (do not trust ordering alone), including its keyboard-interactive
#      directives and its misleading comment. Validates with `sshd -t`,
#      restarts sshd, then re-derives the EFFECTIVE config with `sshd -T` and
#      reverts + fails loudly if anything still outbids the hardening. ALL
#      FOUR directives the drop-in writes are verified: omitting
#      KbdInteractiveAuthentication would let PAM serve a password prompt on a
#      box reported as hardened.
#   6. Print LAN IPv4 addresses and a ready-to-run `ssh-copy-id` hint. When no
#      key was authorized, also print every route to closing the password
#      window (--key, ssh-copy-id, --github, or disabling sshd).

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

ssh_setup_usage() {
    cat <<'EOF'
syntropia-ssh-setup — set up an SSH server on this machine.

THE EASY WAY (one command, no password login ever enabled):

  1. On the machine you want to connect FROM:
         cat ~/.ssh/id_ed25519.pub
     (no key there yet? run: ssh-keygen -t ed25519)

  2. Here, paste it in:
         sudo syntropia-ssh-setup --key "ssh-ed25519 AAAA... you@laptop"

  That authorizes the key, hardens sshd and starts it, in that order,
  so sshd is never reachable with password login.

Options:
  --key "<pubkey>"     Authorize this public key. May be repeated.
  --key-file <path>    Authorize every key in a file ("-" reads stdin).
  --github <user>      Authorize the keys published at github.com/<user>.keys
  -h, --help           Show this help.

With no options it installs openssh, starts sshd and generates a local
keypair, but CANNOT harden until a key is authorized — leaving password
login open until you run ssh-copy-id and re-run this. Prefer --key.
EOF
}

# Accept only key types sshd actually honours, so a pasted fragment or a
# private key can never end up in authorized_keys looking plausible.
ssh_setup_valid_pubkey() {
    local key="${1:-}"
    [[ "$key" =~ ^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp256|ecdsa-sha2-nistp384|ecdsa-sha2-nistp521|sk-ssh-ed25519@openssh\.com|sk-ecdsa-sha2-nistp256@openssh\.com)[[:space:]]+[A-Za-z0-9+/]+=*([[:space:]].*)?$ ]]
}

# The key body (type + base64) without the trailing comment, for dedupe.
ssh_setup_key_body() {
    awk '{print $1" "$2}' <<<"${1:-}"
}

ssh_setup_read_key_file() {
    local path="${1:-}"
    if [[ "$path" == "-" ]]; then
        cat
    elif [[ -r "$path" ]]; then
        cat -- "$path"
    else
        echo "ERROR: cannot read key file: $path" >&2
        return 1
    fi
}

ssh_setup_fetch_github_keys() {
    local user="${1:-}"
    if ! command -v curl >/dev/null 2>&1; then
        echo "ERROR: --github needs curl, which is not installed" >&2
        return 1
    fi
    local url="https://github.com/${user}.keys"
    local body
    if ! body="$(curl -fsSL --max-time 20 "$url" 2>/dev/null)"; then
        echo "ERROR: could not fetch $url" >&2
        return 1
    fi
    if [[ -z "${body//[[:space:]]/}" ]]; then
        echo "ERROR: github.com/${user} publishes no SSH keys" >&2
        return 1
    fi
    printf '%s\n' "$body"
}

# Append authorized keys for the target user. Needs no root: the file lives in
# the user's own home. Returns 1 if nothing valid was installed.
ssh_setup_install_authorized_keys() {
    local home_dir="${1:-}"
    local owner="${2:-}"
    shift 2 || true
    local -a keys=("$@")

    ((${#keys[@]} > 0)) || return 1
    if [[ -z "$home_dir" ]]; then
        echo "ERROR: cannot resolve the target home directory" >&2
        return 1
    fi

    local ssh_dir="$home_dir/.ssh"
    local auth_keys="$ssh_dir/authorized_keys"
    mkdir -p "$ssh_dir"
    chmod 700 "$ssh_dir"
    [[ -f "$auth_keys" ]] || : > "$auth_keys"
    chmod 600 "$auth_keys"

    local key body installed=0 skipped=0
    for key in "${keys[@]}"; do
        key="${key#"${key%%[![:space:]]*}"}"
        key="${key%"${key##*[![:space:]]}"}"
        [[ -n "$key" ]] || continue
        if ! ssh_setup_valid_pubkey "$key"; then
            echo "authorized_keys: ignoring line that is not an SSH public key: ${key:0:40}..." >&2
            skipped=$((skipped + 1))
            continue
        fi
        body="$(ssh_setup_key_body "$key")"
        if grep -qF -- "$body" "$auth_keys" 2>/dev/null; then
            echo "authorized_keys: already present, skipping duplicate"
            continue
        fi
        printf '%s\n' "$key" >> "$auth_keys"
        installed=$((installed + 1))
    done

    if ssh_setup_is_root && [[ -n "$owner" ]]; then
        chown -R "$owner:" "$ssh_dir"
    fi

    if ((installed > 0)); then
        echo "authorized_keys: installed $installed key(s) for ${owner:-the target user}"
        return 0
    fi
    if ((skipped > 0)); then
        echo "ERROR: no valid public keys supplied — nothing authorized" >&2
        return 1
    fi
    # Only duplicates: the key is authorized, so hardening may proceed.
    return 0
}

# Ask for the client's public key when none was passed. The prompt goes to
# stderr, not stdout: callers pipe our stdout (the first-boot wizard runs us
# through `tee`), and stdout here carries the accepted key back to the caller.
# Reads stdin, which the caller has already confirmed is a TTY.
# Returns 1 when the user skips, so the caller falls back to the legacy flow.
ssh_setup_prompt_for_key() {
    local attempt line
    for attempt in 1 2 3; do
        {
            echo ""
            echo "Set up access from another machine now?"
            echo "On the machine you want to connect FROM, run:"
            echo "    cat ~/.ssh/id_ed25519.pub"
            echo "(nothing there? run 'ssh-keygen -t ed25519' there first)"
            echo "Paste that line below, or press Enter to skip."
            printf 'public key> '
        } >&2
        read -r line || return 1
        line="${line#"${line%%[![:space:]]*}"}"
        line="${line%"${line##*[![:space:]]}"}"
        [[ -n "$line" ]] || return 1
        if ssh_setup_valid_pubkey "$line"; then
            printf '%s\n' "$line"
            return 0
        fi
        echo "Not an SSH public key — expected something like 'ssh-ed25519 AAAA... you@host'." >&2
    done
    echo "Giving up on the key prompt; continuing without it." >&2
    return 1
}

ssh_setup_host_fingerprint() {
    local dir="${SYNTROPIA_SSH_HOST_KEY_DIR:-${SYNTROPIA_ROOT:-}/etc/ssh}"
    local pub="$dir/ssh_host_ed25519_key.pub"
    [[ -r "$pub" ]] || return 0
    command -v ssh-keygen >/dev/null 2>&1 || return 0
    ssh-keygen -lf "$pub" 2>/dev/null | awk '{print $2}'
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

    # Deliberately NOT gated on a local id_ed25519: that key is for this host
    # connecting outward and has nothing to do with who may log in here.
    # authorized_keys is the only thing that decides whether locking out
    # passwords is survivable.
    if [[ -z "$home_dir" ]]; then
        echo "sshd hardening: cannot resolve the target home directory, hardening skipped" >&2
        return 0
    fi

    local auth_keys="$home_dir/.ssh/authorized_keys"
    if [[ ! -f "$auth_keys" || ! -s "$auth_keys" ]]; then
        echo "sshd hardening: key-copy not done yet ($auth_keys missing), hardening skipped, rerun after ssh-copy-id"
        return 0
    fi

    local dropin_dir="${SYNTROPIA_SSHD_CONFIG_D:-${SYNTROPIA_ROOT:-}/etc/ssh/sshd_config.d}"
    local dropin_file="$dropin_dir/00-syntropia-ssh.conf"
    local legacy_dropin="$dropin_dir/50-syntropia-ssh.conf"
    local archiso_dropin="$dropin_dir/10-archiso.conf"

    mkdir -p "$dropin_dir"

    # sshd uses the first value it reads for a keyword, so the archiso live-ISO
    # leftover (PasswordAuthentication/PermitRootLogin "yes") would otherwise
    # win outright once it sorts before our drop-in. "00" fixes read order, but
    # do not trust ordering alone: neutralize the archiso file's values too.
    if [[ -f "$archiso_dropin" ]]; then
        sed -i \
            -e 's/^\([[:space:]]*PasswordAuthentication[[:space:]]\+\)yes/\1no/I' \
            -e 's/^\([[:space:]]*KbdInteractiveAuthentication[[:space:]]\+\)yes/\1no/I' \
            -e 's/^\([[:space:]]*ChallengeResponseAuthentication[[:space:]]\+\)yes/\1no/I' \
            -e 's/^\([[:space:]]*PermitRootLogin[[:space:]]\+\)yes/\1prohibit-password/I' \
            "$archiso_dropin" \
            && sed -i \
            -e 's|^# Allow root login using password authentication$|# Neutralized by syntropia-ssh-setup: the directives below were flipped to\n# deny password and root logins. The original archiso comment claimed the\n# opposite and no longer describes this file.|' \
            "$archiso_dropin"
    fi

    cat > "$dropin_file" <<EOF
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
AllowUsers $target_user
EOF
    chmod 644 "$dropin_file"
    chown root:root "$dropin_file"
    rm -f "$legacy_dropin"

    if ! sshd -t; then
        rm -f "$dropin_file"
        echo "ERROR: sshd -t validation failed — removed $dropin_file"
        echo "ERROR: sshd -t validation failed — removed $dropin_file" >&2
        return 1
    fi

    systemctl restart sshd

    # A file that looks correct is not the same as sshd agreeing: re-derive the
    # EFFECTIVE config sshd would actually apply and fail loudly (reverting our
    # drop-in) if anything still outbids the hardening.
    local effective
    effective="$(sshd -T 2>/dev/null)"
    # Every directive the drop-in writes is verified here. Leaving one out
    # means something could outbid it and hardening would still report
    # success — KbdInteractiveAuthentication is the dangerous one to miss,
    # since PAM can serve a password prompt through it even with
    # PasswordAuthentication no.
    if ! grep -qix 'passwordauthentication no' <<<"$effective" \
        || ! grep -qix 'kbdinteractiveauthentication no' <<<"$effective" \
        || ! grep -qix 'permitrootlogin prohibit-password' <<<"$effective" \
        || ! grep -qix "allowusers $target_user" <<<"$effective"; then
        rm -f "$dropin_file"
        echo "ERROR: effective sshd config does not match the intended hardening — removed $dropin_file" >&2
        echo "$effective" | grep -iE '^(passwordauthentication|kbdinteractiveauthentication|permitrootlogin|allowusers) ' >&2 || true
        systemctl restart sshd
        return 1
    fi

    echo "sshd hardening: applied $dropin_file (effective config verified)"
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
    local -a argv=("$@")
    local -a keys=()
    local arg raw

    # --help must never trigger a sudo prompt, so scan for it before re-exec.
    for arg in "${argv[@]}"; do
        case "$arg" in
            -h|--help)
                ssh_setup_usage
                return 0
                ;;
        esac
    done

    # Gate on stdin only. sudo prompts on /dev/tty, not stdout, so demanding
    # `-t 1` here meant any caller that piped our output got no escalation at
    # all: the first-boot wizard runs us through `tee`, so picking "SSH Setup"
    # silently did nothing but print instructions and exit 0.
    if ! ssh_setup_is_root && [[ -z "${SYNTROPIA_SSH_NO_SUDO:-}" ]] && [[ -t 0 ]]; then
        if command -v sudo >/dev/null 2>&1; then
            echo "syntropia-ssh-setup: root privileges are needed to install openssh and enable sshd."
            echo "Re-running via sudo (enter your account password if prompted)..."
            exec sudo -E "${BASH_SOURCE[0]}" "${argv[@]}"
        fi
    fi

    while (($#)); do
        case "$1" in
            --key)
                shift || true
                [[ $# -gt 0 ]] || { echo "ERROR: --key needs a value" >&2; return 2; }
                keys+=("$1")
                ;;
            --key=*)   keys+=("${1#--key=}") ;;
            --key-file|--key-file=*|--github|--github=*)
                case "$1" in
                    --key-file=*) raw="$(ssh_setup_read_key_file "${1#--key-file=}")" || return 1 ;;
                    --github=*)   raw="$(ssh_setup_fetch_github_keys "${1#--github=}")" || return 1 ;;
                    --key-file)
                        shift || true
                        [[ $# -gt 0 ]] || { echo "ERROR: --key-file needs a path" >&2; return 2; }
                        raw="$(ssh_setup_read_key_file "$1")" || return 1
                        ;;
                    --github)
                        shift || true
                        [[ $# -gt 0 ]] || { echo "ERROR: --github needs a username" >&2; return 2; }
                        raw="$(ssh_setup_fetch_github_keys "$1")" || return 1
                        ;;
                esac
                while IFS= read -r arg; do
                    [[ -n "${arg//[[:space:]]/}" ]] || continue
                    [[ "$arg" == \#* ]] && continue
                    keys+=("$arg")
                done <<<"$raw"
                ;;
            *)
                echo "ERROR: unknown option: $1" >&2
                ssh_setup_usage >&2
                return 2
                ;;
        esac
        shift || true
    done

    local target_user target_home fingerprint
    local -a ips=()
    local ip_addr=""
    local host=""

    target_user="$(ssh_setup_target_user)"
    target_home="$(ssh_setup_target_home)"

    ssh_setup_ensure_openssh

    # No key on the command line, but someone is sitting at a terminal: ask,
    # so the interactive and wizard routes get the same one-pass hardening the
    # --key flag gives instead of a sshd left open to passwords.
    local prompted=""
    if ((${#keys[@]} == 0)) && [[ -z "${SYNTROPIA_SSH_NO_PROMPT:-}" ]] && [[ -t 0 ]]; then
        if prompted="$(ssh_setup_prompt_for_key)" && [[ -n "$prompted" ]]; then
            keys+=("$prompted")
        fi
    fi

    if ((${#keys[@]} > 0)); then
        # Authorize, harden, THEN start: sshd must never be reachable while
        # password authentication is still permitted.
        ssh_setup_install_authorized_keys "$target_home" "$target_user" "${keys[@]}" || return 1
        ssh_setup_harden_sshd "$target_home" "$target_user" || return 1
        ssh_setup_enable_sshd
    else
        ssh_setup_enable_sshd
        ssh_setup_ensure_keypair "$target_home" "$target_user"
        ssh_setup_harden_sshd "$target_home" "$target_user" || return 1
    fi

    mapfile -t ips < <(ssh_setup_lan_ipv4)
    if ((${#ips[@]} > 0)); then
        echo "LAN IPv4 addresses:"
        for ip_addr in "${ips[@]}"; do
            echo "  $ip_addr"
        done
        host="${ips[0]}"
    else
        echo "LAN IPv4 addresses: none detected"
        host="<LAN-IP>"
    fi

    if ((${#keys[@]} > 0)); then
        echo "Connect from the machine whose key you just authorized:"
        echo "  ssh ${target_user}@${host}"
        fingerprint="$(ssh_setup_host_fingerprint)"
        if [[ -n "$fingerprint" ]]; then
            echo "Host key fingerprint (expect this on first connect):"
            echo "  $fingerprint"
        fi
    else
        echo "Copy your key from another machine with:"
        echo "  ssh-copy-id ${target_user}@${host}"
        echo "then re-run syntropia-ssh-setup here to lock out password logins."
        if ssh_setup_is_root; then
            echo ""
            echo "WARNING: password login is OPEN until you do. Anyone who can reach"
            echo "WARNING: this machine on the network may attempt to log in."
            echo ""
            echo "Close it now, by whichever route suits you:"
            echo "  - already have a key here?   sudo syntropia-ssh-setup --key \"\$(cat ~/.ssh/id_ed25519.pub)\""
            echo "  - key on the other machine?  ssh-copy-id ${target_user}@${host}  then re-run this"
            echo "  - keys published on GitHub?  sudo syntropia-ssh-setup --github <your-user>"
            echo "  - not using SSH after all?   sudo systemctl disable --now sshd"
        fi
    fi
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    ssh_setup_main "$@"
fi
