#!/bin/bash
# Installer config: the contract between the setup TUI and the runner.
# -------------------------------------------------------------------
# The TUI writes one JSON file; syntropia-install-runner reads it. Both sides
# go through here so the key names live in exactly one place.
#
# Secrets never travel in argv: `ps` / /proc/<pid>/cmdline would expose them.
# Values are passed to Python through the environment, and the file is created
# owner-only (0600) — it holds the account, root and disk passwords.

[[ -n "${SYNTROPIA_CONFIG_SH:-}" ]] && return 0
SYNTROPIA_CONFIG_SH=1

# Where the TUI writes and the runner reads. Overridable for tests/dry runs.
SYNTROPIA_INSTALL_CONFIG="${SYNTROPIA_INSTALL_CONFIG:-/run/syntropia-install/config.json}"

# config_write <path>  (values in INSTALL_* env vars)
config_write() {
    local path="${1:-$SYNTROPIA_INSTALL_CONFIG}"
    mkdir -p "$(dirname "$path")"
    (
        umask 077
        python3 - "$path" <<'PY'
import json, os, sys

env = os.environ
data = {
    "disk":          env.get("INSTALL_DISK", ""),
    "username":      env.get("INSTALL_USERNAME", "syntropia"),
    "hostname":      env.get("INSTALL_HOSTNAME", "syntropia"),
    "password":      env.get("INSTALL_PASSWORD", ""),
    # Locked root ships no root password at all; the mode is what tells the
    # runner to run `passwd -l root` instead of `chpasswd`.
    "root_password": env.get("INSTALL_ROOT_PASSWORD", ""),
    "root_password_mode": env.get("INSTALL_ROOT_PASSWORD_MODE", "locked"),
    # Hyprland (UWSM) is the only desktop the image ships; the key is kept as
    # a record of the install, not as a choice (NEXT_SESSION.md item 4).
    "desktop_env":   env.get("INSTALL_DESKTOP", "hyprland"),
    "encrypt":       env.get("INSTALL_ENCRYPT", "true") == "true",
    "keymap":        env.get("INSTALL_KEYMAP", "us"),
    "online":        env.get("INSTALL_ONLINE", "false") == "true",
}
with open(sys.argv[1], "w") as fh:
    json.dump(data, fh, indent=2)
    fh.write("\n")
PY
    )
    chmod 600 "$path"
}

# config_get <path> <key> [default] — always prints something and always exits 0,
# so callers under `set -e` never die on a missing key.
config_get() {
    local path="$1" key="$2" default="${3:-}" value=""
    value=$(python3 - "$path" "$key" "$default" 2>/dev/null <<'PY'
import json, sys

path, key, default = sys.argv[1], sys.argv[2], sys.argv[3]
try:
    with open(path) as fh:
        data = json.load(fh)
except Exception:
    data = {}
value = data.get(key, default)
if isinstance(value, bool):
    print("true" if value else "false")
else:
    print(value)
PY
    ) || value="$default"
    printf '%s' "${value:-$default}"
}
