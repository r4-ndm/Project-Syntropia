"""Tests for the installed system's keyring auto-unlock (iso/installer/lib/keyring.sh).

The 2026-10-21 laptop install asked the user to create a NEW keyring password on
first login, and the 2026-10-25 install (SDDM + Hyprland instead of plasmalogin)
prompted again. The image ships KWallet *and* gnome-keyring, and a wallet is only
created/unlocked silently when pam_kwallet receives the login password. These
tests drive the real library against a fake target tree — no PAM, no chroot.
"""

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LIB = REPO / "iso" / "installer" / "lib" / "keyring.sh"
UNLOCK_HELPER = REPO / "iso" / "installer" / "lib" / "syntropia-kwallet-unlock"
UNLOCK_SERVICE = REPO / "iso" / "installer" / "lib" / "syntropia-kwallet-unlock.service"
RUNNER = REPO / "iso" / "installer" / "syntropia-install-runner"
BUILD = REPO / "iso" / "build.sh"
BRANDING_HOOK = REPO / "iso" / "hook-scripts" / "hook-branding-users.sh"

BASE_ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}

PAM_STOCK = """#%PAM-1.0
auth       include      system-login
account    include      system-login
password   include      system-login
session    include      system-login
"""


def target(tmp_path: Path, *, module: bool = True, loadkey: bool = True,
           daemon: str = "ksecretd", pam_files=("plasmalogin",),
           name: str = "target") -> Path:
    root = tmp_path / name
    (root / "usr" / "lib" / "security").mkdir(parents=True, exist_ok=True)
    (root / "etc" / "pam.d").mkdir(parents=True, exist_ok=True)
    (root / "usr" / "bin").mkdir(parents=True, exist_ok=True)
    # A current image ships socat alongside pam_kwallet; the offline warning is
    # tested separately with a target that lacks it.
    (root / "usr" / "bin" / "socat").write_text("#!/bin/sh\n")
    (root / "usr" / "bin" / "socat").chmod(0o755)
    (root / "home" / "producer").mkdir(parents=True, exist_ok=True)
    (root / "etc" / "skel").mkdir(parents=True, exist_ok=True)

    if module:
        (root / "usr" / "lib" / "security" / "pam_kwallet5.so").write_bytes(b"so")
    if loadkey:
        (root / "usr" / "lib" / "security" / "pam_systemd_loadkey.so").write_bytes(b"so")
    if daemon:
        (root / "usr" / "bin" / daemon).write_text("#!/bin/sh\n")
        (root / "usr" / "bin" / daemon).chmod(0o755)
    for name in pam_files:
        (root / "etc" / "pam.d" / name).write_text(PAM_STOCK)
    return root


def call(function: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-c", f'source "{LIB}"; {function} "$@"', "_", *args],
        capture_output=True,
        text=True,
        env=BASE_ENV,
        timeout=60,
    )


# --- detection ------------------------------------------------------------

def test_pam_module_is_found(tmp_path: Path) -> None:
    result = call("keyring_pam_module", str(target(tmp_path)))
    assert result.returncode == 0
    assert result.stdout == "pam_kwallet5.so"


def test_pam_kwallet6_is_accepted_when_5_is_absent(tmp_path: Path) -> None:
    root = target(tmp_path, module=False)
    (root / "usr" / "lib" / "security" / "pam_kwallet6.so").write_bytes(b"so")
    assert call("keyring_pam_module", str(root)).stdout == "pam_kwallet6.so"


def test_missing_module_is_a_failure_not_an_empty_path(tmp_path: Path) -> None:
    root = target(tmp_path, module=False)
    result = call("keyring_pam_module", str(root))
    assert result.returncode == 1
    assert result.stdout == ""


def test_daemon_prefers_ksecretd(tmp_path: Path) -> None:
    root = target(tmp_path)
    (root / "usr" / "bin" / "kwalletd6").write_text("#!/bin/sh\n")
    (root / "usr" / "bin" / "kwalletd6").chmod(0o755)
    assert call("keyring_daemon", str(root)).stdout == "/usr/bin/ksecretd"


def test_autologin_needs_pam_kwallet_and_loadkey(tmp_path: Path) -> None:
    no_loadkey = target(tmp_path, loadkey=False, name="no-loadkey")
    no_module = target(tmp_path, module=False, name="no-module")
    complete = target(tmp_path, name="complete")

    assert call("keyring_can_feed_autologin", str(no_loadkey)).returncode != 0
    assert call("keyring_can_feed_autologin", str(no_module)).returncode != 0
    assert call("keyring_can_feed_autologin", str(complete)).returncode == 0


# --- PAM wiring -----------------------------------------------------------

def test_configure_pam_adds_auth_and_session_lines(tmp_path: Path) -> None:
    root = target(tmp_path)
    result = call("keyring_configure_pam", str(root), "0")
    assert result.returncode == 0, result.stderr

    pam = (root / "etc" / "pam.d" / "plasmalogin").read_text()
    assert "auth optional pam_kwallet5.so" in pam
    assert (
        "session optional pam_kwallet5.so auto_start kwalletd=/usr/bin/ksecretd"
        in pam
    )
    # No loadkey line without autologin, and no service drop-in either.
    assert "pam_systemd_loadkey" not in pam
    assert not (root / "etc" / "systemd" / "system" / "plasmalogin.service.d").exists()


"""The vendor stack plasmalogin actually ships (from /usr/lib/pam.d).

It already has pam_kwallet lines, but without `kwalletd=`, so Plasma 6's
ksecretd (the Secret Service the session uses) is not the daemon being
unlocked. The library must copy the file into /etc/pam.d and normalise it.
"""
PAM_VENDOR = """#%PAM-1.0

auth        include     system-login
-auth       optional    pam_kwallet5.so

account     include     system-login

password    include     system-login

session     include     system-login
-session    optional    pam_kwallet5.so         auto_start
"""


def vendor_target(tmp_path: Path, name: str = "plasmalogin") -> Path:
    root = target(tmp_path, pam_files=(), name=f"vendor-{name}")
    (root / "usr" / "lib" / "pam.d").mkdir(parents=True, exist_ok=True)
    (root / "usr" / "lib" / "pam.d" / name).write_text(PAM_VENDOR)
    return root


def test_vendor_pam_file_is_copied_and_points_at_ksecretd(tmp_path: Path) -> None:
    root = vendor_target(tmp_path)

    result = call("keyring_configure_pam", str(root), "0")
    assert result.returncode == 0, result.stderr

    etc = root / "etc" / "pam.d" / "plasmalogin"
    assert etc.is_file(), "the vendor file must be copied into /etc/pam.d to edit it"
    text = etc.read_text()
    # auth + password + session, and no second pair of any of them.
    assert len(active_pam_lines(text, "pam_kwallet5.so")) == 3
    assert len(active_pam_stack(text, "pam_kwallet5.so", "session")) == 1
    assert "kwalletd=/usr/bin/ksecretd" in text
    assert "force_run" not in text


def test_autologin_loadkey_goes_above_the_existing_kwallet_auth_line(tmp_path: Path) -> None:
    root = vendor_target(tmp_path, "plasmalogin-autologin")

    assert call("keyring_configure_pam", str(root), "1").returncode == 0

    text = (root / "etc" / "pam.d" / "plasmalogin-autologin").read_text()
    assert text.index("pam_systemd_loadkey") < text.index("auth       optional    pam_kwallet5.so")
    assert "kwalletd=/usr/bin/ksecretd" in text
    assert (root / "etc" / "systemd" / "system" / "plasmalogin.service.d" / "keyringmode.conf").is_file()


def test_configure_pam_is_idempotent_on_a_vendor_file(tmp_path: Path) -> None:
    root = vendor_target(tmp_path, "plasmalogin-autologin")
    call("keyring_configure_pam", str(root), "1")
    call("keyring_configure_pam", str(root), "1")

    text = (root / "etc" / "pam.d" / "plasmalogin-autologin").read_text()
    assert text.count("pam_systemd_loadkey") == 1
    assert text.count("kwalletd=/usr/bin/ksecretd") == 1


def test_configure_pam_is_idempotent(tmp_path: Path) -> None:
    root = target(tmp_path)
    call("keyring_configure_pam", str(root), "0")
    call("keyring_configure_pam", str(root), "0")
    pam = (root / "etc" / "pam.d" / "plasmalogin").read_text()
    assert pam.count("auth optional pam_kwallet5.so") == 1
    assert pam.count("auto_start") == 1


def test_autologin_stack_reads_the_luks_key_before_kwallet(tmp_path: Path) -> None:
    root = target(tmp_path, pam_files=("plasmalogin", "plasmalogin-autologin"))
    result = call("keyring_configure_pam", str(root), "1")
    assert result.returncode == 0, result.stderr

    pam = (root / "etc" / "pam.d" / "plasmalogin-autologin").read_text()
    loadkey = pam.index("-auth optional pam_systemd_loadkey.so")
    kwallet = pam.index("auth optional pam_kwallet5.so")
    assert loadkey < kwallet, "pam_systemd_loadkey must run before pam_kwallet"

    dropin = root / "etc" / "systemd" / "system" / "plasmalogin.service.d" / "keyringmode.conf"
    assert "KeyringMode=inherit" in dropin.read_text()


def test_tty_login_gets_force_run(tmp_path: Path) -> None:
    # pam_kwallet only starts from autostart in a graphical session; tty logins
    # need force_run or the session line does nothing.
    root = target(tmp_path, pam_files=("login",))
    call("keyring_configure_pam", str(root), "0")
    pam = (root / "etc" / "pam.d" / "login").read_text()
    assert "force_run" in pam


def test_force_run_is_a_separate_option_on_an_existing_session_line(tmp_path: Path) -> None:
    # Regression: the normalisation sed glued force_run onto auto_start
    # ("auto_startforce_run"), an option pam_kwallet5.so does not know, so the
    # wallet daemon was never force-started and the user got a password prompt.
    pam = tmp_path / "login"
    pam.write_text("session optional pam_kwallet5.so auto_start\n")

    result = call("keyring_pam_ensure", str(pam), "pam_kwallet5.so", "/usr/bin/ksecretd", "0", "1")
    assert result.returncode == 0, result.stderr

    session = active_pam_stack(pam.read_text(), "pam_kwallet5.so", "session")
    assert len(session) == 1
    assert session[0].split() == [
        "session", "optional", "pam_kwallet5.so",
        "auto_start", "force_run", "kwalletd=/usr/bin/ksecretd",
    ]
    assert "auto_start force_run kwalletd=/usr/bin/ksecretd" in session[0]


def test_sddm_is_wired_when_that_is_the_login_manager(tmp_path: Path) -> None:
    root = target(tmp_path, pam_files=("sddm",))
    assert call("keyring_configure_pam", str(root), "0").returncode == 0
    assert "pam_kwallet5.so" in (root / "etc" / "pam.d" / "sddm").read_text()


def test_missing_module_is_reported_and_touches_nothing(tmp_path: Path) -> None:
    root = target(tmp_path, module=False)
    result = call("keyring_configure_pam", str(root), "0")
    assert result.returncode == 1
    assert "pam_kwallet5.so is not in the target" in result.stderr
    assert (root / "etc" / "pam.d" / "plasmalogin").read_text() == PAM_STOCK


def test_no_display_manager_pam_file_is_reported(tmp_path: Path) -> None:
    root = target(tmp_path, pam_files=())
    result = call("keyring_configure_pam", str(root), "0")
    assert result.returncode == 1
    assert "no display-manager PAM file" in result.stderr


# --- user config ----------------------------------------------------------

def test_secret_service_bridge_is_enabled(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    assert call("keyring_write_user_config", str(home)).returncode == 0
    rc = (home / ".config" / "kwalletrc").read_text()
    assert "[org.freedesktop.secrets]" in rc
    assert "apiEnabled=true" in rc


def test_existing_kwalletrc_is_extended_not_replaced(tmp_path: Path) -> None:
    home = tmp_path / "home"
    (home / ".config").mkdir(parents=True)
    rc = home / ".config" / "kwalletrc"
    rc.write_text("[Wallet]\nEnabled=true\n")
    call("keyring_write_user_config", str(home))
    text = rc.read_text()
    assert "Enabled=true" in text
    assert "Default Wallet=kdewallet" in text
    assert "apiEnabled=true" in text


def test_existing_disabled_kwalletrc_is_forced_enabled(tmp_path: Path) -> None:
    home = tmp_path / "home"
    (home / ".config").mkdir(parents=True)
    rc = home / ".config" / "kwalletrc"
    rc.write_text("[Wallet]\nEnabled=false\nFirst Use=true\n")
    assert call("keyring_write_user_config", str(home)).returncode == 0
    text = rc.read_text()
    assert "Enabled=true" in text
    assert "Enabled=false" not in text
    assert "Default Wallet=kdewallet" in text
    # First Use= remains add-if-missing, so a pre-existing value is preserved.
    assert "First Use=true" in text


def test_existing_default_wallet_is_forced_to_kdewallet(tmp_path: Path) -> None:
    home = tmp_path / "home"
    (home / ".config").mkdir(parents=True)
    rc = home / ".config" / "kwalletrc"
    rc.write_text("[Wallet]\nEnabled=false\nDefault Wallet=customwallet\n")
    assert call("keyring_write_user_config", str(home)).returncode == 0
    text = rc.read_text()
    assert "Enabled=true" in text
    assert "Default Wallet=kdewallet" in text
    assert "customwallet" not in text


# --- offline / package bootstrap ------------------------------------------

def test_offline_missing_packages_warn_instead_of_stalling(tmp_path: Path) -> None:
    root = target(tmp_path, module=False)
    (root / "usr" / "bin" / "socat").unlink()
    result = call("keyring_install_packages", str(root), "false")
    assert result.returncode == 1
    assert "offline" in result.stderr
    assert "kwallet-pam" in result.stderr


def test_configure_target_writes_pam_and_user_config(tmp_path: Path) -> None:
    root = target(tmp_path)
    result = call("keyring_configure_target", str(root), "producer", "false", "0")
    assert result.returncode == 0, result.stderr
    assert "pam_kwallet5.so" in (root / "etc" / "pam.d" / "plasmalogin").read_text()
    assert "apiEnabled=true" in (root / "home" / "producer" / ".config" / "kwalletrc").read_text()
    assert "apiEnabled=true" in (root / "etc" / "skel" / ".config" / "kwalletrc").read_text()


# --- runner + build wiring ------------------------------------------------

def test_runner_configures_the_keyring_before_branding() -> None:
    src = RUNNER.read_text()
    assert 'source "$INSTALLER_LIB/keyring.sh"' in src
    keyring_call = src.index('keyring_configure_target "$TARGET" "$USERNAME" "$ONLINE" 0')
    assert keyring_call < src.index('set_phase "Applying Syntropia branding')


def test_runner_never_writes_autologin_or_references_autologin_user() -> None:
    src = RUNNER.read_text()
    assert "[Autologin]" not in src
    assert "AUTOLOGIN_USER" not in src
    assert "KEYRING_AUTOLOGIN" not in src
    assert "SDDM_AUTOLOGIN_BLOCK" not in src
    assert 'keyring_configure_target "$TARGET" "$USERNAME" "$ONLINE" 0' in src


def login_block() -> str:
    """The runner's real login-manager config block (SDDM)."""
    src = RUNNER.read_text()
    start = src.index('mkdir -p "$TARGET/etc/sddm.conf.d"')
    end_marker = 'Session=/usr/share/wayland-sessions/$SESSION_NAME\nEOF'
    end = src.index(end_marker, start) + len(end_marker)
    return src[start:end]


def run_login_block(target: Path, username: str = "producer") -> subprocess.CompletedProcess:
    script = (
        "set -e\n"
        f'TARGET="{target}"\n'
        'SESSION_NAME="hyprland-uwsm.desktop"\n'
        f'USERNAME="{username}"\n' + login_block()
    )
    return subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, env=BASE_ENV, timeout=60
    )


def test_login_config_without_autologin_keeps_the_login_screen(tmp_path: Path) -> None:
    (tmp_path / "etc" / "sddm.conf.d").mkdir(parents=True)
    # Even if the live image left an [Autologin] block behind, the runner wipes it.
    (tmp_path / "etc" / "sddm.conf").write_text("[Autologin]\nUser=liveuser\n")
    (tmp_path / "etc" / "sddm.conf.d" / "autologin.conf").write_text("[Autologin]\nUser=liveuser\n")
    result = run_login_block(tmp_path, "producer")
    assert result.returncode == 0, result.stderr

    assert (tmp_path / "etc" / "sddm.conf").read_text() == ""
    assert (tmp_path / "etc" / "sddm.conf.d" / "autologin.conf").read_text() == ""
    assert not (tmp_path / "etc" / "plasmalogin.conf").exists()


def test_login_config_preselects_hyprland_uwsm_without_autologin(tmp_path: Path) -> None:
    (tmp_path / "etc").mkdir()
    result = run_login_block(tmp_path, "producer")
    assert result.returncode == 0, result.stderr

    syntropia_conf = (tmp_path / "etc" / "sddm.conf.d" / "10-syntropia.conf").read_text()
    assert "[Autologin]" not in syntropia_conf
    assert "[Users]" in syntropia_conf
    assert "DefaultSession=hyprland-uwsm.desktop" in syntropia_conf

    state_conf = (tmp_path / "var" / "lib" / "sddm" / "state.conf").read_text()
    assert "[Last]" in state_conf
    assert "User=producer" in state_conf
    assert "Session=/usr/share/wayland-sessions/hyprland-uwsm.desktop" in state_conf


"""The PAM stack Arch's sddm package actually ships (/etc/pam.d/sddm).

This is what the 2026-10-25 laptop had: kwallet lines from upstream, plus
pam_gnome_keyring lines that plasmalogin's stack never had — and a password
stack with no wallet hook at all.
"""
PAM_SDDM_STOCK = """#%PAM-1.0

auth        include     system-login
-auth       optional    pam_gnome_keyring.so
-auth       optional    pam_kwallet5.so

account     include     system-login

password    include     system-login
-password   optional    pam_gnome_keyring.so    use_authtok

session     optional    pam_keyinit.so          force revoke
session     include     system-login
-session    optional    pam_gnome_keyring.so    auto_start
-session    optional    pam_kwallet5.so         auto_start
"""

PAM_SDDM_AUTOLOGIN_STOCK = """#%PAM-1.0
auth        required    pam_env.so
auth        required    pam_faillock.so preauth
auth        required    pam_shells.so
auth        required    pam_nologin.so
auth        required    pam_permit.so
-auth       optional    pam_gnome_keyring.so
-auth       optional    pam_kwallet5.so
account     include     system-local-login
password    include     system-local-login
session     include     system-local-login
-session    optional    pam_gnome_keyring.so auto_start
-session    optional    pam_kwallet5.so auto_start
"""

GNOME_SECRETS_SERVICE = """[D-BUS Service]
Name=org.freedesktop.secrets
Exec=/usr/bin/gnome-keyring-daemon --start --foreground --components=secrets
"""


def active_pam_lines(text: str, module: str) -> list:
    """Lines that actually load `module` (uncommented)."""
    return [
        line for line in text.splitlines()
        if module in line and not line.lstrip().startswith("#")
    ]


def active_pam_stack(text: str, module: str, stack: str) -> list:
    """Uncommented lines that load `module` in the given PAM stack."""
    found = []
    for line in active_pam_lines(text, module):
        fields = line.split()
        if fields and fields[0].lstrip("-") == stack:
            found.append(line)
    return found


def sddm_target(tmp_path: Path, *, autologin: bool = True, name: str = "sddm") -> Path:
    root = target(tmp_path, pam_files=(), name=name)
    (root / "etc" / "pam.d" / "sddm").write_text(PAM_SDDM_STOCK)
    if autologin:
        (root / "etc" / "pam.d" / "sddm-autologin").write_text(PAM_SDDM_AUTOLOGIN_STOCK)
    return root


def with_gnome_secrets(root: Path) -> Path:
    services = root / "usr" / "share" / "dbus-1" / "services"
    services.mkdir(parents=True, exist_ok=True)
    for name in ("org.freedesktop.secrets.service", "org.freedesktop.impl.portal.Secret.service"):
        (services / name).write_text(GNOME_SECRETS_SERVICE)
    return root


def test_sddm_gets_the_full_auth_password_session_stack(tmp_path: Path) -> None:
    root = sddm_target(tmp_path, autologin=False)

    assert call("keyring_configure_pam", str(root), "0").returncode == 0

    pam = (root / "etc" / "pam.d" / "sddm").read_text()
    assert active_pam_stack(pam, "pam_kwallet5.so", "auth")
    assert active_pam_stack(pam, "pam_kwallet5.so", "password"), "password changes must re-key the wallet"
    assert active_pam_stack(pam, "pam_kwallet5.so", "session")
    assert "kwalletd=/usr/bin/ksecretd" in pam


def test_gnome_keyring_cannot_compete_in_the_sddm_stack(tmp_path: Path) -> None:
    root = sddm_target(tmp_path)

    assert call("keyring_configure_pam", str(root), "1").returncode == 0

    for name in ("sddm", "sddm-autologin"):
        pam = (root / "etc" / "pam.d" / name).read_text()
        assert active_pam_lines(pam, "pam_gnome_keyring.so") == [], name
        # The original lines stay visible, commented, with the reason.
        assert "# -auth" in pam and "KWallet is the wallet" in pam, name


def test_sddm_autologin_feeds_the_wallet_the_luks_key(tmp_path: Path) -> None:
    root = sddm_target(tmp_path)

    assert call("keyring_configure_pam", str(root), "1").returncode == 0

    pam = (root / "etc" / "pam.d" / "sddm-autologin").read_text()
    loadkey = pam.index("-auth optional pam_systemd_loadkey.so")
    kwallet = pam.index("-auth       optional    pam_kwallet5.so")
    assert loadkey < kwallet, "pam_systemd_loadkey must run before pam_kwallet"
    assert "kwalletd=/usr/bin/ksecretd" in pam
    assert (root / "etc" / "systemd" / "system" / "sddm.service.d" / "keyringmode.conf").is_file()


def test_sddm_wiring_is_idempotent(tmp_path: Path) -> None:
    root = sddm_target(tmp_path)
    call("keyring_configure_pam", str(root), "1")
    call("keyring_configure_pam", str(root), "1")

    pam = (root / "etc" / "pam.d" / "sddm-autologin").read_text()
    assert pam.count("password optional pam_kwallet5.so") == 1
    assert pam.count("pam_systemd_loadkey") == 1
    assert pam.count("kwalletd=/usr/bin/ksecretd") == 1


def test_gnome_keyring_secret_service_is_parked(tmp_path: Path) -> None:
    root = with_gnome_secrets(sddm_target(tmp_path))

    assert call("keyring_configure_target", str(root), "producer", "false", "1").returncode == 0

    services = root / "usr" / "share" / "dbus-1" / "services"
    # gnome-keyring must not be D-Bus-activated as the Secret Service; the
    # ksecretd that PAM just unlocked is the wallet apps should reach.
    assert not (services / "org.freedesktop.secrets.service").exists()
    assert (services / "org.freedesktop.secrets.service.syntropia-disabled").is_file()


def test_gnome_keyring_is_left_alone_without_a_wallet_daemon(tmp_path: Path) -> None:
    root = with_gnome_secrets(sddm_target(tmp_path))
    (root / "usr" / "bin" / "ksecretd").unlink()

    call("keyring_configure_target", str(root), "producer", "false", "0")

    assert (root / "usr" / "share" / "dbus-1" / "services" / "org.freedesktop.secrets.service").is_file()


def test_missing_wallet_daemon_is_reported(tmp_path: Path) -> None:
    root = sddm_target(tmp_path)
    (root / "usr" / "bin" / "ksecretd").unlink()

    result = call("keyring_configure_pam", str(root), "0")

    assert result.returncode == 1
    assert "no KWallet daemon" in result.stderr


def test_autologin_needs_a_wallet_daemon(tmp_path: Path) -> None:
    root = sddm_target(tmp_path)
    (root / "usr" / "bin" / "ksecretd").unlink()

    assert call("keyring_can_feed_autologin", str(root)).returncode != 0


def test_runner_configures_keyring_for_password_login_without_autologin_fallback() -> None:
    src = RUNNER.read_text()
    # With autologin removed, the SDDM greeter is always the PAM path: the
    # runner empties sddm.conf and autologin.conf up front and configures
    # keyring_configure_target with autologin=0.
    assert src.index(': > "$TARGET/etc/sddm.conf"') < src.index(
        'keyring_configure_target "$TARGET" "$USERNAME" "$ONLINE" 0'
    )
    assert "Autologin disabled" not in src


def test_build_ships_the_keyring_packages() -> None:
    build = BUILD.read_text()
    # The daemon (kwallet) is a separate package that Plasma used to pull in;
    # with Plasma out of the list it has to be named explicitly.
    assert "for pkg in kwallet-pam kwallet socat; do" in build
    # And says so when the built image lacks them (a silent failure otherwise).
    assert "pam_kwallet5.so, the kwallet daemon or socat is missing from the live image" in build
    # Phase 2 cannot install packages, so a stale stock image is called out
    # before it is remastered rather than producing a prompting install.
    assert "Stock image lacks kwallet-pam/kwallet/socat" in build


def test_kwallet_unlock_helper_and_service_are_valid_and_shipped_everywhere() -> None:
    assert UNLOCK_HELPER.is_file()
    syntax = subprocess.run(
        ["bash", "-n", str(UNLOCK_HELPER)],
        capture_output=True,
        text=True,
        env=BASE_ENV,
        timeout=30,
    )
    assert syntax.returncode == 0, syntax.stderr

    assert UNLOCK_SERVICE.is_file()
    unit_text = UNLOCK_SERVICE.read_text()
    assert "ExecStart=/usr/local/bin/syntropia-kwallet-unlock" in unit_text
    assert "After=graphical-session.target" in unit_text
    assert "PartOf=graphical-session.target" in unit_text
    assert "ConditionPathExists=%t/kwallet5.socket" in unit_text

    build = BUILD.read_text()
    runner = RUNNER.read_text()
    hook = BRANDING_HOOK.read_text()

    # 1) build.sh rootfs installs
    assert "rootfs/usr/local/bin/syntropia-kwallet-unlock" in build
    assert "rootfs/etc/systemd/user/syntropia-kwallet-unlock.service" in build
    assert (
        "rootfs/etc/systemd/user/graphical-session.target.wants/syntropia-kwallet-unlock.service"
        in build
    )

    # 2) syntropia-install-runner target installs
    assert "$TARGET/usr/local/bin/syntropia-kwallet-unlock" in runner
    assert "$TARGET/etc/systemd/user/syntropia-kwallet-unlock.service" in runner
    assert (
        "$TARGET/etc/systemd/user/graphical-session.target.wants/syntropia-kwallet-unlock.service"
        in runner
    )

    # 3) hook-branding-users.sh fallback installs
    assert "$ROOT/usr/local/bin/syntropia-kwallet-unlock" in hook
    assert "$ROOT/etc/systemd/user/syntropia-kwallet-unlock.service" in hook
    assert (
        "$ROOT/etc/systemd/user/graphical-session.target.wants/syntropia-kwallet-unlock.service"
        in hook
    )


def test_kwallet_unlock_helper_gives_ksecretd_a_qt_platform_and_any_wallet_counts() -> None:
    """Two hardware findings that the helper must keep (2026-10-29).

    ksecretd is a Qt app: with no WAYLAND_DISPLAY/DISPLAY in the environment that
    pam_kwallet_init forwards, it dies with "no Qt platform plugin could be
    initialized" and no wallet is ever created. And KWallet 6 names the
    PAM-unlocked collection after the first libsecret consumer ("Default
    keyring.kwl"), so pinning the success check to kdewallet.kwl reports failure
    even when secret-tool round-trips.
    """
    text = UNLOCK_HELPER.read_text()
    assert "wayland-*" in text
    assert "QT_QPA_PLATFORM" in text
    assert "offscreen" in text
    assert '*.kwl' in text
    # The success check must be a glob over the wallet dir, not a hard-coded name.
    assert 'wallet_file=' not in text


def test_kwallet_unlock_helper_exits_silently_when_no_socket(tmp_path: Path) -> None:
    env = {
        **BASE_ENV,
        "HOME": str(tmp_path / "home"),
        "XDG_RUNTIME_DIR": str(tmp_path / "run"),
    }
    (tmp_path / "home").mkdir()
    (tmp_path / "run").mkdir()
    res = subprocess.run(
        ["bash", str(UNLOCK_HELPER)],
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )
    assert res.returncode == 0
    assert res.stderr == ""


def test_kwallet_unlock_helper_stops_early_once_kdewallet_kwl_exists(tmp_path: Path) -> None:
    home = tmp_path / "home"
    run_dir = tmp_path / "run"
    bin_dir = tmp_path / "bin"
    home.mkdir()
    run_dir.mkdir()
    bin_dir.mkdir()

    sock = run_dir / "kwallet5.socket"
    sock.write_text("")
    sock.chmod(0o600)

    # Stub pgrep so ksecretd appears running.
    pgrep = bin_dir / "pgrep"
    pgrep.write_text("#!/bin/sh\nexit 0\n")
    pgrep.chmod(0o755)

    calls_file = tmp_path / "calls.txt"
    env_dump = tmp_path / "env.txt"
    fake_init = tmp_path / "pam_kwallet_init"
    fake_init.write_text(
        "#!/bin/sh\n"
        f'echo "call" >> "{calls_file}"\n'
        f'printf "%s|%s|%s\\n" "$WAYLAND_DISPLAY" "$DBUS_SESSION_BUS_ADDRESS" "$PAM_KWALLET5_LOGIN" > "{env_dump}"\n'
        'count=$(wc -l < "' + str(calls_file) + '")\n'
        'if [ "$count" -ge 2 ]; then\n'
        '  mkdir -p "$HOME/.local/share/kwalletd"\n'
        '  : > "$HOME/.local/share/kwalletd/kdewallet.kwl"\n'
        "fi\n"
        "exit 0\n"
    )
    fake_init.chmod(0o755)

    env = {
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "HOME": str(home),
        "XDG_RUNTIME_DIR": str(run_dir),
        "WAYLAND_DISPLAY": "wayland-1",
        "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus",
        "SYNTROPIA_PAM_KWALLET_INIT": str(fake_init),
    }
    res = subprocess.run(
        ["bash", str(UNLOCK_HELPER)],
        capture_output=True,
        text=True,
        env=env,
        timeout=15,
    )
    assert res.returncode == 0
    assert (home / ".local" / "share" / "kwalletd" / "kdewallet.kwl").is_file()
    # Stopped on attempt 2 out of 5 once kdewallet.kwl appeared.
    assert len(calls_file.read_text().splitlines()) == 2
    assert env_dump.read_text().strip() == f"wayland-1|unix:path=/run/user/1000/bus|{sock}"
    assert len(res.stderr.strip().splitlines()) == 1
    assert "wallet unlocked" in res.stderr
    assert "kdewallet.kwl" in res.stderr
