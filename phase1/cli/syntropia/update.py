"""syntropia update — pull latest CLI + brews and re-apply branding.

Detects how syntropia was installed and updates from the appropriate
source, then re-runs the transform to apply any updated branding assets
or configs. The ``yay -Syu`` equivalent for the Syntropia layer.

Install sources detected (in priority order):
* **aur** — installed via pacman (``pacman -Q syntropia``), whether
  from the AUR, a local ``makepkg -si``, or a custom repo. Tells the
  user to run ``yay -Syu`` (we can't call pacman safely from here).
* **git** — cloned via ``install-syntropia.sh`` or manually to
  ``~/syntropia`` (or ``$SYNTROPIA_SRC``). Runs ``git pull``.
* **pip** — installed via ``pip install .`` or ``pip install syntropia``.
  Rebuilds from the repo if a git clone exists alongside.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


class UpdateError(Exception):
    """An update step failed."""


def run_command(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)


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
        print("  📦 Installed via: pacman (local package)")
        print("  Run this to update: yay -Syu   (or pacman -Syu)")
        print("  (Once on the AUR, this detects the same way — pacman tracks it either way.)")
        # Pacman updates are handled by the user's normal workflow;
        # we still pull brews and re-transform below.
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
            print("  [--check] would pip install --upgrade syntropia")
        # Pip-installed: try to rebuild from the repo if one exists
        # alongside, otherwise tell the user.
        repo = _repo_root()
        if repo is not None:
            print(f"  (found repo at {repo} — rebuilding from source)")
            if not check:
                result = run_command(
                    ["pip", "install", "--upgrade", "--no-deps", str(repo / "phase1" / "cli")]
                )
                if result.returncode != 0:
                    raise UpdateError(f"pip install failed: {result.stderr.strip()}")
                updated_any = True
        else:
            print("  no local repo found — run: pip install --upgrade syntropia")
    else:
        print("  ⚠️  Unknown install source — nothing to pull.")
        print("  If you cloned the repo, set $SYNTROPIA_SRC and try again.")

    # ── Step 2: pull the brew registry ───────────────────────────────
    print()
    if check:
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
        if check:
            print("  [--check] would run: sudo syntropia transform --yes")
        else:
            # We import lazily so the module is importable without root.
            from .transform import run_transform as _run_transform

            _run_transform(check=False, yes=True, branding_dir="/usr/share/syntropia/branding")
    else:
        print("  ✅ Nothing to update — syntropia and brews are current.")
