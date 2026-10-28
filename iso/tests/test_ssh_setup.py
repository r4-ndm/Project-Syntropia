"""Tests for the Syntropia SSH setup helper (iso/installer/lib/ssh-setup.sh).

Pins the helper script syntax, its installation into both the live image and
the installed target (/usr/local/bin/syntropia-ssh-setup via build.sh,
syntropia-install-runner, and hook-branding-users.sh), the verify_installer_libs
stale-file guard in build.sh, the wizard catalog entry in phase1/wizard/apps.list,
and its runtime behavior (SUDO_USER home resolution + chown, passphrase override
and warning, sshd hardening drop-in + sshd -t validation, TTY sudo re-exec, and
non-interactive wizard execution).
"""

import os
import pty
import select
import subprocess
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SSH_SETUP = REPO / "iso" / "installer" / "lib" / "ssh-setup.sh"
BUILD = REPO / "iso" / "build.sh"
RUNNER = REPO / "iso" / "installer" / "syntropia-install-runner"
HOOK = REPO / "iso" / "hook-scripts" / "hook-branding-users.sh"
APPS_LIST = REPO / "phase1" / "wizard" / "apps.list"
# The wizard that actually ships is the vendored app-wiz4rd release tarball, NOT
# phase1/wizard/ (that copy is deprecated and not consumed by the build). Test
# the tarball's script so the coverage tracks what lands in the ISO.
WIZARD_TARBALL = REPO / "iso" / "vendor" / "app-wiz4rd-0.1.0.tar"

BASE_ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}

IP_SAMPLE = """1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000
    inet 127.0.0.1/8 scope host lo
       valid_lft forever preferred_lft forever
2: wlan0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue state UP group default qlen 1000
    inet 192.168.1.42/24 brd 192.168.1.255 scope global dynamic noprefixroute wlan0
       valid_lft 86390sec preferred_lft 86390sec
3: docker0: <NO-CARRIER,BROADCAST,MULTICAST,UP> mtu 1500 qdisc noqueue state DOWN group default
    inet 172.17.0.1/16 brd 172.17.255.255 scope global docker0
       valid_lft forever preferred_lft forever
4: veth9a8b7c@if3: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue master docker0 state UP
    inet 172.18.0.2/16 scope global veth9a8b7c
       valid_lft forever preferred_lft forever
"""


def make_stubs(
    tmp_path: Path,
    *,
    openssh_installed: bool = False,
    sshd_check_rc: int = 0,
) -> tuple[Path, Path]:
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    log = tmp_path / "calls.log"

    pacman_rc = 0 if openssh_installed else 1
    (bindir / "pacman").write_text(
        "#!/bin/sh\n"
        'echo "pacman $*" >> "$SSH_TEST_LOG"\n'
        'if [ "$1" = "-Q" ]; then\n'
        f"    exit {pacman_rc}\n"
        "fi\n"
        "exit 0\n"
    )
    (bindir / "systemctl").write_text(
        "#!/bin/sh\n"
        'echo "systemctl $*" >> "$SSH_TEST_LOG"\n'
        "exit 0\n"
    )
    (bindir / "ssh-keygen").write_text(
        "#!/bin/sh\n"
        'echo "ssh-keygen $*" >> "$SSH_TEST_LOG"\n'
        "while [ $# -gt 0 ]; do\n"
        '    if [ "$1" = "-f" ]; then\n'
        '        touch "$2" "$2.pub"\n'
        "        break\n"
        "    fi\n"
        "    shift\n"
        "done\n"
        "exit 0\n"
    )
    (bindir / "sshd").write_text(
        "#!/bin/sh\n"
        'echo "sshd $*" >> "$SSH_TEST_LOG"\n'
        f"exit {sshd_check_rc}\n"
    )
    (bindir / "chown").write_text(
        "#!/bin/sh\n"
        'echo "chown $*" >> "$SSH_TEST_LOG"\n'
        "exit 0\n"
    )
    (bindir / "ip").write_text(
        "#!/bin/sh\n"
        'echo "ip $*" >> "$SSH_TEST_LOG"\n'
        f"cat <<'EOF'\n{IP_SAMPLE}EOF\n"
    )
    for name in ("pacman", "systemctl", "ssh-keygen", "sshd", "chown", "ip"):
        (bindir / name).chmod(0o755)
    return bindir, log


def test_ssh_setup_script_exists_and_passes_bash_syntax_check() -> None:
    assert SSH_SETUP.is_file(), "iso/installer/lib/ssh-setup.sh must exist"
    for script in (SSH_SETUP, BUILD, RUNNER, HOOK):
        subprocess.run(["bash", "-n", str(script)], check=True, timeout=30)


def test_build_and_install_paths_ship_and_verify_syntropia_ssh_setup() -> None:
    build = BUILD.read_text()
    assert "installer/lib/ssh-setup.sh" in build
    assert "rootfs/usr/local/bin/syntropia-ssh-setup" in build
    assert '"$installer_src"/lib/*.sh' in build

    # Defect 5: verify_installer_libs() must also extract and byte-compare
    # usr/local/bin/syntropia-ssh-setup against iso/installer/lib/ssh-setup.sh.
    verify_block = build.split("verify_installer_libs()", 1)[1].split("\n}", 1)[0]
    assert 'paths+=("usr/local/bin/syntropia-ssh-setup")' in verify_block
    assert 'cmp -s "$SCRIPT_DIR/installer/lib/ssh-setup.sh" "$extract_dir/rootfs/$rel"' in verify_block

    runner = RUNNER.read_text()
    assert "$INSTALLER_LIB/ssh-setup.sh" in runner
    assert "$TARGET/usr/local/bin/syntropia-ssh-setup" in runner

    hook = HOOK.read_text()
    assert "$syntropia_installer_lib/ssh-setup.sh" in hook
    assert "$ROOT/usr/local/bin/syntropia-ssh-setup" in hook


def test_apps_list_contains_ssh_setup_entry() -> None:
    entries = [
        line.strip()
        for line in APPS_LIST.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert "Remote|SSH Setup|syntropia-ssh-setup|One-command SSH server setup" in entries
    # The shipped wizard (vendored tarball) must know between package and
    # local helper, otherwise it hands the entry to paru.
    assert b"HELPER_BIN_DIR" in subprocess.run(
        ["tar", "-xOf", str(WIZARD_TARBALL), "app-wiz4rd-0.1.0/app-wiz4rd"],
        check=True, capture_output=True, timeout=30,
    ).stdout


def test_non_root_prints_instructions_generates_key_warns_no_passphrase_and_filters_lan_ips(
    tmp_path: Path,
) -> None:
    bindir, log = make_stubs(tmp_path, openssh_installed=False)
    home = tmp_path / "home"
    home.mkdir()
    env = {
        **BASE_ENV,
        "PATH": f"{bindir}:{BASE_ENV['PATH']}",
        "HOME": str(home),
        "USER": "producer",
        "SYNTROPIA_EUID": "1000",
        "SSH_TEST_LOG": str(log),
    }

    result = subprocess.run(
        ["bash", str(SSH_SETUP)],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "sudo pacman -S --needed openssh" in out
    assert "sudo systemctl enable --now sshd" in out
    assert (home / ".ssh" / "id_ed25519").is_file()
    assert (
        "key created WITHOUT a passphrase — anyone who reads ~/.ssh/id_ed25519 owns every host you copy it to"
        in out
    )
    assert "192.168.1.42" in out
    assert "127.0.0.1" not in out
    assert "172.17.0.1" not in out
    assert "172.18.0.2" not in out
    assert "ssh-copy-id producer@192.168.1.42" in out

    calls = log.read_text()
    assert "pacman -S" not in calls
    assert "systemctl enable" not in calls
    assert f"ssh-keygen -t ed25519 -f {home}/.ssh/id_ed25519 -N  -q" in calls
    assert "ip -4 addr" in calls


def test_passphrase_env_override_passes_passphrase_and_omits_warning(tmp_path: Path) -> None:
    bindir, log = make_stubs(tmp_path, openssh_installed=True)
    home = tmp_path / "home"
    home.mkdir()
    env = {
        **BASE_ENV,
        "PATH": f"{bindir}:{BASE_ENV['PATH']}",
        "HOME": str(home),
        "USER": "producer",
        "SYNTROPIA_EUID": "1000",
        "SYNTROPIA_SSH_KEY_PASSPHRASE": "correct-horse-battery-staple",
        "SSH_TEST_LOG": str(log),
    }

    result = subprocess.run(
        ["bash", str(SSH_SETUP)],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "key created WITHOUT a passphrase" not in result.stdout
    assert "correct-horse-battery-staple" in log.read_text()


def test_sudo_path_uses_sudo_user_home_not_root_and_chowns_ssh_dir(tmp_path: Path) -> None:
    bindir, log = make_stubs(tmp_path, openssh_installed=True)
    root_home = tmp_path / "root"
    root_home.mkdir()
    user_home = tmp_path / "home" / "producer"
    user_home.mkdir(parents=True)

    (bindir / "getent").write_text(
        "#!/bin/sh\n"
        'echo "getent $*" >> "$SSH_TEST_LOG"\n'
        'if [ "$1" = "passwd" ] && [ "$2" = "producer" ]; then\n'
        f'    echo "producer:x:1000:1000:Producer:{user_home}:/bin/bash"\n'
        "    exit 0\n"
        "fi\n"
        "exit 2\n"
    )
    (bindir / "getent").chmod(0o755)

    env = {
        **BASE_ENV,
        "PATH": f"{bindir}:{BASE_ENV['PATH']}",
        "HOME": str(root_home),
        "USER": "root",
        "SUDO_USER": "producer",
        "SYNTROPIA_EUID": "0",
        "SYNTROPIA_SSHD_CONFIG_D": str(tmp_path / "sshd_config.d"),
        "SSH_TEST_LOG": str(log),
    }

    result = subprocess.run(
        ["bash", str(SSH_SETUP)],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert (user_home / ".ssh" / "id_ed25519").is_file()
    assert not (root_home / ".ssh" / "id_ed25519").exists()
    assert "ssh-copy-id producer@192.168.1.42" in result.stdout
    calls = log.read_text()
    assert f"chown -R producer: {user_home}/.ssh" in calls


def test_root_installs_openssh_and_enables_sshd_and_keeps_existing_key(tmp_path: Path) -> None:
    bindir, log = make_stubs(tmp_path, openssh_installed=False)
    home = tmp_path / "home"
    ssh_dir = home / ".ssh"
    ssh_dir.mkdir(parents=True)
    key = ssh_dir / "id_ed25519"
    key.write_text("existing-private-key\n")
    dropin_dir = tmp_path / "sshd_config.d"

    env = {
        **BASE_ENV,
        "PATH": f"{bindir}:{BASE_ENV['PATH']}",
        "HOME": str(home),
        "USER": "producer",
        "SYNTROPIA_EUID": "0",
        "SYNTROPIA_SSHD_CONFIG_D": str(dropin_dir),
        "SSH_TEST_LOG": str(log),
    }

    result = subprocess.run(
        ["bash", str(SSH_SETUP)],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    calls = log.read_text()
    assert "pacman -S --noconfirm --needed openssh" in calls
    assert "systemctl enable --now sshd" in calls
    assert "ssh-keygen" not in calls
    assert key.read_text() == "existing-private-key\n"
    # No authorized_keys yet -> hardening drop-in is skipped with prominent message
    assert not (dropin_dir / "50-syntropia-ssh.conf").exists()
    assert "key-copy not done yet" in result.stdout
    assert "hardening skipped" in result.stdout
    assert "ssh-copy-id" in result.stdout


def test_sshd_hardening_dropin_written_when_authorized_keys_exists_and_skipped_without(
    tmp_path: Path,
) -> None:
    bindir, log = make_stubs(tmp_path, openssh_installed=True)
    home = tmp_path / "home"
    ssh_dir = home / ".ssh"
    ssh_dir.mkdir(parents=True)
    dropin_dir = tmp_path / "sshd_config.d"
    dropin = dropin_dir / "50-syntropia-ssh.conf"

    env = {
        **BASE_ENV,
        "PATH": f"{bindir}:{BASE_ENV['PATH']}",
        "HOME": str(home),
        "USER": "producer",
        "SYNTROPIA_EUID": "0",
        "SYNTROPIA_SSHD_CONFIG_D": str(dropin_dir),
        "SSH_TEST_LOG": str(log),
    }

    # First run without authorized_keys: skips writing the drop-in.
    res_skip = subprocess.run(
        ["bash", str(SSH_SETUP)],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert res_skip.returncode == 0, res_skip.stderr
    assert not dropin.exists()
    assert "key-copy not done yet" in res_skip.stdout
    assert "hardening skipped" in res_skip.stdout

    # Second run after ssh-copy-id populates authorized_keys: writes and validates drop-in.
    (ssh_dir / "authorized_keys").write_text("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITest producer@host\n")
    res_harden = subprocess.run(
        ["bash", str(SSH_SETUP)],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert res_harden.returncode == 0, res_harden.stderr
    assert dropin.is_file()
    assert (dropin.stat().st_mode & 0o777) == 0o644
    content = dropin.read_text().splitlines()
    assert "PasswordAuthentication no" in content
    assert "KbdInteractiveAuthentication no" in content
    assert "PermitRootLogin prohibit-password" in content
    assert "AllowUsers producer" in content

    calls = log.read_text()
    assert "sshd -t" in calls
    assert f"chown root:root {dropin}" in calls
    assert "systemctl restart sshd" in calls


def test_sshd_hardening_removes_dropin_and_reports_when_sshd_t_fails(tmp_path: Path) -> None:
    bindir, log = make_stubs(tmp_path, openssh_installed=True, sshd_check_rc=1)
    home = tmp_path / "home"
    ssh_dir = home / ".ssh"
    ssh_dir.mkdir(parents=True)
    (ssh_dir / "id_ed25519").write_text("key\n")
    (ssh_dir / "authorized_keys").write_text("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAITest producer@host\n")
    dropin_dir = tmp_path / "sshd_config.d"
    dropin = dropin_dir / "50-syntropia-ssh.conf"

    env = {
        **BASE_ENV,
        "PATH": f"{bindir}:{BASE_ENV['PATH']}",
        "HOME": str(home),
        "USER": "producer",
        "SYNTROPIA_EUID": "0",
        "SYNTROPIA_SSHD_CONFIG_D": str(dropin_dir),
        "SSH_TEST_LOG": str(log),
    }

    result = subprocess.run(
        ["bash", str(SSH_SETUP)],
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )

    assert result.returncode != 0
    assert not dropin.exists()
    assert "sshd -t" in (result.stdout + result.stderr)


def test_tty_non_root_reexecs_via_sudo_before_running(tmp_path: Path) -> None:
    bindir, log = make_stubs(tmp_path, openssh_installed=True)
    home = tmp_path / "home"
    home.mkdir()

    # Stub sudo to record the re-exec invocation and re-run the command with SYNTROPIA_EUID=0.
    (bindir / "sudo").write_text(
        "#!/bin/sh\n"
        'echo "sudo $*" >> "$SSH_TEST_LOG"\n'
        'if [ "$1" = "-E" ]; then\n'
        "    shift\n"
        "fi\n"
        'SYNTROPIA_EUID=0 SUDO_USER="${USER:-producer}" exec "$@"\n'
    )
    (bindir / "sudo").chmod(0o755)

    env = {
        **BASE_ENV,
        "PATH": f"{bindir}:{BASE_ENV['PATH']}",
        "HOME": str(home),
        "USER": "producer",
        "SYNTROPIA_EUID": "1000",
        "SYNTROPIA_SSHD_CONFIG_D": str(tmp_path / "sshd_config.d"),
        "SSH_TEST_LOG": str(log),
    }

    master, slave = pty.openpty()
    proc = subprocess.Popen(
        ["bash", str(SSH_SETUP)],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env=env,
        close_fds=True,
    )
    os.close(slave)

    chunks: list[bytes] = []
    deadline = time.time() + 15
    while time.time() < deadline:
        r, _, _ = select.select([master], [], [], 0.1)
        if r:
            try:
                data = os.read(master, 4096)
                if not data:
                    break
                chunks.append(data)
            except OSError:
                break
        elif proc.poll() is not None:
            break
    os.close(master)
    proc.wait(timeout=10)

    out = b"".join(chunks).decode("utf-8", errors="replace")
    assert proc.returncode == 0, out
    assert "sudo" in out.lower()
    calls = log.read_text()
    assert f"sudo -E {SSH_SETUP}" in calls
    assert "systemctl enable --now sshd" in calls


def test_branding_hook_installs_syntropia_ssh_setup_into_target(tmp_path: Path) -> None:
    root = tmp_path / "target"
    (root / "etc").mkdir(parents=True)
    lib_dir = tmp_path / "installer-lib"
    lib_dir.mkdir()
    (lib_dir / "ssh-setup.sh").write_text(SSH_SETUP.read_text())

    result = subprocess.run(
        ["bash", str(HOOK), str(root)],
        capture_output=True,
        text=True,
        env={**BASE_ENV, "SYNTROPIA_INSTALLER_LIB": str(lib_dir)},
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    installed = root / "usr" / "local" / "bin" / "syntropia-ssh-setup"
    assert installed.is_file()
    assert installed.stat().st_mode & 0o111 != 0


def test_shipped_wizard_runs_local_syntropia_helper_instead_of_paru(
    tmp_path: Path,
) -> None:
    """The wizard that actually ships is the vendored app-wiz4rd tarball."""
    import tarfile

    vendor = tmp_path / "vendor"
    with tarfile.open(WIZARD_TARBALL) as tf:
        tf.extractall(vendor)
    wiz_dir = vendor / "app-wiz4rd-0.1.0"
    wiz_script = wiz_dir / "app-wiz4rd"
    assert wiz_script.is_file()

    helper_bin = tmp_path / "local-bin"
    helper_bin.mkdir()
    helper_log = tmp_path / "helper.log"
    helper = helper_bin / "syntropia-ssh-setup"
    helper.write_text(f'#!/bin/sh\necho "ran-ssh-setup" >> "{helper_log}"\n')
    helper.chmod(0o755)

    paru_log = tmp_path / "paru.log"
    stub_bin = tmp_path / "stub-bin"
    stub_bin.mkdir()
    paru = stub_bin / "paru"
    paru.write_text(f'#!/bin/sh\necho "paru $*" >> "{paru_log}"\n')
    paru.chmod(0o755)
    fzf = stub_bin / "fzf"
    fzf.write_text(
        "#!/bin/sh\n"
        "awk -F'\\t' '$2 == \"syntropia-ssh-setup\" { print $0 }'\n"
    )
    fzf.chmod(0o755)

    home = tmp_path / "home"
    home.mkdir()
    env = {
        **BASE_ENV,
        "PATH": f"{stub_bin}:{BASE_ENV['PATH']}",
        "HOME": str(home),
        "SYNTROPIA_BIN_DIR": str(helper_bin),
    }

    catalog = tmp_path / "apps.list"
    catalog.write_text(APPS_LIST.read_text())

    # The shipped wizard relaunches itself inside a terminal when stdin is not
    # a tty, so drive it through a pty.
    master, slave = pty.openpty()
    proc = subprocess.Popen(
        [str(wiz_script), "--once", "--config", str(catalog)],
        stdin=slave,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        cwd=str(wiz_dir),
    )
    os.close(slave)
    # Keep the master open (closing it hangs up the pty, which makes `-t 0`
    # fail and sends the wizard down its relaunch-in-a-terminal path); feed
    # newlines for the end-of-run "Press Enter" prompt instead.
    os.write(master, b"\n\n\n\n")
    out, _ = proc.communicate(timeout=60)
    os.close(master)

    assert proc.returncode == 0, out
    assert helper_log.is_file() and "ran-ssh-setup" in helper_log.read_text()
    assert not paru_log.exists(), "local syntropia-* helper must not be passed to paru"
    assert "Running Syntropia helpers" in out
