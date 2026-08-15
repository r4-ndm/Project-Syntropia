"""Packaging lockstep: shipped systemd units must reference real commands.

The syntropia-cli package installs the units in phase1/services/ and the
standalone audit script as /usr/bin/aur-audit. Pin that wiring so a unit
can't drift to a command the package no longer ships (the registry-sync
unit got exactly this bug once — it referenced a command that didn't exist).
"""

from __future__ import annotations

from pathlib import Path

PHASE1 = Path(__file__).resolve().parents[1]
SERVICES = PHASE1 / "services"
CLI_PKGBUILD = PHASE1 / "aur" / "syntropia-cli" / "PKGBUILD"
AUDIT_SCRIPT = PHASE1 / "tools" / "aur_audit.py"

EXPECTED_UNITS = (
    "syntropia-aur-audit.service",
    "syntropia-aur-audit.timer",
)


def test_audit_units_exist():
    for unit in EXPECTED_UNITS:
        assert (SERVICES / unit).is_file(), f"missing unit: {unit}"


def test_audit_service_references_installed_command():
    """The service's ExecStart must point at a path the cli PKGBUILD installs."""
    service = (SERVICES / "syntropia-aur-audit.service").read_text(encoding="utf-8")
    exec_start = [ln.split("=", 1)[1].strip() for ln in service.splitlines()
                  if ln.startswith("ExecStart=")]
    assert len(exec_start) == 1, f"expected one ExecStart, got: {exec_start}"
    binary = exec_start[0].split()[0]
    assert binary == "/usr/bin/aur-audit"
    assert "aur_audit.py" in CLI_PKGBUILD.read_text(encoding="utf-8"), (
        "syntropia-cli PKGBUILD no longer installs the audit script"
    )


def test_audit_script_is_stdlib_only():
    """The audit script must not import third-party modules (it runs as root)."""
    text = AUDIT_SCRIPT.read_text(encoding="utf-8")
    stdlib = {"__future__", "argparse", "json", "os", "re", "subprocess", "sys", "urllib", "pathlib"}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("import ") and not line.startswith("from "):
            continue
        mod = line.split()[1].split(".")[0]
        assert mod in stdlib, f"non-stdlib import in aur_audit.py: {mod}"
