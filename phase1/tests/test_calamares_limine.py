"""Tests for the Calamares install path's Limine bootloader.

Calamares does not install the bootloader itself — CachyOS' `bootloader`
module does, and it already knows Limine. build.sh therefore (a) selects
Limine explicitly in `bootloader.conf`, (b) brands it, and (c) adds a
shellprocess check right after the module that refuses to finish an install
whose disk would not boot. These tests drive the real build.sh patch blocks
against fixture Calamares configs and run the real hook against a fake target
root, so the patch text is never taken on trust.
"""

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BUILD = REPO / "iso" / "build.sh"
HOOK = REPO / "iso" / "hook-scripts" / "hook-limine.sh"

BASE_ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}

BOOTLOADER_CONF = """\
---
efiBootLoaderVar: "packagechooser_bootloader"
efiBootLoader: "systemd-boot"
kernelSearchPath: "/usr/lib/modules"
efiBootloaderId: "cachyos"
installEFIFallback: true
installHybridGRUB: false
limineSplashLogo: "/usr/share/wallpapers/cachyos-wallpapers/limine-splash.png"
"""


def run(script: str, cwd: Path, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        env={**BASE_ENV, **(env or {})},
        cwd=str(cwd),
        timeout=120,
    )


def build_block(start: str, end: str) -> str:
    """Pull one shell block out of build.sh, verbatim."""
    src = BUILD.read_text()
    pattern = re.escape(start) + r".*?" + re.escape(end)
    match = re.search(pattern, src, re.S)
    assert match, f"build.sh no longer contains the {start!r} ... {end!r} block"
    return match.group(0)


SETTINGS = """\
---
instances:
- id:       bootloader
  module:   packagechooser
  config:   packagechooser_bootloader.conf

- id:       syntropia_wizard
  module:   shellprocess
  config:   shellprocess_syntropia_wizard.conf


sequence:
- show:
  - welcome
- execute:
  - welcome
  - partition
  - mount
  - unpackfs
  - bootloader
  - shellprocess@reset_mk_hook
  - shellprocess@syntropia_wizard
  - umount
"""


# --- build.sh: select Limine in the Calamares bootloader module -----------

def test_build_patches_calamares_to_limine(tmp_path: Path) -> None:
    conf = tmp_path / "rootfs" / "etc" / "calamares" / "modules" / "bootloader.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text(BOOTLOADER_CONF)

    block = build_block(
        'info "Configuring Calamares bootloader module for Limine..."',
        'ok "Calamares bootloader configured to Limine"',
    )
    result = run(f"ok() {{ :; }}; info() {{ :; }}\n{block}", tmp_path)
    assert result.returncode == 0, result.stderr

    text = conf.read_text()
    assert 'efiBootLoader: "limine"' in text
    assert 'efiBootLoaderVar: ""' in text  # bootloader picker is not in the sequence
    assert 'efiBootloaderId: "syntropia"' in text
    assert "installEFIFallback: true" in text
    assert (
        'limineSplashLogo: "/usr/share/syntropia/branding/wallpaper.png"' in text
    )
    # No stale CachyOS splash or loader selection.
    assert "cachyos-wallpapers" not in text
    assert "systemd-boot" not in text


def test_build_does_not_force_systemd_boot_anywhere() -> None:
    text = BUILD.read_text()
    assert 'efiBootLoader: "systemd-boot"' not in text
    assert "bootctl install" not in text
    # Limine is still both shipped (live rootfs + basePackages) and selected.
    assert 'efiBootLoader: "limine"' in text
    assert "grep -qx 'limine' packages.x86_64" in text


# --- build.sh: schedule the post-bootloader check -------------------------

def make_rootfs(tmp_path: Path, settings: str = SETTINGS) -> Path:
    settings_file = tmp_path / "rootfs" / "usr" / "share" / "calamares" / "settings_online.conf"
    settings_file.parent.mkdir(parents=True)
    settings_file.write_text(settings)
    return tmp_path / "rootfs"


def registration_block() -> str:
    src = BUILD.read_text()
    start = src.index('    cat > "rootfs/etc/calamares/modules/shellprocess_syntropia_limine.conf"')
    end = src.index('ok "Limine bootloader check wired into Calamares"')
    block = src[start:end]
    # Keep only the python heredoc that registers the instance in the sequence.
    py_start = block.index("<< 'PYEOF'") + len("<< 'PYEOF'")
    py_end = block.index("\nPYEOF")
    return block[py_start:py_end]


def test_limine_check_is_registered_right_after_the_bootloader(tmp_path: Path) -> None:
    rootfs = make_rootfs(tmp_path)
    script = f"python3 - {str(rootfs)!r} << 'PYEOF'\n{registration_block()}\nPYEOF"
    result = run(script, tmp_path)
    assert result.returncode == 0, result.stderr

    text = (rootfs / "usr" / "share" / "calamares" / "settings_online.conf").read_text()
    assert "- id:       syntropia_limine" in text
    assert "  config:   shellprocess_syntropia_limine.conf" in text
    # Must run immediately after the module it verifies, before umount.
    assert "- bootloader\n  - shellprocess@syntropia_limine\n" in text
    assert text.index("syntropia_limine") < text.index("- umount")

    # Re-running build.sh must not duplicate the instance or the step.
    again = run(script, tmp_path)
    assert again.returncode == 0, again.stderr
    text = (rootfs / "usr" / "share" / "calamares" / "settings_online.conf").read_text()
    assert text.count("- id:       syntropia_limine") == 1
    assert text.count("- shellprocess@syntropia_limine") == 1


def test_shellprocess_conf_calls_the_hook_and_can_fail_the_install() -> None:
    src = BUILD.read_text()
    conf = re.search(
        r"shellprocess_syntropia_limine\.conf\" << 'LIMINECONF'\n(.*?)\nLIMINECONF",
        src,
        re.S,
    )
    assert conf, "shellprocess conf for Limine is missing"
    body = conf.group(1)
    assert "dontChroot: true" in body
    assert 'command: "bash /etc/syntropia/hook-limine.sh ${ROOT}"' in body
    # No bare shell variables in the command (KWordMacroExpander would expand them).
    command = next(line for line in body.splitlines() if "command:" in line)
    assert "$" not in command.replace("${ROOT}", "")


def test_hook_is_shipped_with_the_live_installer() -> None:
    text = BUILD.read_text()
    assert 'cp "$SCRIPT_DIR/hook-scripts/hook-limine.sh" "$syn_dir/"' in text
    assert 'chmod +x "$syn_dir/hook-branding-users.sh" "$syn_dir/hook-limine.sh"' in text
    assert HOOK.is_file()


# --- hook-limine.sh behaviour --------------------------------------------

def target(tmp_path: Path, *, conf: bool = True, efi: bool = True,
           bios_sys: bool = False, payload_dir: bool = False) -> Path:
    root = tmp_path / "target"
    (root / "boot").mkdir(parents=True)
    (root / "var" / "log").mkdir(parents=True)
    if conf:
        (root / "boot" / "limine.conf").write_text(
            "timeout: 3\n/+CachyOS\n    protocol: linux\n"
        )
    if efi:
        efi_dir = root / "boot" / "EFI" / "BOOT"
        efi_dir.mkdir(parents=True)
        (efi_dir / "BOOTX64.EFI").write_bytes(b"efi")
    if bios_sys:
        (root / "boot" / "limine-bios.sys").write_bytes(b"stage2")
    if payload_dir:
        share = root / "usr" / "share" / "limine"
        share.mkdir(parents=True)
        (share / "BOOTX64.EFI").write_bytes(b"from-package")
        (share / "limine-bios.sys").write_bytes(b"stage2-from-package")
    return root


def run_hook(root: Path, tmp_path: Path, **env: str) -> subprocess.CompletedProcess:
    return run(f'bash "{HOOK}" "{root}"', tmp_path, env=env)


def test_uefi_install_is_verified(tmp_path: Path) -> None:
    root = target(tmp_path)
    efivars = tmp_path / "efivars"
    efivars.mkdir()

    result = run_hook(root, tmp_path, SYNTROPIA_EFIVARS_DIR=str(efivars))

    assert result.returncode == 0, result.stderr
    assert "UEFI payload present" in result.stdout
    assert "Limine bootloader verified" in result.stdout


def test_uefi_install_repairs_a_missing_efi_payload(tmp_path: Path) -> None:
    root = target(tmp_path, efi=False, payload_dir=True)
    efivars = tmp_path / "efivars"
    efivars.mkdir()

    result = run_hook(root, tmp_path, SYNTROPIA_EFIVARS_DIR=str(efivars))

    assert result.returncode == 0, result.stderr
    # The hook tees stderr into the same stream as stdout (so the messages also
    # land in the target's /var/log/syntropia-hooks.log).
    assert "repaired" in result.stdout
    assert (root / "boot" / "EFI" / "BOOT" / "BOOTX64.EFI").read_bytes() == b"from-package"


def test_uefi_install_without_any_payload_fails(tmp_path: Path) -> None:
    root = target(tmp_path, efi=False)
    efivars = tmp_path / "efivars"
    efivars.mkdir()

    result = run_hook(root, tmp_path, SYNTROPIA_EFIVARS_DIR=str(efivars))

    assert result.returncode == 1
    assert "no Limine EFI executable" in result.stdout


def test_install_without_limine_conf_fails(tmp_path: Path) -> None:
    root = target(tmp_path, conf=False)
    efivars = tmp_path / "efivars"
    efivars.mkdir()

    result = run_hook(root, tmp_path, SYNTROPIA_EFIVARS_DIR=str(efivars))

    assert result.returncode == 1
    assert "no limine.conf" in result.stdout


LSBLK_STUB = """#!/bin/sh
# Minimal lsblk: the ESP lives on /dev/vda2, whose disk is vda.
case "$*" in
  *PKNAME*) echo vda ;;
  *PARTTYPE*)
    echo "1 21686148-6449-6E6F-744E-656564454649"
    echo "2 C12A7328-F81F-11D2-BA4B-00A0C93EC93B"
    ;;
  *) exit 0 ;;
esac
"""

LSBLK_STUB_NO_EF02 = """#!/bin/sh
case "$*" in
  *PKNAME*) echo vda ;;
  *PARTTYPE*) echo "1 C12A7328-F81F-11D2-BA4B-00A0C93EC93B" ;;
  *) exit 0 ;;
esac
"""

LIMINE_STUB = """#!/bin/sh
echo "limine $*" >> "$LIMINE_LOG"
"""


def bios_bin(tmp_path: Path, lsblk_stub: str = LSBLK_STUB) -> dict:
    bindir = tmp_path / "bios-bin"
    bindir.mkdir(exist_ok=True)
    (bindir / "lsblk").write_text(lsblk_stub)
    (bindir / "lsblk").chmod(0o755)
    limine = tmp_path / "stub-limine"
    limine.write_text(LIMINE_STUB)
    limine.chmod(0o755)
    return {
        "PATH": f"{bindir}:/usr/bin:/bin",
        "SYNTROPIA_EFIVARS_DIR": str(tmp_path / "no-efivars"),
        "SYNTROPIA_LIMINE_ESP": "/dev/vda2",
        "SYNTROPIA_LIMINE_DISK": "/dev/vda",
        "SYNTROPIA_LIMINE_BIN": str(limine),
        "LIMINE_LOG": str(tmp_path / "limine.log"),
    }


def test_bios_install_runs_bios_install_on_the_ef02_partition(tmp_path: Path) -> None:
    root = target(tmp_path, efi=False, bios_sys=True)

    result = run_hook(root, tmp_path, **bios_bin(tmp_path))

    assert result.returncode == 0, result.stderr
    assert "BIOS boot partition" in result.stdout
    # Same command the TUI runner runs — idempotent, so re-running is safe.
    assert (tmp_path / "limine.log").read_text().strip() == (
        "limine bios-install /dev/vda 1"
    )


def test_bios_install_without_an_ef02_partition_fails(tmp_path: Path) -> None:
    root = target(tmp_path, efi=False, bios_sys=True)

    result = run_hook(root, tmp_path, **bios_bin(tmp_path, LSBLK_STUB_NO_EF02))

    assert result.returncode == 1
    assert "ef02" in result.stdout
    assert not (tmp_path / "limine.log").exists()


def test_bios_install_repairs_missing_stage2(tmp_path: Path) -> None:
    root = target(tmp_path, efi=False, payload_dir=True)

    result = run_hook(root, tmp_path, **bios_bin(tmp_path))

    assert result.returncode == 0, result.stderr
    assert (root / "boot" / "limine-bios.sys").read_bytes() == b"stage2-from-package"
    assert "copied from" in result.stdout
