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
RUNNER = REPO / "iso" / "installer" / "syntropia-install-runner"
BUILD = REPO / "iso" / "build.sh"

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
    assert "apiEnabled=true" in text


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
    keyring_call = src.index('keyring_configure_target "$TARGET" "$USERNAME"')
    assert keyring_call < src.index('set_phase "Applying Syntropia branding')


def test_runner_keeps_autologin_only_when_the_keyring_can_be_fed() -> None:
    src = RUNNER.read_text()
    assert 'if [[ "$ENCRYPT_DISK" == "true" ]] && keyring_can_feed_autologin "$TARGET"; then' in src
    # The login-manager files must not hard-code the user any more.
    assert "User=$USERNAME\nSession=$SESSION_NAME" not in src
    assert "User=$AUTOLOGIN_USER" in src


def login_block() -> str:
    """The runner's real login-manager config block (SDDM)."""
    src = RUNNER.read_text()
    start = src.index('SDDM_AUTOLOGIN_BLOCK=""')
    end_marker = (
        'printf \'%s\' "$SDDM_AUTOLOGIN_BLOCK" '
        '> "$TARGET/etc/sddm.conf.d/autologin.conf"'
    )
    end = src.index(end_marker) + len(end_marker)
    return src[start:end]


def run_login_block(target: Path, autologin_user: str) -> subprocess.CompletedProcess:
    script = (
        "set -e\n"
        f'TARGET="{target}"\n'
        'SESSION_NAME="hyprland-uwsm.desktop"\n'
        f'AUTOLOGIN_USER="{autologin_user}"\n' + login_block()
    )
    return subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, env=BASE_ENV, timeout=60
    )


def test_login_config_without_autologin_keeps_the_login_screen(tmp_path: Path) -> None:
    (tmp_path / "etc").mkdir()
    result = run_login_block(tmp_path, "")
    assert result.returncode == 0, result.stderr

    assert (tmp_path / "etc" / "sddm.conf").read_text() == ""
    assert (tmp_path / "etc" / "sddm.conf.d" / "autologin.conf").read_text() == ""
    # Plasma's login manager left the image with the desktop (NEXT_SESSION.md
    # item 4): the runner must not keep writing a config nothing reads.
    assert not (tmp_path / "etc" / "plasmalogin.conf").exists()


def test_login_config_with_autologin_names_the_user(tmp_path: Path) -> None:
    (tmp_path / "etc").mkdir()
    result = run_login_block(tmp_path, "producer")
    assert result.returncode == 0, result.stderr

    for name in ("sddm.conf", "sddm.conf.d/autologin.conf"):
        text = (tmp_path / "etc" / name).read_text()
        assert "[Autologin]" in text, name
        assert "User=producer" in text, name
        assert "Session=hyprland-uwsm.desktop" in text, name
        assert "Relogin=false" in text, name
    assert not (tmp_path / "etc" / "plasmalogin.conf").exists()


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


def test_runner_falls_back_to_the_login_screen_when_the_keyring_fails() -> None:
    src = RUNNER.read_text()
    # Autologin + a wallet PAM cannot unlock = the prompt is back. The runner
    # must drop autologin instead of shipping it.
    assert "Autologin disabled: without a PAM path to the wallet" in src
    failure = src.index('echo "warning: keyring auto-unlock incomplete')
    assert failure < src.index(': > "$TARGET/etc/sddm.conf"')


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
