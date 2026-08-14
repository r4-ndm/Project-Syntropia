"""syntropia update — pull the latest Syntropia packages + brews and re-apply branding.

Detects how syntropia was installed and updates from the appropriate
source, then re-runs the transform to apply any updated branding assets
or configs. For pacman-tracked installs this runs ``paru -Syu``
(``yay -Syu`` fallback) — paru updates all three packages
(``syntropia-cli``, ``syntropia-brews``, ``syntropia``), and
``syntropia update`` layers the brew registry pull + branding re-apply
on top.

Install sources detected (in priority order):
* **aur** — installed via pacman (``pacman -Q syntropia``), whether
  from the AUR, a local ``makepkg -si``, or a custom repo. Runs
  ``paru -Syu`` to refresh pacman and the syntropia package itself.
* **git** — cloned via ``install-syntropia.sh`` or manually to
  ``~/syntropia`` (or ``$SYNTROPIA_SRC``). Runs ``git pull``.
* **pip** — installed via ``pip install .`` or ``pip install syntropia``.
  Rebuilds from the repo if a git clone exists alongside.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
from pathlib import Path

from syntropia.process import run_command


class UpdateError(Exception):
    """An update step failed."""


def _repo_root() -> Path | None:
    """Find the Project-Syntropia git clone, if any.

    Checks, in order:
    1. $SYNTROPIA_SRC (set by install-syntropia.sh users)
    2. ~/syntropia (the one-liner default)
    3. Walk up from this module's install location to find a git dir.
    """
    env = os.environ.get("SYNTROPIA_SRC")
    if env:
        candidate = Path(env).expanduser()
        if (candidate / ".git").is_dir():
            return candidate

    default = Path.home() / "syntropia"
    if (default / ".git").is_dir():
        return default

    # Heuristic: if the running binary is inside a git worktree, use that.
    # This catches editable pip installs and manual PYTHONPATH setups.
    here = Path(__file__).resolve().parent
    for parent in [here] + list(here.parents):
        if (parent / ".git").is_dir():
            return parent

    return None


def detect_source() -> str:
    """Return the install source: "aur", "git", "pip", or "unknown".

    "aur" means pacman tracks the package — it could be from the AUR,
    a local ``makepkg -si``, or a custom repo. We can't distinguish.
    """
    # 1. pacman-installed? (AUR, local PKGBUILD, or custom repo —
    #    pacman tracks it either way)
    if shutil.which("pacman"):
        result = run_command(["pacman", "-Q", "syntropia"])
        if result.returncode == 0:
            return "aur"

    # 2. Git clone?
    if _repo_root() is not None:
        return "git"

    # 3. Pip-installed?
    result = run_command(["pip", "show", "syntropia"])
    if result.returncode == 0:
        return "pip"

    return "unknown"


def pull_git(repo: Path) -> tuple[bool, str]:
    """Pull the latest from origin/main. Returns (updated, message)."""
    if not (repo / ".git").is_dir():
        raise UpdateError(f"{repo} is not a git repository")

    # Capture current HEAD so we can report what changed.
    before = run_command(["git", "rev-parse", "HEAD"], cwd=repo)
    if before.returncode != 0:
        raise UpdateError(f"git rev-parse failed in {repo}: {before.stderr.strip()}")

    fetch = run_command(["git", "fetch", "--quiet", "origin"], cwd=repo)
    if fetch.returncode != 0:
        raise UpdateError(f"git fetch failed in {repo}: {fetch.stderr.strip()}")

    pull = run_command(
        ["git", "pull", "--quiet", "--ff-only", "origin", "main"], cwd=repo
    )
    if pull.returncode != 0:
        raise UpdateError(f"git pull failed in {repo}: {pull.stderr.strip()}")

    after = run_command(["git", "rev-parse", "HEAD"], cwd=repo)
    if after.returncode != 0:
        raise UpdateError(f"git rev-parse failed in {repo}: {after.stderr.strip()}")

    if before.stdout.strip() == after.stdout.strip():
        return False, "already up to date"

    # Show what changed.
    log = run_command(
        ["git", "log", "--oneline", f"{before.stdout.strip()}..{after.stdout.strip()}"],
        cwd=repo,
    )
    return True, log.stdout.strip() or "(no commit messages)"


def pull_brews() -> tuple[bool, str]:
    """Pull the latest brews from the shared GitHub registry.

    Returns (updated, message). Gracefully handles the case where the
    registry hasn't been cloned yet.
    """
    registry = Path.home() / ".config" / "syntropia" / "brews"
    if not (registry / ".git").is_dir():
        return False, "brew registry not cloned yet — run 'syntropia save' first"
    return pull_git(registry)


TRANSFORM_BRANDING_DIR = "/usr/share/syntropia/branding"

AUR_HELPERS = ("paru", "yay")


def _update_via_pacman(check: bool = False) -> None:
    """Update the system + syntropia through an AUR helper.

    ``paru -Syu`` (falling back to yay) refreshes pacman and pulls the
    latest syntropia package from the AUR — once syntropia is on the
    AUR this is the whole CLI-update story. The terminal is inherited
    so paru shows its package diffs and sudo can prompt for a password.

    A non-zero exit (e.g. the user aborted the update) is reported but
    does not abort the rest of ``syntropia update`` — the brew pull and
    transform re-run stay safe and useful regardless.
    """
    helper = next((h for h in AUR_HELPERS if shutil.which(h)), None)
    if helper is None:
        print(
            "  ⚠️  no AUR helper found (paru/yay) — install one and re-run "
            "'syntropia update', or update manually: "
            "sudo pacman -Syu && sudo syntropia transform --yes"
        )
        return
    if check:
        print(f"  [--check] would run: {helper} -Syu")
        return
    print(f"  🔄 Running {helper} -Syu (this also updates the syntropia packages)...")
    result = subprocess.run([helper, "-Syu"])
    if result.returncode != 0:
        print(
            f"  ⚠️  {helper} -Syu exited with {result.returncode} — "
            "continuing with brews + transform"
        )
    else:
        print("  ✅ system packages updated (incl. syntropia packages)")


def _rerun_transform(check: bool = False) -> None:
    """Re-apply the transform with root privileges.

    Runs a fresh ``syntropia transform --yes`` under sudo so that a
    just-updated CLI executes its own new transform code, the real
    user's home is resolved (transform.py reads SUDO_USER), and root
    failures surface as a clean UpdateError instead of a traceback.
    When already root, run in-process to avoid a pointless sudo hop.

    The subprocess inherits the terminal (no output capture) so the
    transform's APPLY logs are visible live, and sudo can prompt for
    a password on the tty.
    """
    if check:
        print("  [--check] would run: sudo syntropia transform --yes")
        return

    if os.geteuid() == 0:
        from .transform import run_transform as _run_transform

        _run_transform(check=False, yes=True, branding_dir=TRANSFORM_BRANDING_DIR)
        return

    binary = shutil.which("syntropia")
    if binary is None:
        raise UpdateError(
            "cannot find the syntropia binary to re-run the transform — "
            "run: sudo syntropia transform --yes"
        )
    if shutil.which("sudo") is None:
        raise UpdateError(
            "transform needs root privileges but sudo is not available — "
            "run: sudo syntropia transform --yes"
        )

    result = subprocess.run(["sudo", binary, "transform", "--yes"])
    if result.returncode != 0:
        raise UpdateError(
            f"transform re-run failed (exit {result.returncode}) — see output above"
        )


def changelog(repo: Path, n: int = 5) -> str:
    """Show the last n commits in the repo."""
    if not (repo / ".git").is_dir():
        return ""
    result = run_command(
        ["git", "log", "--oneline", f"-{n}"], cwd=repo
    )
    return result.stdout.strip()


def run_update(*, check: bool = False) -> None:
    """Orchestrate the full update flow.

    1. Detect the install source and pull latest CLI.
    2. Pull the brews registry.
    3. Re-run the transform to apply updated branding/configs.
    """
    source = detect_source()
    updated_any = False

    # ── Step 1: pull the CLI / core ──────────────────────────────────
    if source == "aur":
        print("  📦 Installed via: pacman (syntropia packages tracked by pacman — AUR or local package)")
        _update_via_pacman(check=check)
        # Once syntropia is on the AUR, paru -Syu is the whole CLI-update
        # story; we still pull brews and re-run the transform below.
    elif source == "git":
        repo = _repo_root()
        if repo is None:
            raise UpdateError(
                "detected git install but cannot find the repo — is $SYNTROPIA_SRC set?"
            )
        print(f"  📦 Installed via: git clone ({repo})")
        if check:
            print(f"  [--check] would git pull in {repo}")
        else:
            updated, msg = pull_git(repo)
            if updated:
                print(f"  ✅ pulled latest:\n{msg}")
                updated_any = True
            else:
                print(f"  ✅ {msg}")
    elif source == "pip":
        print("  📦 Installed via: pip")
        if check:
            print("  [--check] would pip install --upgrade the three packages from the repo")
        # Pip-installed: try to rebuild all three packages from the repo if
        # one exists alongside, otherwise tell the user.
        repo = _repo_root()
        if repo is not None:
            print(f"  (found repo at {repo} — rebuilding from source)")
            if not check:
                result = run_command(
                    [
                        "pip", "install", "--upgrade", "--no-deps",
                        str(repo / "phase1" / "cli"),
                        str(repo / "phase1" / "cli" / "brews"),
                        str(repo / "phase1" / "cli" / "transform"),
                    ]
                )
                if result.returncode != 0:
                    raise UpdateError(f"pip install failed: {result.stderr.strip()}")
                updated_any = True
        else:
            print("  no local repo found — run: pip install --upgrade syntropia syntropia-cli syntropia-brews")
    else:
        print("  ⚠️  Unknown install source — nothing to pull.")
        print("  If you cloned the repo, set $SYNTROPIA_SRC and try again.")

    # ── Step 2: pull the brew registry (only when brews is installed) ──
    print()
    if importlib.util.find_spec("syntropia_brews") is None:
        print("  🍺 syntropia-brews not installed — skipping the brew registry pull")
    elif check:
        print("  [--check] would pull the brew registry")
    else:
        updated, msg = pull_brews()
        if updated:
            print(f"  🍺 brews updated:\n{msg}")
            updated_any = True
        else:
            print(f"  🍺 brews: {msg}")

    # ── Step 3: re-apply the transform ───────────────────────────────
    print()
    if updated_any or source == "aur":
        print("  🔄 Re-applying transform to pick up any updated assets...")
        _rerun_transform(check=check)
    else:
        print("  ✅ Nothing to update — syntropia and brews are current.")
