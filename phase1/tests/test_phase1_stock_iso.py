"""Tests for phase 1 finding mkarchiso's output (iso/lib/find-built-iso.sh).

Phase 1 used to predict the stock ISO's name: mkarchiso writes
cachyos-<iso_version>-x86_64.iso, build.sh computed ISO_DATE=today and then
renamed $OUT_DIR/cachyos-<today>-x86_64.iso. On 2026-10-21 that broke a full
build: mkarchiso took <iso_version> from <work-dir>/build_date (a file pinned by
the first build in that work dir), produced cachyos-2026.08.12-x86_64.iso, and
the wrapper died with "did not produce expected output".

So the contract tested here is:

* the produced ISO is selected by mtime, newest first, and never by date;
* a leftover ISO from an earlier run (older than the build's start time) is not
  mistaken for this run's output;
* "nothing was produced" is a loud, explained failure;
* build.sh really uses this helper and really re-assembles the ISO on every
  run (its assembly markers are cleared), driven end-to-end with a stubbed
  `mkarchiso`.
"""

import hashlib
import os
import subprocess
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ISO_DIR = REPO / "iso"
HELPER = ISO_DIR / "lib" / "find-built-iso.sh"
BUILD = ISO_DIR / "build.sh"

BASE_ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}


def make_iso(directory: Path, name: str, age_seconds: int = 0) -> Path:
    """Create a sparse stand-in ISO, `age_seconds` in the past."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(b"\0" * 2048)
    stamp = int(time.time()) - age_seconds
    os.utime(path, (stamp, stamp))
    return path


def run_helper(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(HELPER), *args], capture_output=True, text=True, env=BASE_ENV, timeout=60
    )


# --- selecting the produced ISO ------------------------------------------

def test_newest_matching_iso_wins(tmp_path: Path) -> None:
    old = make_iso(tmp_path, "cachyos-2026.08.12-x86_64.iso", age_seconds=3600)
    new = make_iso(tmp_path, "cachyos-2026.10.21-x86_64.iso", age_seconds=0)

    result = run_helper(str(tmp_path))

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(new)
    assert result.stdout.strip() != str(old)


def test_only_cachyos_x86_64_isos_count(tmp_path: Path) -> None:
    wanted = make_iso(tmp_path, "cachyos-2026.08.12-x86_64.iso")
    make_iso(tmp_path, "syntropia-2026.10.21-x86_64-stock.iso")
    make_iso(tmp_path, "cachyos-2026.08.12-i686.iso")
    make_iso(tmp_path, "cachyos-bootstrap-2026.08.12-x86_64.tar")
    (tmp_path / "cachyos-2026.09.01-x86_64.iso.part").write_bytes(b"x")

    result = run_helper(str(tmp_path))

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(wanted)


def test_directory_entries_are_not_isos(tmp_path: Path) -> None:
    (tmp_path / "cachyos-2026.08.12-x86_64.iso").mkdir()

    result = run_helper(str(tmp_path))

    assert result.returncode == 1
    assert "no cachyos-*-x86_64.iso" in result.stderr


def test_selection_is_deterministic_for_equal_mtimes(tmp_path: Path) -> None:
    stamp = int(time.time()) - 60
    for name in ("cachyos-2026.08.12-x86_64.iso", "cachyos-2026.09.01-x86_64.iso"):
        path = make_iso(tmp_path, name)
        os.utime(path, (stamp, stamp))

    first = run_helper(str(tmp_path))
    second = run_helper(str(tmp_path))

    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout


# --- --since (ignore leftovers) ------------------------------------------

def test_since_ignores_an_older_leftover(tmp_path: Path) -> None:
    leftover = make_iso(tmp_path, "cachyos-2026.08.12-x86_64.iso", age_seconds=600)
    run_start = int(time.time()) - 60  # started after the leftover was written
    produced = make_iso(tmp_path, "cachyos-2026.10.21-x86_64.iso")

    result = run_helper(str(tmp_path), "--since", str(run_start))

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(produced)
    assert result.stdout.strip() != str(leftover)


def test_since_fails_when_only_a_leftover_exists(tmp_path: Path) -> None:
    leftover = make_iso(tmp_path, "cachyos-2026.08.12-x86_64.iso", age_seconds=600)
    run_start = int(time.time()) - 60

    result = run_helper(str(tmp_path), "--since", str(run_start))

    assert result.returncode == 1
    assert result.stdout == ""
    assert "was written at or after" in result.stderr
    # The leftover is named, so "mkarchiso skipped its work" is diagnosable.
    assert str(leftover) in result.stderr


def test_since_accepts_a_file_written_in_the_same_second(tmp_path: Path) -> None:
    now = int(time.time())
    iso = make_iso(tmp_path, "cachyos-2026.08.12-x86_64.iso")
    os.utime(iso, (now, now))

    result = run_helper(str(tmp_path), "--since", str(now))

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(iso)


def test_empty_output_dir_is_a_clean_failure(tmp_path: Path) -> None:
    result = run_helper(str(tmp_path))

    assert result.returncode == 1
    assert result.stdout == ""
    assert "no cachyos-*-x86_64.iso" in result.stderr


# --- invocation -----------------------------------------------------------

def test_no_arguments_is_a_usage_error() -> None:
    result = subprocess.run(
        [str(HELPER)], capture_output=True, text=True, env=BASE_ENV, timeout=30
    )
    assert result.returncode == 2
    assert "usage:" in result.stderr


def test_non_numeric_since_is_a_usage_error(tmp_path: Path) -> None:
    make_iso(tmp_path, "cachyos-2026.08.12-x86_64.iso")
    result = run_helper(str(tmp_path), "--since", "yesterday")
    assert result.returncode == 2
    assert "--since needs a whole number" in result.stderr


def test_missing_out_dir_is_a_usage_error(tmp_path: Path) -> None:
    result = run_helper(str(tmp_path / "nope"))
    assert result.returncode == 2
    assert "is not a directory" in result.stderr


def test_unknown_argument_is_a_usage_error(tmp_path: Path) -> None:
    result = run_helper(str(tmp_path), "--newest")
    assert result.returncode == 2
    assert "unexpected argument" in result.stderr


def test_helper_is_executable() -> None:
    assert HELPER.is_file()
    assert HELPER.stat().st_mode & 0o111


# --- build.sh wiring ------------------------------------------------------

def phase1_block() -> str:
    """The real cache-invalidation / assembly / rename part of phase 1."""
    src = BUILD.read_text()
    start = src.index('    local patch_stamp="$WORK_DIR/mkarchiso-work/syntropia-patches.sha256"')
    end_marker = 'ok "Phase 1 complete:'
    end = src.index(end_marker, start)
    end = src.index("\n", end) + 1
    return src[start:end]


PROFILE_FILES = (
    ("packages.x86_64", "base\nlimine\n"),
    ("pacman.conf", "[options]\n"),
    ("profiledef.sh", 'iso_name="cachyos"\n'),
)


def profile_hash(profile: Path) -> str:
    """The same value build.sh stamps: sha256 of `sha256sum <inputs>`."""
    sums = "".join(
        f"{hashlib.sha256((profile / name).read_bytes()).hexdigest()}  {name}\n"
        for name, _ in PROFILE_FILES
    )
    return hashlib.sha256(sums.encode()).hexdigest()


def run_phase1_block(
    tmp_path: Path, produced_name: str | None, *, cache_valid: bool = False
) -> subprocess.CompletedProcess:
    """Execute build.sh's real block with `mkarchiso` stubbed out.

    produced_name=None makes the stub behave like mkarchiso skipping all its
    work (markers present, nothing written).
    """
    profile = tmp_path / "profile"
    profile.mkdir(exist_ok=True)
    for name, body in PROFILE_FILES:
        (profile / name).write_text(body)
    if cache_valid:
        work = tmp_path / "work" / "mkarchiso-work"
        work.mkdir(parents=True, exist_ok=True)
        (work / "syntropia-patches.sha256").write_text(profile_hash(profile) + "\n")

    script = (
        "set -euo pipefail\n"
        f'SCRIPT_DIR="{ISO_DIR}"\n'
        f'WORK_DIR="{tmp_path}/work"\n'
        f'OUT_DIR="{tmp_path}/out"\n'
        f'CACHYOS_PROFILE_DIR="{profile}"\n'
        'ISO_NAME="syntropia-2026.10.21-x86_64"\n'
        f'PRODUCED="{produced_name or ""}"\n'
        'info() { echo "INFO: $*"; }\n'
        'ok()   { echo "OK: $*"; }\n'
        'warn() { echo "WARN: $*"; }\n'
        'err()  { echo "ERR: $*" >&2; exit 9; }\n'
        'mkarchiso() {\n'
        '    mkdir -p "$OUT_DIR"\n'
        '    [[ -z "$PRODUCED" ]] && return 0\n'
        '    printf "iso" > "$OUT_DIR/$PRODUCED"\n'
        '}\n'
        "phase1_tail() {\n"
        + phase1_block()
        + "}\n"
        'cd "$CACHYOS_PROFILE_DIR"\n'
        "phase1_tail\n"
    )
    return subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, env=BASE_ENV, timeout=120
    )


def test_build_sh_renames_the_iso_mkarchiso_actually_wrote(tmp_path: Path) -> None:
    # The 2026-10-21 failure: mkarchiso stamps a months-old version.
    result = run_phase1_block(tmp_path, "cachyos-2026.08.12-x86_64.iso")

    assert result.returncode == 0, result.stderr
    out = tmp_path / "out"
    assert (out / "syntropia-2026.10.21-x86_64-stock.iso").read_text() == "iso"
    assert not (out / "cachyos-2026.08.12-x86_64.iso").exists()
    # The log has to say where the file came from, or the rename hides a bug.
    assert "from cachyos-2026.08.12-x86_64.iso" in result.stdout


def test_build_sh_fails_when_no_new_iso_appears(tmp_path: Path) -> None:
    result = run_phase1_block(tmp_path, None)

    assert result.returncode == 9
    assert "mkarchiso produced no new ISO" in result.stderr


def test_build_sh_does_not_rename_a_leftover_iso(tmp_path: Path) -> None:
    out = tmp_path / "out"
    leftover = make_iso(out, "cachyos-2026.08.12-x86_64.iso", age_seconds=600)

    result = run_phase1_block(tmp_path, None)

    assert result.returncode == 9
    assert leftover.exists()  # untouched: it is not this run's output
    assert not (out / "syntropia-2026.10.21-x86_64-stock.iso").exists()
    assert "cachyos-2026.08.12-x86_64.iso" in result.stderr


def test_build_sh_clears_the_assembly_markers_so_the_iso_rebuilds(tmp_path: Path) -> None:
    work = tmp_path / "work" / "mkarchiso-work"
    work.mkdir(parents=True)
    kept = work / "base._mkairootfs_squashfs"  # expensive step, must stay cached
    for name in ("build._build_buildmode_iso", "iso._build_iso_image"):
        (work / name).write_text("")
    kept.write_text("")

    result = run_phase1_block(
            tmp_path, "cachyos-2026.10.21-x86_64.iso", cache_valid=True
        )

    assert result.returncode == 0, result.stderr
    assert not (work / "build._build_buildmode_iso").exists()
    assert not (work / "iso._build_iso_image").exists()
    assert kept.exists()
    assert "Clearing ISO-assembly marker" in result.stdout


def test_stale_rootfs_cache_is_discarded_when_the_profile_changed(tmp_path: Path) -> None:
    work = tmp_path / "work" / "mkarchiso-work"
    base_markers = [work / "base._make_packages", work / "base._mkairootfs_squashfs"]
    for path in base_markers:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("")
    cached_rootfs = work / "x86_64" / "airootfs" / "usr"
    cached_rootfs.mkdir(parents=True)
    cached_sfs = work / "iso" / "arch" / "x86_64" / "airootfs.sfs"
    cached_sfs.parent.mkdir(parents=True)
    cached_sfs.write_bytes(b"old-squashfs")
    (work / "syntropia-patches.sha256").write_text("stalehash\n")

    result = run_phase1_block(tmp_path, "cachyos-2026.08.12-x86_64.iso")

    assert result.returncode == 0, result.stderr
    # The Aug-12 problem: cached rootfs/squashfs reused after the package list
    # gained limine, so the ISO shipped without it.
    assert not any(path.exists() for path in base_markers)
    assert not (work / "x86_64" / "airootfs").exists()
    assert not (work / "iso").exists()
    assert "discarding the cached rootfs" in result.stderr + result.stdout


def test_matching_profile_stamp_keeps_the_rootfs_cache(tmp_path: Path) -> None:
    # First run stamps the work dir; a second run with the same profile must
    # not throw away the expensive pacstrap/squashfs steps.
    assert run_phase1_block(tmp_path, "cachyos-2026.08.12-x86_64.iso").returncode == 0
    work = tmp_path / "work" / "mkarchiso-work"
    squashfs_marker = work / "base._mkairootfs_squashfs"
    squashfs_marker.write_text("")

    result = run_phase1_block(tmp_path, "cachyos-2026.08.12-x86_64.iso")

    assert result.returncode == 0, result.stderr
    assert squashfs_marker.exists()
    assert "discarding the cached rootfs" not in result.stdout + result.stderr


def test_patch_stamp_is_only_written_after_a_successful_build(tmp_path: Path) -> None:
    assert run_phase1_block(tmp_path, None).returncode == 9
    stamp = tmp_path / "work" / "mkarchiso-work" / "syntropia-patches.sha256"
    assert not stamp.exists()

    assert run_phase1_block(tmp_path, "cachyos-2026.08.12-x86_64.iso").returncode == 0
    assert len(stamp.read_text().strip()) == 64


def test_phase1_no_longer_predicts_the_iso_name() -> None:
    src = BUILD.read_text()
    assert "cachyos-${ISO_DATE}" not in src
    assert "did not produce expected output" not in src
    helper_call = '"$SCRIPT_DIR/lib/find-built-iso.sh" "$OUT_DIR" --since "$run_started_at"'
    assert helper_call in src
    # The run start is taken before mkarchiso runs, and the helper call after.
    assert src.index("run_started_at=$(date +%s)") < src.index("mkarchiso -v")
    assert src.index("mkarchiso -v") < src.index(helper_call)
