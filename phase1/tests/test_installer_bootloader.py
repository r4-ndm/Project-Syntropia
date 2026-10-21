"""Tests for the installer's Limine bootloader step (iso/installer/lib/bootloader.sh).

The runner used to write systemd-boot entries (UEFI) and GRUB (BIOS); Limine is
the confirmed bootloader (NEXT_SESSION.md), so what we pin here is:

* the limine.conf the runner generates (paths, the LTS entry, and the OS entry
  name that the branding hook + limine-snapper-sync match against), and
* that the UEFI/BIOS install helpers copy the right payloads and invoke the
  right commands — driven with stubbed `efibootmgr` / `limine` binaries, so no
  disk is touched.

The runner itself is a destructive bash script; its structure is pinned with
static guards (no bootctl/GRUB left, a BIOS boot partition exists).
"""

import ast
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
INSTALLER_DIR = REPO / "iso" / "installer"
LIB = INSTALLER_DIR / "lib" / "bootloader.sh"
RUNNER = INSTALLER_DIR / "syntropia-install-runner"
HOOK = REPO / "iso" / "hook-scripts" / "hook-branding-users.sh"
TRANSFORM = REPO / "phase1" / "cli" / "transform" / "syntropia_transform" / "transform.py"

BASE_ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}


def call_lib(
    function: str, *args: str, tmp_path: Path, env: dict | None = None
) -> subprocess.CompletedProcess:
    """Source the real library and run one of its functions (nothing else)."""
    return subprocess.run(
        ["bash", "-c", f'source "{LIB}"; {function} "$@"', "_", *args],
        capture_output=True,
        text=True,
        env={**BASE_ENV, **(env or {})},
        cwd=str(tmp_path),
        timeout=60,
    )


# --- limine.conf generation -----------------------------------------------

def write_conf(tmp_path: Path, cmdline: str = "root=UUID=abc rootflags=subvol=@ rw",
               lts: str = "0", splash: str | None = None) -> Path:
    boot = tmp_path / "boot"
    # Always pass an explicit splash: the default points into the live ISO's
    # /usr/share/syntropia, which would make these tests host-dependent.
    splash = splash or str(tmp_path / "no-splash.png")
    result = call_lib("limine_conf_write", str(boot), cmdline, lts, splash,
                      tmp_path=tmp_path)
    assert result.returncode == 0, result.stderr
    return boot / "limine.conf"


def entry_lines(conf: Path) -> list[str]:
    return [line for line in conf.read_text().splitlines() if line.startswith("/")]


def test_conf_has_limine_globals_and_kernel_entry(tmp_path: Path) -> None:
    text = write_conf(tmp_path).read_text()

    assert "timeout: 3" in text
    assert "default_entry: 1" in text
    assert "interface_branding: Syntropia Bootloader" in text
    assert "interface_branding_color: bd93f9" in text
    # `boot():` is the volume Limine was booted from — the ESP mounted at /boot.
    assert "    path: boot():/vmlinuz-linux-cachyos" in text
    assert "    module_path: boot():/initramfs-linux-cachyos.img" in text
    assert "    cmdline: root=UUID=abc rootflags=subvol=@ rw" in text
    assert "    protocol: linux" in text
    # Kernel and initramfs live at the ESP root next to the config, so no
    # /boot prefix may appear in the paths.
    assert "boot():/boot/" not in text


def test_conf_without_lts_kernel_has_one_entry(tmp_path: Path) -> None:
    conf = write_conf(tmp_path, lts="0")
    assert len(entry_lines(conf)) == 1
    assert "lts" not in conf.read_text().lower()


def test_conf_omits_wallpaper_without_a_splash(tmp_path: Path) -> None:
    text = write_conf(tmp_path).read_text()
    assert "wallpaper:" not in text
    assert not (tmp_path / "boot" / "syntropia-splash.png").exists()


def test_conf_uses_the_syntropia_wallpaper_when_shipped(tmp_path: Path) -> None:
    splash = tmp_path / "branding" / "wallpaper.png"
    splash.parent.mkdir()
    splash.write_bytes(b"png-bytes")

    conf = write_conf(tmp_path, splash=str(splash))
    text = conf.read_text()

    # The image is copied onto the ESP (Limine loads it from the boot volume)
    # and referenced, so the Calamares path's limineSplashLogo has a TUI twin.
    assert (tmp_path / "boot" / "syntropia-splash.png").read_bytes() == b"png-bytes"
    assert "wallpaper: boot():/syntropia-splash.png" in text
    assert "wallpaper_style: stretched" in text
    # Still exactly one menu entry: the wallpaper is a global option.
    assert len(entry_lines(conf)) == 1


def test_conf_with_lts_kernel_adds_second_entry(tmp_path: Path) -> None:
    conf = write_conf(tmp_path, lts="1")
    text = conf.read_text()
    entries = entry_lines(conf)
    assert len(entries) == 2
    assert "path: boot():/vmlinuz-linux-cachyos-lts" in text
    assert "module_path: boot():/initramfs-linux-cachyos-lts.img" in text
    # The default entry stays the main kernel.
    assert text.index(entries[0]) < text.index(entries[1])


def test_conf_entry_name_matches_os_release_pretty_name(tmp_path: Path) -> None:
    """The entry must equal os-release PRETTY_NAME: that is what
    limine-snapper-sync compares (via TARGET_OS_NAME) and what the branding
    hook renames CachyOS's bare `/+CachyOS` entry to."""
    source = TRANSFORM.read_text()
    pretty_name = None
    for node in ast.parse(source).body:
        if (
            isinstance(node, ast.Assign)
            and any(getattr(t, "id", "") == "OS_RELEASE_CONTENT" for t in node.targets)
            and isinstance(node.value, ast.Constant)
        ):
            pretty_name = next(
                line.split("=", 1)[1].strip('"')
                for line in node.value.value.splitlines()
                if line.startswith("PRETTY_NAME=")
            )
    assert pretty_name, "PRETTY_NAME not found in OS_RELEASE_CONTENT"

    entry = entry_lines(write_conf(tmp_path))[0]
    assert entry == f"/+{pretty_name}"

    # The branding hook pins the same name in /etc/default/limine.
    assert f'TARGET_OS_NAME="{pretty_name}"' in HOOK.read_text()


# --- UEFI install ----------------------------------------------------------

EFIBOOTMGR_STUB = """#!/bin/sh
if [ $# -eq 0 ]; then
    echo "Boot0001* Syntropia OS\tHD(2,GPT,abc)/File(\\\\EFI\\\\limine\\\\BOOTX64.EFI)"
    echo "Boot0002* Windows Boot Manager\tHD(2,GPT,def)"
    exit 0
fi
echo "efibootmgr $*" >> "$EFI_LOG"
"""


def fake_share_dir(tmp_path: Path) -> Path:
    share = tmp_path / "share" / "limine"
    share.mkdir(parents=True)
    (share / "BOOTX64.EFI").write_bytes(b"efi-binary")
    (share / "limine-bios.sys").write_bytes(b"bios-stage2")
    return share


def efibootmgr_bin(tmp_path: Path) -> Path:
    bindir = tmp_path / "stub-bin"
    bindir.mkdir()
    path = bindir / "efibootmgr"
    path.write_text(EFIBOOTMGR_STUB)
    path.chmod(0o755)
    return bindir


def test_efi_install_copies_loader_and_registers_entry(tmp_path: Path) -> None:
    share = fake_share_dir(tmp_path)
    bindir = efibootmgr_bin(tmp_path)
    efivars = tmp_path / "efivars"
    efivars.mkdir()
    boot = tmp_path / "boot"
    log = tmp_path / "efi.log"

    result = call_lib(
        "limine_install_efi", str(share), str(boot), "/dev/vda", "2",
        tmp_path=tmp_path,
        env={"PATH": f"{bindir}:/usr/bin:/bin", "LIMINE_EFIVARS_DIR": str(efivars),
             "EFI_LOG": str(log)},
    )

    assert result.returncode == 0, result.stderr
    # Both the firmware fallback path and the path NVRAM points at.
    assert (boot / "EFI" / "BOOT" / "BOOTX64.EFI").read_bytes() == b"efi-binary"
    assert (boot / "EFI" / "limine" / "BOOTX64.EFI").read_bytes() == b"efi-binary"

    calls = log.read_text()
    # Our own previous entry is dropped first so reinstalls don't pile up...
    assert "--delete-bootnum --bootnum 0001" in calls
    assert "0002" not in calls  # never touch another OS's entry
    # ...then Limine is registered with the ESP partition number.
    assert (
        "--create --disk /dev/vda --part 2 --label Syntropia OS "
        "--loader \\EFI\\limine\\BOOTX64.EFI"
    ) in calls


def test_efi_install_skips_efibootmgr_without_efivars(tmp_path: Path) -> None:
    share = fake_share_dir(tmp_path)
    bindir = efibootmgr_bin(tmp_path)
    boot = tmp_path / "boot"
    log = tmp_path / "efi.log"

    result = call_lib(
        "limine_install_efi", str(share), str(boot), "/dev/vda", "2",
        tmp_path=tmp_path,
        env={"PATH": f"{bindir}:/usr/bin:/bin",
             "LIMINE_EFIVARS_DIR": str(tmp_path / "no-such-efivars"),
             "EFI_LOG": str(log)},
    )

    assert result.returncode == 0, result.stderr
    assert (boot / "EFI" / "BOOT" / "BOOTX64.EFI").exists()
    assert not log.exists()


def test_efi_install_without_payload_fails_loudly(tmp_path: Path) -> None:
    empty = tmp_path / "share"
    empty.mkdir()
    boot = tmp_path / "boot"

    result = call_lib(
        "limine_install_efi", str(empty), str(boot), "/dev/vda", "2", tmp_path=tmp_path
    )

    assert result.returncode == 1
    assert "BOOTX64.EFI" in result.stderr
    assert not (boot / "EFI").exists()


# --- BIOS install ----------------------------------------------------------

LIMINE_STUB = """#!/bin/sh
echo "limine $*" >> "$LIMINE_LOG"
"""


def limine_stub(tmp_path: Path) -> Path:
    path = tmp_path / "stub-limine"
    path.write_text(LIMINE_STUB)
    path.chmod(0o755)
    return path


def test_bios_install_writes_stage2_and_runs_bios_install(tmp_path: Path) -> None:
    share = fake_share_dir(tmp_path)
    boot = tmp_path / "boot"
    log = tmp_path / "limine.log"

    result = call_lib(
        "limine_install_bios", str(share), str(boot), str(limine_stub(tmp_path)),
        "/dev/vda", "1",
        tmp_path=tmp_path, env={"LIMINE_LOG": str(log)},
    )

    assert result.returncode == 0, result.stderr
    # Limine loads stage 2 from the boot volume at boot time.
    assert (boot / "limine-bios.sys").read_bytes() == b"bios-stage2"
    assert log.read_text().strip() == "limine bios-install /dev/vda 1"


def test_bios_install_requires_limine_binary(tmp_path: Path) -> None:
    share = fake_share_dir(tmp_path)
    result = call_lib(
        "limine_install_bios", str(share), str(tmp_path / "boot"),
        str(tmp_path / "missing-limine"), "/dev/vda", "1", tmp_path=tmp_path,
    )
    assert result.returncode == 1
    assert "bios-install" in result.stderr


# --- runner structure ------------------------------------------------------

def test_runner_dropped_systemd_boot_and_grub() -> None:
    text = RUNNER.read_text()
    for gone in ("bootctl", "loader/entries", "systemd-bootx64.efi", "grub-install",
                 "grub-mkconfig"):
        assert gone not in text, f"{gone} still in the runner"


def test_runner_installs_limine() -> None:
    text = RUNNER.read_text()
    assert 'source "$INSTALLER_LIB/bootloader.sh"' in text
    for call in ("limine_conf_write", "limine_install_efi", "limine_install_bios",
                 "limine_tools_dir"):
        assert call in text, f"runner no longer calls {call}"
    # A missing limine package must abort instead of shipping an unbootable system.
    assert "Rebuild the ISO" in text


def test_runner_partitions_a_bios_boot_partition() -> None:
    text = RUNNER.read_text()
    # Limine's BIOS stage 2 needs a GPT "BIOS boot" partition (type ef02).
    assert '-t 1:ef02' in text
    assert '-t 2:ef00' in text
    assert '-t 3:8309' in text
    assert 'BIOS_PART="${TARGET_DISK}p1"' in text
    assert 'BOOT_PART="${TARGET_DISK}p2"' in text
    assert 'ROOT_PART="${TARGET_DISK}p3"' in text


def test_lib_is_shipped_with_the_installer() -> None:
    """build.sh installs iso/installer/lib/*.sh verbatim, so a new lib is
    picked up automatically — pin that the glob (not a hardcoded list) is used."""
    build = (REPO / "iso" / "build.sh").read_text()
    assert '"$installer_src"/lib/*.sh' in build
    assert LIB.is_file()
    assert LIB.stat().st_mode & 0o111 == 0  # sourced, never executed


# --- branding hook: identity sync stays intact ----------------------------

CORE_TOOLS = ("awk", "bash", "cat", "chmod", "chown", "cp", "dirname", "grep",
              "mkdir", "rm", "sed", "basename")


def core_bin(tmp_path: Path) -> Path:
    """PATH holding only coreutils — so the hook's kdialog/notify-send
    notification branch cannot pop a window during the test."""
    bindir = tmp_path / "core-bin"
    bindir.mkdir(exist_ok=True)
    for tool in CORE_TOOLS:
        target = subprocess.run(["sh", "-c", f"command -v {tool}"],
                                capture_output=True, text=True).stdout.strip()
        assert target, f"{tool} missing on this host"
        link = bindir / tool
        if not link.exists():
            link.symlink_to(target)
    return bindir


def run_hook(root: Path, tmp_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(HOOK), str(root)],
        capture_output=True,
        text=True,
        env={"PATH": f"{core_bin(tmp_path)}", "LANG": "C.UTF-8"},
        cwd=str(tmp_path),
        timeout=60,
    )


def make_root(tmp_path: Path, conf: str, default_limine: str | None = "") -> Path:
    root = tmp_path / "target"
    (root / "boot").mkdir(parents=True)
    (root / "boot" / "limine.conf").write_text(conf)
    (root / "etc").mkdir()
    if default_limine is not None:
        (root / "etc" / "default").mkdir()
        (root / "etc" / "default" / "limine").write_text(default_limine)
    return root


def test_hook_renames_bare_cachyos_entry_once(tmp_path: Path) -> None:
    root = make_root(tmp_path, "timeout: 3\n/+CachyOS\n    protocol: linux\n")

    first = run_hook(root, tmp_path)
    assert first.returncode == 0, first.stderr
    conf = (root / "boot" / "limine.conf").read_text()
    assert "/+CachyOS Syntropia\n" in conf

    second = run_hook(root, tmp_path)  # an install re-run must not double-rename
    assert second.returncode == 0, second.stderr
    conf = (root / "boot" / "limine.conf").read_text()
    assert [line for line in conf.splitlines() if line.startswith("/")] == [
        "/+CachyOS Syntropia"
    ]
    assert "Syntropia Syntropia" not in conf
    assert conf.count("interface_branding:") == 1

    pinned = (root / "etc" / "default" / "limine").read_text()
    assert pinned.count("TARGET_OS_NAME") == 1
    assert 'TARGET_OS_NAME="CachyOS Syntropia"' in pinned


@pytest.mark.parametrize(
    "entry",
    [
        "/+CachyOS",           # CachyOS' own installer / limine-entry-tool
        "/+Syntropia",          # Calamares limine module via branding.desc
        "/Syntropia OS",        # no `+` (expanded-directory marker) variant
        "/CachyOS",             # no `+`, no branding
        "/+CachyOS Syntropia",  # already canonical: must stay unchanged
    ],
)
def test_hook_normalises_every_installer_spelling(tmp_path: Path, entry: str) -> None:
    """Both installers must end up with the one name limine-snapper-sync is
    pinned to, and a second run must be a no-op."""
    root = make_root(tmp_path, f"timeout: 3\n{entry}\n    protocol: linux\n")

    for _ in range(2):
        result = run_hook(root, tmp_path)
        assert result.returncode == 0, result.stderr
        entries = [
            line for line in (root / "boot" / "limine.conf").read_text().splitlines()
            if line.startswith("/")
        ]
        assert entries == ["/+CachyOS Syntropia"]

    pinned = (root / "etc" / "default" / "limine").read_text()
    assert pinned.count("TARGET_OS_NAME") == 1


def test_hook_creates_the_target_os_pin_when_the_file_is_absent(tmp_path: Path) -> None:
    root = make_root(tmp_path, "timeout: 3\n/+CachyOS\n", default_limine=None)

    result = run_hook(root, tmp_path)

    assert result.returncode == 0, result.stderr
    pinned = root / "etc" / "default" / "limine"
    assert pinned.read_text() == 'TARGET_OS_NAME="CachyOS Syntropia"\n'


def test_hook_leaves_runner_generated_entry_untouched(tmp_path: Path) -> None:
    boot = tmp_path / "generated" / "boot"
    write = call_lib("limine_conf_write", str(boot), "root=UUID=abc rw", "0",
                     str(tmp_path / "no-splash.png"), tmp_path=tmp_path)
    assert write.returncode == 0, write.stderr

    root = make_root(tmp_path, (boot / "limine.conf").read_text())
    result = run_hook(root, tmp_path)
    assert result.returncode == 0, result.stderr

    conf = (root / "boot" / "limine.conf").read_text()
    assert entry_lines(root / "boot" / "limine.conf") == ["/+CachyOS Syntropia"]
    assert "Syntropia Syntropia" not in conf
    # The runner already wrote the branded interface, so the hook's injection
    # guard must leave exactly one of each global.
    assert conf.count("interface_branding:") == 1
    assert conf.count("term_background:") == 1
