"""Tests for the phase-2 stale stock ISO guard (iso/lib/verify-live-image.sh).

`--phase2` remasters an existing stock ISO and cannot install packages, so a
stock image built before the current package patch produces an ISO that boots
and then fails every install at the bootloader step. That is exactly what the
2026-10-21 VM test hit: an Oct-21 ISO whose live image had no `limine`
package. The guard reads the *unsquashed* rootfs and fails with the reason.
"""

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
GUARD = REPO / "iso" / "lib" / "verify-live-image.sh"
BUILD = REPO / "iso" / "build.sh"

BASE_ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}

PACKAGE = "var/lib/pacman/local/limine-12.9.3-2"
PAYLOADS = ("usr/share/limine/BOOTX64.EFI", "usr/share/limine/limine-bios.sys")


def rootfs(tmp_path: Path, *, package: bool = True, payloads=PAYLOADS) -> Path:
    """A stand-in for the unsquashed airootfs the guard inspects."""
    root = tmp_path / "rootfs"
    if package:
        (root / PACKAGE).mkdir(parents=True)
        (root / PACKAGE / "desc").write_text("NAME=limine\n")
    for payload in payloads:
        path = root / payload
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"payload")
    # A stock CachyOS image has the installer scripts' mount points but no
    # limine: create the rest of the tree so the "missing" cases are about the
    # package only.
    (root / "usr" / "share" / "calamares").mkdir(parents=True, exist_ok=True)
    return root


def run_guard(root: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(GUARD), str(root), *extra],
        capture_output=True,
        text=True,
        env=BASE_ENV,
        timeout=60,
    )


# --- current image --------------------------------------------------------

def test_current_image_passes_silently(tmp_path: Path) -> None:
    result = run_guard(rootfs(tmp_path), str(tmp_path / "syntropia-stock.iso"))
    assert result.returncode == 0, result.stderr
    assert result.stdout == ""
    assert result.stderr == ""


def test_package_db_entry_alone_with_all_payloads_is_enough(tmp_path: Path) -> None:
    # mkarchiso also ships other limine versions/arch payloads; only the x86_64
    # pair the installer copies matters.
    result = run_guard(rootfs(tmp_path, payloads=PAYLOADS))
    assert result.returncode == 0, result.stderr


# --- stale image ----------------------------------------------------------

def test_stale_image_fails_with_every_reason(tmp_path: Path) -> None:
    iso = tmp_path / "out" / "syntropia-2026.08.12-x86_64-stock.iso"
    root = tmp_path / "rootfs"
    (root / "usr" / "share" / "calamares").mkdir(parents=True)

    result = run_guard(root, str(iso))

    assert result.returncode == 1
    err = result.stderr
    assert "Stale stock image" in err
    assert str(iso) in err  # names the image the operator passed
    assert "package limine is not installed" in err
    assert "usr/share/limine/BOOTX64.EFI is missing" in err
    assert "usr/share/limine/limine-bios.sys is missing" in err
    # The message has to say what to do, not just what is wrong.
    assert "sudo iso/build.sh" in err
    assert "cannot install packages" in err


def test_missing_payloads_are_named_individually(tmp_path: Path) -> None:
    root = rootfs(tmp_path, payloads=("usr/share/limine/BOOTX64.EFI",))
    result = run_guard(root)

    assert result.returncode == 1
    assert "limine-bios.sys is missing" in result.stderr
    # The payload that is present must not be reported as missing.
    assert "BOOTX64.EFI is missing" not in result.stderr
    assert "package limine is not installed" not in result.stderr


def test_hand_copied_payloads_without_the_package_still_fail(tmp_path: Path) -> None:
    # A stray file pair means the image was edited by hand and will not survive
    # a kernel/mkinitcpio update — the package record is what makes it current.
    result = run_guard(rootfs(tmp_path, package=False))

    assert result.returncode == 1
    assert "package limine is not installed" in result.stderr


# --- invocation -----------------------------------------------------------

def test_missing_rootfs_is_an_invocation_error(tmp_path: Path) -> None:
    result = run_guard(tmp_path / "does-not-exist")
    assert result.returncode == 2
    assert "no unsquashed rootfs" in result.stderr


def test_no_arguments_is_an_invocation_error() -> None:
    result = subprocess.run(
        [str(GUARD)], capture_output=True, text=True, env=BASE_ENV, timeout=30
    )
    assert result.returncode == 2
    assert "no unsquashed rootfs" in result.stderr


# --- build.sh wiring ------------------------------------------------------

def test_guard_is_executable() -> None:
    assert GUARD.is_file()
    assert GUARD.stat().st_mode & 0o111


def guard_call_block() -> str:
    """The real info/if/err lines build.sh uses to invoke the guard."""
    src = BUILD.read_text()
    start = src.index('    info "Verifying the stock image carries the current live package set..."')
    end_marker = 'ok "Stock image is current (limine package + payloads present)"'
    end = src.index(end_marker) + len(end_marker) + 1
    return src[start:end]


def run_guard_call(tmp_path: Path, root: Path) -> subprocess.CompletedProcess:
    """Execute build.sh's guard call with stubs for its reporting helpers."""
    script = (
        "set -e\n"
        f'SCRIPT_DIR="{REPO / "iso"}"\n'
        f'remaster_dir="{tmp_path}"\n'
        "input_iso=/out/syntropia-stock.iso\n"
        'info() { :; }\n'
        'ok() { echo "OK: $*"; }\n'
        'err() { echo "ERR: $*" >&2; exit 9; }\n'
        + guard_call_block()
    )
    if root != tmp_path / "rootfs":
        script = script.replace(f'"{tmp_path}/rootfs"', f'"{root}"')
    return subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, env=BASE_ENV, timeout=60
    )


def test_build_sh_fails_the_run_on_a_stale_image(tmp_path: Path) -> None:
    root = tmp_path / "rootfs"
    (root / "usr" / "share" / "calamares").mkdir(parents=True)

    result = run_guard_call(tmp_path, root)

    # build.sh's err() exits; the run must not continue into the remaster.
    assert result.returncode == 9
    assert "Stale stock ISO" in result.stderr
    assert "OK:" not in result.stdout


def test_build_sh_continues_on_a_current_image(tmp_path: Path) -> None:
    rootfs(tmp_path)  # creates tmp_path/rootfs with the package + payloads

    result = run_guard_call(tmp_path, tmp_path / "rootfs")

    assert result.returncode == 0, result.stderr
    assert "OK: Stock image is current" in result.stdout


def test_phase2_runs_the_guard_before_touching_the_image() -> None:
    src = BUILD.read_text()
    guard_call = 'if ! "$SCRIPT_DIR/lib/verify-live-image.sh" "$remaster_dir/rootfs" "$input_iso"; then'
    assert guard_call in src

    # After the rootfs is available to inspect, and before the first injection
    # step: a stale image must fail in the first minute, not after a remaster.
    assert src.index('ok "Rootfs unsquashed') < src.index(guard_call)
    assert src.index(guard_call) < src.index('info "Injecting Syntropia slides..."')
    # And the failure is fatal, not a warning.
    after = src[src.index(guard_call):]
    assert "err \"Stale stock ISO" in after[:400]
