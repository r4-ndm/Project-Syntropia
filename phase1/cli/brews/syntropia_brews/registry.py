"""Syntropia registry sync — the AUR-style submit flow.

The local registry (``~/.config/syntropia/brews``) is a git clone of the
shared GitHub registry (``r4-ndm/syntropia-brews``). ``syntropia save``
writes into that tree; ``submit_brew`` turns a local brew into a pull
request against the shared registry, exactly like submitting a PKGBUILD
to the AUR.

Only ever touches the registry repository — never other repos.
"""

from __future__ import annotations

import shutil
from subprocess import CompletedProcess
from pathlib import Path

from .brew import BrewError, load_brew
from syntropia.process import run_command

SHARED_REGISTRY_URL = "https://github.com/r4-ndm/syntropia-brews"


class RegistryError(Exception):
    """Raised when the submit flow cannot proceed safely."""


def _check(proc: CompletedProcess, context: str) -> None:
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RegistryError(f"{context}: {detail or 'command failed'}")


def repo_root(registry: Path) -> Path:
    """Return the git work-tree root containing the registry, or raise."""
    proc = run_command(["git", "-C", str(registry), "rev-parse", "--show-toplevel"])
    if proc.returncode != 0:
        raise RegistryError(
            f"{registry} is not inside a git repository — the shared-registry submit "
            f"flow needs the registry to be a clone of {SHARED_REGISTRY_URL}. "
            f"Fix with: git clone {SHARED_REGISTRY_URL} {registry}"
        )
    return Path(proc.stdout.strip())


def require_gh() -> str:
    path = shutil.which("gh")
    if path is None:
        raise RegistryError(
            "'gh' (GitHub CLI) is not installed — install it and run 'gh auth login' "
            "before submitting brews"
        )
    return path


def brew_relpath(root: Path, brew_path: Path) -> str:
    """Path of the brew relative to the repo root (for git add/commit)."""
    try:
        return str(brew_path.resolve().relative_to(root.resolve()))
    except ValueError as exc:
        raise RegistryError(f"{brew_path} is outside the registry repository {root}") from exc


def _exists_on_head(root: Path, rel: str) -> bool:
    proc = run_command(["git", "-C", str(root), "cat-file", "-e", f"HEAD:{rel}"])
    return proc.returncode == 0


def _origin_url(root: Path) -> str | None:
    """URL of the repo's ``origin`` remote, or ``None`` if unset."""
    proc = run_command(["git", "-C", str(root), "remote", "get-url", "origin"])
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def _is_shared_origin(origin: str) -> bool:
    return origin.rstrip("/").rstrip(".git") == SHARED_REGISTRY_URL.rstrip("/").rstrip(".git")


def submit_brew(brew_path: Path, registry: Path, *, base: str = "main") -> str:
    """Open a PR for a local brew against the shared registry.

    Creates a feature branch, commits only the brew file, pushes it, and
    opens a PR with ``gh``. Returns the PR URL.

    Steps (each verified before the next):
    git rev-parse --show-toplevel -> require gh -> branch check ->
    git checkout -b -> git add -> git commit -> git push -u ->
    gh pr create.
    """
    root = repo_root(registry)
    origin = _origin_url(root)
    if origin is None:
        raise RegistryError(
            f"registry repo {root} has no 'origin' remote — add it with: "
            f"git -C {root} remote add origin {SHARED_REGISTRY_URL}"
        )
    if not _is_shared_origin(origin):
        print(
            f"warning: registry origin is '{origin}', expected "
            f"{SHARED_REGISTRY_URL} — double-check before merging"
        )
    gh = require_gh()
    rel = brew_relpath(root, brew_path)
    slug = Path(rel).stem
    branch = f"brews/{slug}"

    exists = run_command(["git", "-C", str(root), "rev-parse", "--verify", f"refs/heads/{branch}"])
    if exists.returncode == 0:
        raise RegistryError(
            f"branch '{branch}' already exists locally — merge or delete it first "
            f"(git -C {root} branch -D {branch})"
        )

    action = "update" if _exists_on_head(root, rel) else "add"
    try:
        brew = load_brew(brew_path)
        summary = f"{brew.name} {brew.version}"
    except BrewError:
        summary = slug

    title = f"brews: {action} {slug}"
    body = (
        f"**{action.title()} `{rel}`** — {summary}.\n\n"
        f"Submitted via `syntropia submit {slug}`.\n\n"
        f"See the [.brew specification](https://github.com/r4-ndm/Project-Syntropia/blob/main/phase1/plan.md)."
    )

    _check(
        run_command(["git", "-C", str(root), "checkout", "-b", branch]),
        f"create branch '{branch}'",
    )
    _check(run_command(["git", "-C", str(root), "add", "--", rel]), f"stage {rel}")
    # Pathspec-limited commit: only the brew can ever be committed, even if
    # other files were pre-staged in the registry tree.
    _check(
        run_command(["git", "-C", str(root), "commit", "-m", title, "--", rel]),
        f"commit {rel}",
    )
    _check(
        run_command(["git", "-C", str(root), "push", "-u", "origin", branch]),
        f"push branch '{branch}'",
    )
    pr = run_command(
        [
            gh,
            "pr",
            "create",
            "--base",
            base,
            "--head",
            branch,
            "--title",
            title,
            "--body",
            body,
        ]
    )
    _check(pr, "open pull request")
    # Best-effort: return the registry to the base branch so it stays
    # pullable; the feature branch persists on origin for the PR.
    restore = run_command(["git", "-C", str(root), "checkout", base])
    if restore.returncode == 0:
        run_command(["git", "-C", str(root), "branch", "-D", branch])
    else:
        print(
            f"warning: could not switch the registry back to '{base}' — "
            f"it is on branch '{branch}' (git -C {root} checkout {base})"
        )
    out = pr.stdout.strip()
    url = next((line for line in out.splitlines() if line.startswith("https://")), out)
    return url
