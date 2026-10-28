"""Tests for app-wiz4rd's install path, queue and connectivity prompt.

The ISO ships the wizard from the vendored release tarball in iso/vendor/, so
that tarball is what the installed system actually runs — the tests extract it
and drive it with stub `yay` / pacman / network / TUI binaries. What we pin:
picks install visibly while online (yay is really called, and the output is
logged), the picker offers nmtui before the app list while offline, a pick made
while offline is never lost, and the next run (or `--resume`) finishes the job
once the network is back.

The picker's own key handling (enter installs from any row) is pinned by the Go
tests in the app-wiz4rd repo, dialog/main_test.go.
"""

import hashlib
import os
import pty
import shutil
import subprocess
import tarfile
import threading
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TARBALL = REPO / "iso" / "vendor" / "app-wiz4rd-0.1.0.tar"

YAY_STUB = """#!/bin/sh
echo "yay $*" >> "$WIZ_YAY_LOG"
[ -f "$WIZ_ONLINE" ] || exit 1
echo "yay: installing $*"
exit "${WIZ_YAY_RC:-0}"
"""

NETWORK_STUB = """#!/bin/sh
[ -f "$WIZ_ONLINE" ] && exit 0
exit 1
"""

# pacman -Q <pkg>: succeed only for packages listed in WIZ_INSTALLED_FILE — how
# the tests model "yay failed, but some of the transaction landed".
PACMAN_STUB = """#!/bin/sh
echo "$*" >> "$WIZ_PACMAN_LOG"
[ "$1" = "-Q" ] || exit 0
for pkg in $(cat "$WIZ_INSTALLED_FILE" 2>/dev/null); do
    [ "$2" = "$pkg" ] && exit 0
done
exit 1
"""

NMTUI_STUB = """#!/bin/sh
echo "nmtui-connect $*" >> "$WIZ_NMTUI_LOG"
exit 0
"""

FZF_STUB = """#!/bin/sh
# Stand-in for the fzf picker: reads catalog rows from stdin and echoes the
# rows whose package field (field 2) or display line (field 1) matches the
# requested picks in $WIZ_SELECTION, preserving all tab-separated fields.
awk -F'\\t' -v picks="${WIZ_SELECTION:-}" '
BEGIN {
    n = split(picks, want, /[[:space:]]+/)
}
{
    rows[NR] = $0
    disp[NR] = $1
    pkg[NR] = $2
}
END {
    for (i = 1; i <= n; i++) {
        p = want[i]
        if (p == "") continue
        matched = 0
        for (r = 1; r <= NR; r++) {
            if (pkg[r] == p || disp[r] == p) {
                print rows[r]
                matched = 1
                break
            }
        }
        if (!matched) {
            printf "%s\\t%s\\t\\t\\t\\n", p, p
        }
    }
}
'
"""


def extract_wizard(tmp_path: Path) -> Path:
    dest = tmp_path / "wizard"
    dest.mkdir()
    with tarfile.open(TARBALL) as tar:
        try:
            tar.extractall(dest, filter="data")
        except TypeError:  # Python < 3.11.4
            tar.extractall(dest)
    return dest / "app-wiz4rd-0.1.0"


# Everything the driver needs from a normal system, symlinked into an isolated
# bin dir so PATH holds no yay/pacman of the host's own.
CORE_TOOLS = (
    "awk", "bash", "cat", "date", "dirname", "env", "grep", "mkdir",
    "mktemp", "mv", "nohup", "rm", "sed", "sh", "sleep", "tee", "touch",
    "tr", "wc",
)


@pytest.fixture
def wizard(tmp_path: Path) -> dict:
    root = extract_wizard(tmp_path)
    stub_bin = tmp_path / "bin"
    stub_bin.mkdir()
    for tool in CORE_TOOLS:
        real = shutil.which(tool)
        if real:
            (stub_bin / tool).symlink_to(real)
    (stub_bin / "yay").write_text(YAY_STUB)
    (stub_bin / "ping").write_text(NETWORK_STUB)
    (stub_bin / "getent").write_text(NETWORK_STUB)
    (stub_bin / "pacman").write_text(PACMAN_STUB)
    (stub_bin / "nmtui-connect").write_text(NMTUI_STUB)
    (stub_bin / "fzf").write_text(FZF_STUB)
    for name in ("yay", "ping", "getent", "pacman", "nmtui-connect", "fzf"):
        (stub_bin / name).chmod(0o755)

    # Ensure synthetic package names used across the pending-queue tests exist
    # as real catalog rows so fzf matches them from stdin.
    with (root / "apps.list").open("a") as cat:
        cat.write(
            "\n"
            "DAW|Bitwig|bitwig|Digital audio workstation\n"
            "Audio|Vital|vital|Spectral warping wavetable synth\n"
            "Web|Studio|https://example.com/studio|Web studio launcher\n"
        )

    home = tmp_path / "home"
    home.mkdir()
    return {
        "root": root,
        "script": root / "app-wiz4rd",
        "home": home,
        "online": tmp_path / "online",
        "yay_log": tmp_path / "yay.log",
        "nmtui_log": tmp_path / "nmtui.log",
        "installed_file": tmp_path / "installed",
        "env": {
            "PATH": str(stub_bin),
            "HOME": str(home),
            "LANG": "C.UTF-8",
            "WIZ_ONLINE": str(tmp_path / "online"),
            "WIZ_YAY_LOG": str(tmp_path / "yay.log"),
            "WIZ_PACMAN_LOG": str(tmp_path / "pacman.log"),
            "WIZ_NMTUI_LOG": str(tmp_path / "nmtui.log"),
            "WIZ_INSTALLED_FILE": str(tmp_path / "installed"),
            # The wizard asks "Proceed? [Y/n]" before installing; tests drive it
            # non-interactively (or through a pty), so skip the prompt.
            "SYNTROPIA_WIZARD_ASSUME_YES": "1",
        },
    }


def pending_file(ctx: dict) -> Path:
    return ctx["home"] / ".config" / "syntropia" / "apps-wizard.pending"


def done_marker(ctx: dict) -> Path:
    return ctx["home"] / ".config" / "syntropia" / "apps-wizard.done"


def queued(ctx: dict) -> list:
    path = pending_file(ctx)
    if not path.exists():
        return []
    return [line for line in path.read_text().splitlines() if line]


def run_picker(ctx: dict, selection: str, *args: str) -> subprocess.CompletedProcess:
    """Run the picker path, which needs stdin to be a terminal (autostart).

    The master fd must stay OPEN for the whole run: closing it makes the slave
    hang up, `[[ -t 0 ]]` turns false, and the wizard correctly decides it was
    started detached and relaunches inside a terminal instead. A feeder thread
    keeps newlines coming so the trailing "press Enter" reads finish.
    """
    env = {**ctx["env"], "WIZ_SELECTION": selection}
    master, slave = pty.openpty()
    proc = subprocess.Popen(
        [str(ctx["script"]), "--config", str(ctx["root"] / "apps.list"), *args],
        stdin=slave,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=str(ctx["root"]),
    )
    os.close(slave)

    stop = threading.Event()

    def feed() -> None:
        while not stop.is_set():
            try:
                os.write(master, b"\n")
            except OSError:
                return
            time.sleep(0.05)

    feeder = threading.Thread(target=feed, daemon=True)
    feeder.start()
    try:
        out, err = proc.communicate(timeout=120)
    finally:
        stop.set()
        os.close(master)
    return subprocess.CompletedProcess(proc.args, proc.returncode, out, err)


def test_offline_picks_are_queued_not_lost(wizard: dict) -> None:
    result = run_picker(wizard, "reaper bitwig", "--once")

    assert result.returncode == 0, result.stderr
    assert queued(wizard) == ["reaper", "bitwig"]
    # The wizard ran, but it must NOT consider the job done.
    assert not done_marker(wizard).exists()
    assert "saved and waiting" in result.stdout


def test_resume_installs_the_queue_and_marks_done(wizard: dict) -> None:
    wizard["online"].touch()
    pending_file(wizard).parent.mkdir(parents=True, exist_ok=True)
    pending_file(wizard).write_text("reaper\nbitwig\n")

    result = subprocess.run(
        [str(wizard["script"]), "--resume"],
        capture_output=True,
        text=True,
        env=wizard["env"],
        cwd=str(wizard["root"]),
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    assert queued(wizard) == []
    assert done_marker(wizard).exists()
    log = wizard["yay_log"].read_text()
    assert "-S --noconfirm --needed reaper bitwig" in log


def test_once_runs_again_while_pending(wizard: dict) -> None:
    # A completed wizard with a queue left over must not short-circuit: this is
    # the "first boot was offline" case the user recovers from by logging in.
    wizard["online"].touch()
    done_marker(wizard).parent.mkdir(parents=True, exist_ok=True)
    done_marker(wizard).touch()
    pending_file(wizard).write_text("surge\n")

    result = run_picker(wizard, "vital", "--once")

    assert result.returncode == 0, result.stderr
    assert "Already completed" not in result.stdout
    assert queued(wizard) == []
    log = wizard["yay_log"].read_text()
    assert "surge" in log and "vital" in log


def test_completed_wizard_stays_closed(wizard: dict) -> None:
    done_marker(wizard).parent.mkdir(parents=True, exist_ok=True)
    done_marker(wizard).touch()

    result = subprocess.run(
        [str(wizard["script"]), "--once"],
        capture_output=True,
        text=True,
        env=wizard["env"],
        cwd=str(wizard["root"]),
        timeout=60,
    )

    assert result.returncode == 0
    assert "Already completed" in result.stdout
    assert not wizard["yay_log"].exists()


def test_web_apps_work_offline(wizard: dict) -> None:
    # A web app is only a local launcher — no download, so offline is fine.
    result = run_picker(wizard, "https://example.com/studio", "--once")

    assert result.returncode == 0, result.stderr
    assert queued(wizard) == []
    launchers = list((wizard["home"] / ".local" / "share" / "applications").glob("syntropia-*.desktop"))
    assert len(launchers) == 1
    assert "https://example.com/studio" in launchers[0].read_text()


def test_missing_yay_offline_keeps_the_queue(wizard: dict) -> None:
    (Path(wizard["env"]["PATH"].split(":")[0]) / "yay").unlink()

    result = run_picker(wizard, "reaper", "--once")

    assert result.returncode == 0, result.stderr
    assert queued(wizard) == ["reaper"]
    assert "yay is not installed and there is no internet" in result.stdout


def install_log(ctx: dict) -> Path:
    return ctx["home"] / ".local" / "state" / "app-wiz4rd" / "install.log"


# --- the reported "picked apps, nothing installed" path -------------------

def test_online_picks_install_immediately_and_are_logged(wizard: dict) -> None:
    wizard["online"].touch()

    result = run_picker(wizard, "reaper bitwig", "--once")

    assert result.returncode == 0, result.stderr
    assert "Installing packages: reaper bitwig" in result.stdout
    log = wizard["yay_log"].read_text()
    assert "-S --noconfirm --needed reaper bitwig" in log
    assert queued(wizard) == []
    assert done_marker(wizard).exists()
    # Output survives the window: the same text is on disk.
    trace = install_log(wizard).read_text()
    assert "run mode=once" in trace
    assert "picked: reaper bitwig" in trace
    assert "yay -S --noconfirm --needed reaper bitwig" in trace
    assert "yay: installing" in trace


def test_offline_picker_offers_a_connection_before_app_selection(wizard: dict) -> None:
    result = run_picker(wizard, "reaper", "--once")

    assert result.returncode == 0, result.stderr
    out = result.stdout
    assert "No internet connection." in out
    assert "Connect now" in out
    # The menu comes before the picker (whose stub prints nothing), so the
    # prompt appears even though a pick was made afterwards.
    assert wizard["nmtui_log"].exists(), "nmtui-connect must be offered when offline"
    assert queued(wizard) == ["reaper"]


def test_partial_yay_failure_unqueues_only_installed_picks(wizard: dict) -> None:
    wizard["online"].touch()
    wizard["installed_file"].write_text("reaper\n")
    wizard["env"]["WIZ_YAY_RC"] = "1"

    result = run_picker(wizard, "reaper bitwig", "--once")

    assert result.returncode == 0, result.stderr
    # Batch aborted (reaper landed in the transaction, bitwig did not); the
    # per-package fallback skips installed reaper, solo-installs... fails on
    # bitwig, which stays queued. Nothing installed is ever re-queued.
    log = wizard["yay_log"].read_text()
    assert "yay -S --noconfirm --needed reaper bitwig" in log
    assert "yay -S --noconfirm --needed bitwig\n" in log  # solo retry call
    trace = install_log(wizard).read_text()
    assert "bitwig (solo retry)" in trace
    assert "reaper (solo retry)" not in trace
    assert queued(wizard) == ["bitwig"]
    assert not done_marker(wizard).exists()
    assert "could not install: bitwig" in result.stdout


def test_build_sh_pins_the_vendored_tarball() -> None:
    """build.sh refuses to build on a sha mismatch — keep the pin honest."""
    import re

    build = (REPO / "iso" / "build.sh").read_text()
    pinned = re.search(r'APP_WIZ4RD_SHA256="([0-9a-f]{64})"', build)
    assert pinned, "build.sh must pin the wizard tarball"
    actual = hashlib.sha256(TARBALL.read_bytes()).hexdigest()
    assert actual == pinned.group(1), "regenerate iso/vendor/ and update APP_WIZ4RD_SHA256"
