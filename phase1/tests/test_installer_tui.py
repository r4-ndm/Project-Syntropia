"""Tests for the live installer's setup TUI (iso/installer/).

The installer is bash (documented deviation: it runs on the live ISO before
anything else exists), so the tests drive the real scripts with a stubbed PATH
and assert on what the operator sees plus what the config contains. The
--dry-run mode exists for this: same questions, no disk, no /run writes.
"""

import json
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
INSTALLER_DIR = REPO / "iso" / "installer"
LIB_DIR = INSTALLER_DIR / "lib"

# A single installable disk, so the TUI never inspects the host's real devices.
STUBS = {
    "lsblk": 'echo "/dev/vda 40G QEMU HARDDISK"\n',
    # Offline: no default route and no reachable probe address.
    "ip": "exit 0\n",
    "ping": "exit 1\n",
    "getent": "exit 1\n",
    "clear": "exit 0\n",
    "setleds": "exit 0\n",
    "loadkeys": "exit 0\n",
    "localectl": 'echo "   VC Keymap: us"\n',
}


def make_stub_bin(tmp_path: Path) -> Path:
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir(exist_ok=True)
    for name, body in STUBS.items():
        path = stub_dir / name
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)
    return stub_dir


def installer_env(tmp_path: Path) -> dict:
    return {
        "PATH": f"{make_stub_bin(tmp_path)}:/usr/local/bin:/usr/bin:/bin",
        "HOME": str(tmp_path / "home"),
        "TERM": "xterm-256color",
        "LANG": "C.UTF-8",
        "LINES": "48",
        "COLUMNS": "120",
        # Keep the dry run's config out of /run.
        "SYNTROPIA_INSTALL_CONFIG": str(tmp_path / "run" / "config.json"),
    }


def run_tui(tmp_path: Path, answers: str, *args: str) -> subprocess.CompletedProcess:
    env = installer_env(tmp_path)
    return subprocess.run(
        [str(INSTALLER_DIR / "syntropia-install"), *args],
        input=answers,
        text=True,
        capture_output=True,
        env=env,
        timeout=120,
        cwd=str(tmp_path),
    )


# --- strength estimate ----------------------------------------------------


def strength(password: str) -> int:
    result = subprocess.run(
        ["bash", "-c", f'source "{LIB_DIR}/password.sh"; password_strength_score "$1"', "_", password],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    return int(result.stdout.strip())


@pytest.mark.parametrize(
    "password,expected",
    [
        ("password", 0),  # deny-listed
        ("aaaaaaaa", 0),  # one repeated character
        ("short", 0),  # too short to score anything
        ("short1!", 1),  # mixed classes, still below the minimum
        ("abcdefghij", 1),  # long enough, one character class

        ("Tr0ub4dor&3", 3),
        ("correct horse battery staple", 4),
    ],
)
def test_password_strength_score(password: str, expected: int) -> None:
    assert strength(password) == expected


def test_strength_is_monotonic_in_length() -> None:
    assert strength("aaaaaaaaaaa1") < strength("aaaaaaaaaaaaaaaaaaaa1")


# --- config contract ------------------------------------------------------


def write_config(tmp_path: Path, **values: str) -> Path:
    path = tmp_path / "config.json"
    env = {
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        **{f"INSTALL_{k.upper()}": v for k, v in values.items()},
    }
    subprocess.run(
        ["bash", "-c", f'source "{LIB_DIR}/config.sh"; config_write "$1"', "_", str(path)],
        env=env,
        check=True,
        timeout=30,
    )
    return path


def test_config_records_both_passwords_owner_only(tmp_path: Path) -> None:
    path = write_config(
        tmp_path,
        disk="/dev/vda",
        username="producer",
        hostname="studio",
        password="account-secret",
        root_password="root-secret",
        desktop="hyprland",
        encrypt="true",
        keymap="uk",
        online="false",
    )
    data = json.loads(path.read_text())
    assert data["password"] == "account-secret"
    assert data["root_password"] == "root-secret"
    assert data["online"] is False
    assert data["encrypt"] is True
    # The file holds every credential in the install: nobody else may read it.
    assert path.stat().st_mode & 0o777 == 0o600


def test_config_get_falls_back_when_root_password_absent(tmp_path: Path) -> None:
    path = tmp_path / "old.json"
    path.write_text(json.dumps({"disk": "/dev/vda", "password": "only-account"}))
    result = subprocess.run(
        [
            "bash",
            "-c",
            f'source "{LIB_DIR}/config.sh"; config_get "$1" root_password "$2"',
            "_",
            str(path),
            "only-account",
        ],
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin"},
        timeout=30,
    )
    assert result.stdout == "only-account"


def test_runner_sets_root_and_account_passwords_separately() -> None:
    runner = (INSTALLER_DIR / "syntropia-install-runner").read_text()
    assert '"$USERNAME" "$USER_PASSWORD" | arch-chroot "$TARGET" chpasswd' in runner
    assert '"root" "$ROOT_PASSWORD" | arch-chroot "$TARGET" chpasswd' in runner
    # Passwords must not be handed to cryptsetup via argv either.
    assert 'echo -n "$PASSWORD"' not in runner


# --- dry run --------------------------------------------------------------


def test_dry_run_asks_for_both_passwords_and_changes_nothing(tmp_path: Path) -> None:
    answers = "\n".join(
        [
            "1",  # install
            "1",  # disk
            "",  # username (default)
            "",  # hostname (default)
            "",  # keymap (default)
            "3",  # network: continue offline
            "correct horse battery staple",  # account password
            "correct horse battery staple",  # confirmation
            "1",  # root: same as user
            "",  # encryption (default: on)
            "",  # desktop (default: plasma)
            "y",  # proceed
        ]
    )
    result = run_tui(tmp_path, answers + "\n", "--dry-run")

    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "Account password" in out
    assert "Strength" in out and "very strong" in out
    assert "Root (administrator) password" in out
    assert 'Same password as "syntropia"' in out
    assert "no internet connection detected" in out
    assert "dry run" in out
    # Dry run must not leave the credentials on disk.
    assert not Path(installer_env(tmp_path)["SYNTROPIA_INSTALL_CONFIG"]).exists()


def test_dry_run_separate_root_password(tmp_path: Path) -> None:
    answers = "\n".join(
        [
            "1",
            "1",
            "producer",
            "studio",
            "",
            "3",
            "account passphrase 1",
            "account passphrase 1",  # confirmation
            "2",  # separate root password
            "root passphrase 2",  # root password
            "root passphrase 2",  # root confirmation
            "2",  # encryption off
            "2",  # hyprland
            "y",
        ]
    )
    result = run_tui(tmp_path, answers + "\n", "--dry-run")

    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert out.count("New password") == 2
    assert "separate from producer" in out
    assert "Encryption" in out and "off" in out


def test_rejects_short_password_and_bad_disk_choice(tmp_path: Path) -> None:
    answers = "\n".join(
        [
            "1",
            "7",  # invalid disk index — must re-ask
            "1",
            "",
            "",
            "",
            "3",
            "short",  # rejected: below the minimum
            "abcdefghij",  # scores "weak" — kept only on explicit [k]
            "k",
            "abcdefghij",  # confirmation
            "1",  # root: same
            "",  # encryption
            "",  # desktop
            "y",
        ]
    )
    result = run_tui(tmp_path, answers + "\n", "--dry-run")

    assert result.returncode == 0, result.stderr
    assert "not one of the listed drives" in result.stdout
    assert "too short" in result.stdout
    assert "Weak." in result.stdout


def test_help_lists_dry_run() -> None:
    result = subprocess.run(
        [str(INSTALLER_DIR / "syntropia-install"), "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0
    assert "--dry-run" in result.stdout


# --- packaging contract ---------------------------------------------------


def test_installer_scripts_are_syntactically_valid() -> None:
    scripts = [
        INSTALLER_DIR / "syntropia-install",
        INSTALLER_DIR / "syntropia-install-runner",
        INSTALLER_DIR / "syntropia-install-dashboard",
        *sorted(LIB_DIR.glob("*.sh")),
    ]
    assert len(scripts) >= 7
    for script in scripts:
        subprocess.run(["bash", "-n", str(script)], check=True, timeout=30)


def test_build_sh_ships_the_installer_instead_of_embedding_it() -> None:
    build = (REPO / "iso" / "build.sh").read_text()
    # No heredocs may creep back in: the UI is reviewed and tested as files.
    for name in ("syntropia-install", "syntropia-install-runner", "syntropia-install-dashboard"):
        assert f'cat > "rootfs/usr/local/bin/{name}"' not in build
    assert 'for script in syntropia-install syntropia-install-runner syntropia-install-dashboard; do' in build
    assert '"$installer_src"/lib/*.sh' in build


def test_runner_reads_only_keys_the_tui_writes() -> None:
    import re

    written = set(
        re.findall(r'"([a-z_]+)":', (LIB_DIR / "config.sh").read_text())
    )
    runner = (INSTALLER_DIR / "syntropia-install-runner").read_text()
    read = set(re.findall(r'config_get "\$CONFIG_FILE" ([a-z_]+)', runner))
    assert read, "runner should read its config through config_get"
    assert read <= written, f"runner reads keys the TUI never writes: {read - written}"
