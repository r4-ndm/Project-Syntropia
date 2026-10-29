"""Tests for the Brave/Chromium chrome-sandbox permission fix.

Brave is installed by the apps wizard (paru/AUR `brave-bin`), i.e. after the
installer has finished, so the fix lives in a pacman hook that build.sh ships
into the live rootfs — the runner's rsync carries it into every installed
system. A chrome-sandbox that is not root:root 4755 makes Brave refuse to start;
the fix is the upstream permission, never `--no-sandbox`.
"""

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HOOK = REPO / "iso" / "hook-scripts" / "hook-chrome-sandbox.sh"
BUILD = REPO / "iso" / "build.sh"

BASE_ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}

# Records the call; the real chown/chmod are not allowed to run as a test user.
STUB = """#!/bin/sh
echo "$(basename "$0") $*" >> "$SANDBOX_LOG"
exit 0
"""


def stubs(tmp_path: Path) -> tuple:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name in ("chown", "chmod"):
        stub = bindir / name
        stub.write_text(STUB)
        stub.chmod(0o755)
    return bindir, tmp_path / "calls.log"


def run_hook(paths: list, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(HOOK), *[str(p) for p in paths]],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def test_a_broken_helper_gets_root_ownership_and_setuid(tmp_path: Path) -> None:
    helper = tmp_path / "chrome-sandbox"
    helper.write_text("#!/bin/sh\n")
    bindir, log = stubs(tmp_path)
    env = {**BASE_ENV, "PATH": f"{bindir}:{BASE_ENV['PATH']}", "SANDBOX_LOG": str(log)}

    result = run_hook([helper], env)

    assert result.returncode == 0, result.stderr
    calls = log.read_text()
    assert f"chown root:root {helper}" in calls
    assert f"chmod 4755 {helper}" in calls
    assert "fixed to root:root 4755" in result.stdout


def test_a_missing_helper_is_not_an_error(tmp_path: Path) -> None:
    bindir, log = stubs(tmp_path)
    env = {**BASE_ENV, "PATH": f"{bindir}:{BASE_ENV['PATH']}", "SANDBOX_LOG": str(log)}

    result = run_hook([tmp_path / "nope" / "chrome-sandbox"], env)

    assert result.returncode == 0, result.stderr
    assert not log.exists(), "nothing to fix, nothing to call"
    assert result.stdout == ""


def test_the_fix_is_the_setuid_helper_not_a_no_sandbox_wrapper() -> None:
    # The comment explains why --no-sandbox is wrong; no active line may use it.
    active = [
        line for line in HOOK.read_text().splitlines()
        if not line.lstrip().startswith("#")
    ]
    assert not any("--no-sandbox" in line for line in active)
    assert any("chmod 4755" in line for line in active)


def test_build_ships_the_fixer_and_a_pacman_hook_for_every_brave_path() -> None:
    build = BUILD.read_text()
    assert "hook-scripts/hook-chrome-sandbox.sh" in build
    assert "rootfs/usr/local/bin/syntropia-fix-chrome-sandbox" in build
    assert "etc/pacman.d/hooks/syntropia-chrome-sandbox.hook" in build
    # AUR brave-bin (opt/brave.com) and the repo package (usr/lib/brave) both
    # need the trigger, or whichever one the wizard installs stays broken.
    # Current brave-bin PKGBUILD installs under opt/brave-bin (2026-10-29
    # laptop), older revisions under opt/brave.com — both need the trigger.
    assert "Target = opt/brave-bin/chrome-sandbox" in build
    assert "Target = opt/brave.com/brave/chrome-sandbox" in build
    assert "Target = usr/lib/brave/chrome-sandbox" in build
    assert "When = PostTransaction" in build
