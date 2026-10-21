"""Tests for the TUI installer's Syntropia identity copy.

Calamares copies the generated `/usr/share/syntropia/branding/os-release` into
the target (`syntropia_branding` shellprocess, iso/build.sh). The TUI path did
not, so a TUI install kept CachyOS' stock `/etc/os-release` while limine.conf
and `TARGET_OS_NAME` said "CachyOS Syntropia" — found in the 2026-10-21 VM
test (`PRETTY_NAME="CachyOS"` on the installed system).

The runner is destructive, so these tests pull the real identity block out of
it and run that block against a fixture target.
"""

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
INSTALLER_DIR = REPO / "iso" / "installer"
RUNNER = INSTALLER_DIR / "syntropia-install-runner"
BOOTLOADER_LIB = INSTALLER_DIR / "lib" / "bootloader.sh"
HOOK = REPO / "iso" / "hook-scripts" / "hook-branding-users.sh"
TRANSFORM = REPO / "phase1" / "cli" / "transform" / "syntropia_transform" / "transform.py"

BASE_ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}

SYNTROPIA_OS_RELEASE = (
    'NAME="Syntropia"\n'
    'PRETTY_NAME="CachyOS Syntropia"\n'
    "ID=cachyos\n"
    'ID_LIKE="arch"\n'
    'VARIANT="Syntropia"\n'
    "VARIANT_ID=syntropia\n"
)
SYNTROPIA_LSB_RELEASE = (
    "DISTRIB_ID=Syntropia\n"
    'DISTRIB_DESCRIPTION="CachyOS Syntropia"\n'
)
STOCK_OS_RELEASE = 'NAME="CachyOS Linux"\nPRETTY_NAME="CachyOS"\nID=cachyos\n'


def identity_block() -> str:
    """The runner's identity block, verbatim, bounded by its own markers."""
    src = RUNNER.read_text()
    start = src.index("# --- Syntropia identity: os-release / lsb-release")
    end = src.index("# --- end Syntropia identity")
    return src[start:end]


def run_block(tmp_path: Path, *, assets: bool = True, stock: bool = True) -> subprocess.CompletedProcess:
    """Run the real block with HOME/TARGET pointed at a fixture target."""
    target = tmp_path / "target"
    (target / "etc").mkdir(parents=True)
    if stock:
        (target / "etc" / "os-release").write_text(STOCK_OS_RELEASE)
    if assets:
        # The block reads the live image's asset dir; point it at the fixture.
        live = tmp_path / "live"
        share = live / "usr" / "share" / "syntropia" / "branding"
        share.mkdir(parents=True)
        (share / "os-release").write_text(SYNTROPIA_OS_RELEASE)
        (share / "lsb-release").write_text(SYNTROPIA_LSB_RELEASE)
    script = f'set -euo pipefail\nTARGET={str(target)!r}\n' + identity_block()
    if assets:
        # Redirect the absolute asset path into the fixture tree.
        script = script.replace(
            'identity_src="/usr/share/syntropia/branding/$identity_file"',
            f'identity_src="{tmp_path}/live/usr/share/syntropia/branding/$identity_file"',
        )
    return subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        env=BASE_ENV,
        cwd=str(tmp_path),
        timeout=60,
    )


# --- behaviour ------------------------------------------------------------

def test_identity_is_copied_into_the_target(tmp_path: Path) -> None:
    result = run_block(tmp_path)
    assert result.returncode == 0, result.stderr

    target = tmp_path / "target"
    assert (target / "etc" / "os-release").read_text() == SYNTROPIA_OS_RELEASE
    assert (target / "etc" / "lsb-release").read_text() == SYNTROPIA_LSB_RELEASE
    # The stock file is replaced, not appended to.
    assert "CachyOS Linux" not in (target / "etc" / "os-release").read_text()
    # The install log says what identity the system ended up with.
    assert 'PRETTY_NAME="CachyOS Syntropia"' in result.stdout


def test_identity_files_are_world_readable(tmp_path: Path) -> None:
    assert run_block(tmp_path).returncode == 0
    mode = (tmp_path / "target" / "etc" / "os-release").stat().st_mode & 0o777
    assert mode == 0o644


def test_missing_asset_warns_and_leaves_the_system_alone(tmp_path: Path) -> None:
    result = run_block(tmp_path, assets=False)

    # A missing branding asset must not abort an otherwise finished install.
    assert result.returncode == 0, result.stderr
    assert "missing" in result.stderr
    assert (tmp_path / "target" / "etc" / "os-release").read_text() == STOCK_OS_RELEASE
    assert not (tmp_path / "target" / "etc" / "lsb-release").exists()


def test_block_runs_after_the_branding_hook() -> None:
    src = RUNNER.read_text()
    hook_call = 'bash /etc/syntropia/hook-branding-users.sh "$TARGET"'
    assert hook_call in src
    # The hook normalises limine.conf/TARGET_OS_NAME; the identity copy must
    # come after it, inside the same (last) branding phase.
    assert src.index('set_phase "Applying Syntropia branding & identity"') < src.index(hook_call)
    assert src.index(hook_call) < src.index("# --- Syntropia identity: os-release / lsb-release")


def test_no_second_copy_of_the_identity_later_in_the_runner() -> None:
    # One place writes /etc/os-release; a later copy would silently undo it.
    src = RUNNER.read_text()
    assert src.count('"$TARGET/etc/os-release"') == 2  # install + the log line
    assert src.count("install -Dm644 \"$identity_src\"") == 1


# --- contract with the identity sources -----------------------------------

def test_pristine_asset_matches_the_limine_entry_and_target_os_name() -> None:
    # transform.py is the single source of truth for the asset; the limine
    # entry name and TARGET_OS_NAME have to agree with it, or snapshots warn.
    transform = TRANSFORM.read_text()
    assert 'PRETTY_NAME="CachyOS Syntropia"' in transform

    bootloader = BOOTLOADER_LIB.read_text()
    entry = re.search(r'LIMINE_ENTRY_NAME="\$\{LIMINE_ENTRY_NAME:-([^}]+)\}"', bootloader)
    assert entry, "LIMINE_ENTRY_NAME is no longer overridable the way the tests expect"
    assert entry.group(1) == "/+CachyOS Syntropia"

    hook = HOOK.read_text()
    assert 'TARGET_OS_NAME="CachyOS Syntropia"' in hook
    # The hook normalises anything else to the same string.
    assert "#/+CachyOS Syntropia#" in hook
