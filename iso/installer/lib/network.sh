#!/bin/bash
# Network availability and guided connection for the Syntropia live installer.
# --------------------------------------------------------------------------
# The install itself works offline (the runner copies the live image to disk),
# but the desktop we pre-install and the first-boot app wizard need packages.
# So the installer asks once, up front, and records the answer for the runner.
#
# NetworkManager's nmcli is the live image's connection tool (CachyOS ships it
# and the target enables NetworkManager.service). Everything here degrades
# gracefully when nmcli is missing: print what to do, never hang the install.

[[ -n "${SYNTROPIA_NETWORK_SH:-}" ]] && return 0
SYNTROPIA_NETWORK_SH=1

[[ -n "${SYNTROPIA_COMMON_SH:-}" ]] || source "$(dirname "${BASH_SOURCE[0]}")/common.sh"
# network_wifi_connect reuses the masked-passphrase prompt.
[[ -n "${SYNTROPIA_PASSWORD_SH:-}" ]] || source "$(dirname "${BASH_SOURCE[0]}")/password.sh"

NETWORK_PROBE_HOST="${NETWORK_PROBE_HOST:-archlinux.org}"
INSTALL_ONLINE=false

# A default route means the kernel has somewhere to send packets. It does not
# mean the network works (captive portals, dead uplink), so it is only step one.
network_link_up() {
    if ! command -v ip >/dev/null 2>&1; then
        return 1
    fi
    ip route 2>/dev/null | grep -q '^default'
}

# Online = link up AND (ICMP reaches 1.1.1.1 OR DNS resolves a real host).
# ICMP is the cheapest check; the DNS fallback covers networks that drop ping.
network_online() {
    network_link_up || return 1
    if command -v ping >/dev/null 2>&1 && ping -c1 -W2 -q 1.1.1.1 >/dev/null 2>&1; then
        return 0
    fi
    if command -v getent >/dev/null 2>&1 && getent hosts "$NETWORK_PROBE_HOST" >/dev/null 2>&1; then
        return 0
    fi
    return 1
}

# Poll for up to N seconds — a DHCP lease or a Wi-Fi association takes a moment
# and the user should not have to press "check again" for that.
network_wait_online() {
    local seconds="${1:-15}" waited=0
    while ((waited < seconds)); do
        network_online && return 0
        sleep 1
        waited=$((waited + 1))
    done
    return 1
}

network_status_line() {
    local line=""
    if command -v nmcli >/dev/null 2>&1; then
        line=$(nmcli -t -f DEVICE,TYPE,STATE device status 2>/dev/null |
            awk -F: '$3 == "connected" { printf "%s%s (%s)", sep, $1, $2; sep = ", " }')
    fi
    [[ -n "$line" ]] || line="default route present"
    printf '%s' "$line"
}

# Ask for a Wi-Fi network and try to join it. Returns 0 when a connection was
# attempted successfully (the caller re-checks reachability).
network_wifi_connect() {
    if ! command -v nmcli >/dev/null 2>&1; then
        note "$YELLOW" "!" "NetworkManager (nmcli) is not available in this image."
        note "$DIM" " " "plug in an Ethernet cable, or use iwctl from another TTY (Ctrl+Alt+F2)."
        return 1
    fi

    local -a ssids=()
    local choice="" idx=0 ssid="" pass=""
    nmcli radio wifi on >/dev/null 2>&1 || true

    note "$DIM" " " "scanning for Wi-Fi networks…"
    mapfile -t ssids < <(nmcli -t -f SSID device wifi list --rescan yes 2>/dev/null |
        sed 's/\\:/:/g' | awk 'length($0) > 0 && !seen[$0]++')
    if ((${#ssids[@]} == 0)); then
        note "$YELLOW" "!" "no Wi-Fi networks found."
        note "$DIM" " " "check that the Wi-Fi radio is on, or use an Ethernet cable."
        return 1
    fi

    printf '%s  %sAvailable networks:%s\n' "$INDENT" "$BOLD" "$RESET"
    for idx in "${!ssids[@]}"; do
        printf '%s    [%d] %s\n' "$INDENT" "$((idx + 1))" "${ssids[$idx]}"
    done
    printf '\n'

    ask_line "Network number (q to cancel)" choice "" || return 1
    if [[ -z "$choice" || "$choice" =~ ^[qQ]$ ]]; then
        return 1
    fi
    if ! [[ "$choice" =~ ^[0-9]+$ ]] || ((choice < 1 || choice > ${#ssids[@]})); then
        note "$RED" "✗" "that is not one of the listed networks."
        return 1
    fi
    ssid="${ssids[$((choice - 1))]}"

    note "$DIM" " " "connecting to \"$ssid\"…"
    # Try without a passphrase first: open networks and already-saved ones work,
    # and asking for a key on an open network is a confusing dead end.
    if timeout 60 nmcli device wifi connect "$ssid" >/dev/null 2>&1; then
        network_wait_online 15 || true
        note "$GREEN" "✓" "connected to \"$ssid\""
        return 0
    fi

    password_header "Wi-Fi passphrase" "Network \"$ssid\"."
    password_row_prompt "Passphrase"
    password_read_hidden pass || return 1

    if timeout 90 nmcli device wifi connect "$ssid" password "$pass" >/dev/null 2>&1; then
        network_wait_online 15 || true
        note "$GREEN" "✓" "connected to \"$ssid\""
        return 0
    fi

    note "$RED" "✗" "could not join \"$ssid\" — the passphrase may be wrong, or the signal too weak."
    return 1
}

# Hand the terminal to NetworkManager's own UI. The installer's Wi-Fi menu is
# the short path; nmtui is the fallback for hidden SSIDs, enterprise WPA,
# VLANs and static addresses, and it is what "connect with NetworkManager"
# means to an Arch user.
network_nmtui() {
    if command -v nmtui-connect >/dev/null 2>&1; then
        nmtui-connect || true
    elif command -v nmtui >/dev/null 2>&1; then
        nmtui || true
    else
        note "$YELLOW" "!" "nmtui is not available in this image."
        note "$DIM" " " "use nmcli, or iwctl on another TTY (Ctrl+Alt+F2)."
        return 1
    fi
    network_wait_online 10 || true
    if network_online; then
        note "$GREEN" "✓" "online — $(network_status_line)"
    else
        note "$YELLOW" "!" "still offline."
    fi
}

# The install-time network step: status line plus a menu when offline. Sets
# INSTALL_ONLINE for the config, so the runner knows whether it may reach the
# package repos during the install.
network_prompt() {
    local answer=""

    section_rule "Internet connection"
    printf '%s  The install runs offline, but packages (desktop, apps you pick%s\n' "$INDENT" "$RESET"
    printf '%s  %slater) need a connection at some point.%s\n\n' "$INDENT" "$DIM" "$RESET"

    while :; do
        if network_online; then
            INSTALL_ONLINE=true
            note "$GREEN" "✓" "online — $(network_status_line)"
            return 0
        fi

        INSTALL_ONLINE=false
        note "$YELLOW" "!" "no internet connection detected."
        printf '\n'
        printf '%s    [1] Connect to Wi-Fi\n' "$INDENT"
        printf '%s    [2] Check the connection again\n' "$INDENT"
        printf '%s    [3] Continue without internet\n' "$INDENT"
        printf '%s    [4] NetworkManager UI (nmtui-connect) — hidden/enterprise networks\n\n' "$INDENT"
        printf '%s  %sEthernet is already trying: plug in a cable and press 2.%s\n\n' "$INDENT" "$DIM" "$RESET"

        ask_line "Choose [1-4]" answer "2" || answer="3"
        case "${answer:-2}" in
            1) network_wifi_connect || true ;;
            4) network_nmtui || true ;;
            3)
                note "$YELLOW" "!" "installing offline."
                note "$DIM" " " "the first-boot app wizard queues your picks and installs them once you're online."
                return 0
                ;;
            *)
                note "$DIM" " " "re-checking…"
                ;;
        esac
    done
}
