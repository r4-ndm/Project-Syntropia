#!/usr/bin/env python3
"""AUR security audit — cross-check foreign packages against known-compromised lists.

Checks a CachyOS/Arch machine that uses the AUR (via paru/yay/makepkg):

1. Lists foreign packages (``pacman -Qm``).
2. Cross-checks them (exact + suffix-stripped) against the community
   ``aur-malware-check`` compromised-package lists (Atomic Arch campaign and
   related waves).
3. Scans the paru/yay build caches for the campaign's known payload names.
4. Flags any package installed during the known attack windows.
5. Optional (``--commits``): pulls each package's AUR git atom feed to spot
   anomalous recent commits / maintainer changes — the actual attack vector.

Pure matching logic lives in importable functions so tests can exercise it
without network or pacman.

Usage:
    python3 phase1/tools/aur-audit.py            # core checks
    python3 phase1/tools/aur-audit.py --commits  # + AUR commit history scan
    python3 phase1/tools/aur-audit.py --json     # machine-readable report

Exit codes: 0 = no issues found, 1 = issues found, 2 = error.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

# ── Known-compromised lists (community scanner, archlinux/aur mirror) ──────
# Repo: https://github.com/lenucksi/aur-malware-check  (default branch: master)
SCANNER_RAW = "https://raw.githubusercontent.com/lenucksi/aur-malware-check/master/data/campaigns"
COMPROMISED_FILES = (
    "aur-infected/packages.txt",
    "aur-infected/packages-extra.txt",
    "chaos-rat/packages.txt",
    "russian-spam/packages.txt",
)

# The campaign's known payload binary names (Wave 1 + Wave 3) — disguised as
# build tools. Also catches bare *.elf files.
SUSPICIOUS_NAMES = (
    "linter", "hasher", "minifier", "validator",
    "assembler", "optimizer", "*.elf",
)

# Attack windows (UTC) from the public Atomic Arch timeline. Anything installed
# during these deserves extra scrutiny even if not on a list yet.
ATTACK_WINDOWS = (
    ("Wave 1", "2026-06-11", "2026-06-12"),
    ("Wave 2 hardening gap", "2026-07-13", "2026-07-14"),
    ("Wave 3", "2026-07-25", "2026-07-31"),
    ("Write freeze", "2026-08-01", "2026-08-11"),
)

SUFFIX_RE = re.compile(r"-(git|bin|svn|cvs|hg|bzr)$")


# ── Pure logic (testable) ───────────────────────────────────────────────────

def normalize(name: str) -> str:
    """Strip the VCS/binary suffix: ``grayjay-bin`` -> ``grayjay``."""
    return SUFFIX_RE.sub("", name)


def cross_check(installed: list[str], compromised: list[str]) -> dict[str, list[str]]:
    """Return {'exact': [...], 'fuzzy': [...]} matches, both directions clean.

    ``exact`` = package name literally present in a compromised list.
    ``fuzzy`` = present only after suffix normalization (e.g. ``-bin``).
    """
    compromised_set = {n for n in compromised if n}
    installed_set = {n for n in installed if n}
    exact = sorted(installed_set & compromised_set)
    fuzzy = sorted(
        {n for n in installed_set - set(exact)
         if normalize(n) in {normalize(c) for c in compromised_set}}
    )
    return {"exact": exact, "fuzzy": fuzzy}


MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

# pacman -Qi prints e.g. "Thu 11 Jun 2026 12:00:00 UTC" (locale-independent
# weekday/month names, regardless of the system locale).
_PACMAN_DATE_RE = re.compile(r"^\w{3}\s+(\d{1,2})\s+(\w{3})\s+(\d{4})")


def _parse_pacman_date(date_str: str) -> tuple[int, int, int] | None:
    """Parse a pacman -Qi install date into (year, month, day), or None."""
    m = _PACMAN_DATE_RE.match(date_str.strip())
    if not m:
        return None
    day, mon_name, year = int(m.group(1)), m.group(2), int(m.group(3))
    month = MONTHS.get(mon_name)
    if month is None:
        return None
    return year, month, day


def flag_install_windows(installed: dict[str, str]) -> list[tuple[str, str, str]]:
    """Return [(package, window_name, install_date)] for installs inside an attack window.

    ``installed`` maps package name -> install date string as printed by
    ``pacman -Qi`` (e.g. "Sat 08 Aug 2026 09:32:16 BST").
    """
    flagged: list[tuple[str, str, str]] = []
    for pkg, date_str in installed.items():
        parsed = _parse_pacman_date(date_str)
        if parsed is None:
            continue
        for window, start, end in ATTACK_WINDOWS:
            sy, smo, sd = (int(x) for x in start.split("-"))
            ey, emo, ed = (int(x) for x in end.split("-"))
            if (sy, smo, sd) <= parsed <= (ey, emo, ed):
                flagged.append((pkg, window, date_str))
                break
    return flagged


# ── System-facing helpers (not unit-tested) ─────────────────────────────────

def foreign_packages() -> list[str]:
    """Return the name-only list from ``pacman -Qm`` (alphabetical)."""
    proc = subprocess.run(["pacman", "-Qm"], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"pacman -Qm failed: {proc.stderr.strip()}")
    return sorted(line.split()[0] for line in proc.stdout.splitlines() if line.strip())


def install_dates(packages: list[str]) -> dict[str, str]:
    """Map package name -> install date (from pacman -Qi), best effort."""
    dates: dict[str, str] = {}
    for pkg in packages:
        proc = subprocess.run(["pacman", "-Qi", pkg], capture_output=True, text=True)
        if proc.returncode != 0:
            continue
        m = re.search(r"^Install Date\s*: (.+)$", proc.stdout, re.M)
        if m:
            dates[pkg] = m.group(1).strip()
    return dates


def fetch_compromised() -> list[str]:
    """Download all compromised-package lists; union them. Network failure -> []."""
    names: set[str] = set()
    for path in COMPROMISED_FILES:
        url = f"{SCANNER_RAW}/{path}"
        try:
            with urllib.request.urlopen(url, timeout=20) as resp:
                body = resp.read().decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001 — any fetch failure degrades gracefully
            print(f"  ⚠️  could not fetch {url}: {exc}", file=sys.stderr)
            continue
        for line in body.splitlines():
            line = line.strip().split("#")[0].strip()
            if line:
                names.add(line)
    return sorted(names)


def scan_caches() -> list[Path]:
    """Find suspicious-named binaries in ~/.cache/paru and ~/.cache/yay."""
    hits: list[Path] = []
    for cache_dir in (Path.home() / ".cache" / "paru", Path.home() / ".cache" / "yay"):
        if not cache_dir.is_dir():
            continue
        for pattern in SUSPICIOUS_NAMES:
            hits.extend(cache_dir.glob(f"**/{pattern}"))
    return hits


def fetch_commit_info(package: str) -> str:
    """Return the latest AUR git commit (title/author/date) for a package.

    Returns "not on AUR" for packages with no such branch (e.g. CachyOS-repo
    or removed packages), and the raw error text on fetch failure.
    """
    url = f"https://aur.archlinux.org/cgit/aur.git/atom/?h={package}"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            body = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        # 404 = no such branch on the AUR (CachyOS-repo or removed package).
        return "not on AUR" if exc.code == 404 else f"(fetch failed: HTTP {exc.code})"
    except Exception as exc:  # noqa: BLE001
        return f"(fetch failed: {exc})"
    # Atom feed: <title>upgpkg: ...</title> ... <updated>ISO</updated> <name>Author</name>
    titles = re.findall(r"<title>([^<]*)</title>", body)
    updates = re.findall(r"<updated>([^<]*)</updated>", body)
    authors = re.findall(r"<name>([^<]*)</name>", body)
    # The feed's own title is "aur.git, branch <pkg>"; real commits follow it.
    commit_titles = [t for t in titles if not t.startswith("aur.git")]
    if not commit_titles:
        return "not on AUR"
    date = updates[1] if len(updates) > 1 else (updates[0] if updates else "?")
    author = authors[0] if authors else "?"
    return f"{date}  {author}  {commit_titles[0][:60]}"


# ── Report ──────────────────────────────────────────────────────────────────

def run_audit(check_commits: bool, *, quiet: bool = False) -> dict:
    report: dict = {
        "scanned": [],
        "exact_matches": [],
        "fuzzy_matches": [],
        "suspicious_binaries": [],
        "window_flags": [],
        "commits": {},
    }

    def say(msg: str = "") -> None:
        if not quiet:
            print(msg)

    say("== AUR security audit ==")
    installed = foreign_packages()
    report["scanned"] = installed
    say(f"\nForeign packages ({len(installed)}): {', '.join(installed)}")

    say("\n[1/4] Compromised-list cross-check…")
    compromised = fetch_compromised()
    if compromised:
        result = cross_check(installed, compromised)
        report["exact_matches"] = result["exact"]
        report["fuzzy_matches"] = result["fuzzy"]
        say(f"  compared {len(installed)} installed vs {len(compromised)} listed")
        if result["exact"]:
            say(f"  🔴 EXACT MATCHES: {', '.join(result['exact'])}")
        if result["fuzzy"]:
            say(f"  🟠 FUZZY MATCHES: {', '.join(result['fuzzy'])}")
        if not result["exact"] and not result["fuzzy"]:
            say("  ✅ no matches (exact or fuzzy)")
    else:
        say("  ⚠️  could not fetch any compromised lists — skipped (network?)")

    say("\n[2/4] Build-cache scan…")
    hits = scan_caches()
    report["suspicious_binaries"] = [str(p) for p in hits]
    if hits:
        for p in hits:
            say(f"  🔴 suspicious binary: {p}")
    else:
        say("  ✅ no suspicious binaries in ~/.cache/paru or ~/.cache/yay")

    say("\n[3/4] Install-date window check…")
    dates = install_dates(installed)
    flags = flag_install_windows(dates)
    report["window_flags"] = [{"package": p, "window": w, "date": d} for p, w, d in flags]
    if flags:
        for pkg, window, date in flags:
            say(f"  🟠 {pkg} installed {date} — inside {window}")
    else:
        say("  ✅ nothing installed inside the known attack windows")

    if check_commits:
        say("\n[4/4] AUR commit-history scan (slow, one request per package)…")
        for pkg in installed:
            info = fetch_commit_info(pkg)
            report["commits"][pkg] = info
            say(f"  {pkg}: {info}")
    else:
        report["commits"] = {"(skipped)": "pass --commits to scan AUR git history"}

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commits", action="store_true",
                        help="also scan each package's AUR git history (slow)")
    parser.add_argument("--json", action="store_true",
                        help="print the report as JSON instead of prose")
    args = parser.parse_args()

    try:
        report = run_audit(check_commits=args.commits, quiet=args.json)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2))
        return 0 if not (report["exact_matches"] or report["suspicious_binaries"]) else 1

    issues = report["exact_matches"] or report["suspicious_binaries"]
    print()
    if issues:
        print(f"🔴 ISSUES FOUND — review the flagged packages above. "
              f"See https://github.com/lenucksi/aur-malware-check for guidance.")
        return 1
    print("✅ clean — no exact matches, no suspicious binaries. "
          "Lists only cover waves known up to their last update; "
          "if a package was installed during a flagged window, re-check it manually.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
