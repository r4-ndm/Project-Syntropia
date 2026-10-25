#!/usr/bin/env python3
"""Patch and validate the ISO's bootloader configs (build.sh phase 2).

Why this exists
---------------
Phase 2 rewrites the stock ISO's GRUB and syslinux menus so the live medium
boots with the Syntropia kernel arguments. Two things went wrong when that was
done with a pile of `sed` calls:

1. The default entry blacklisted no NVIDIA module, so pre-Turing cards loaded
   `nvidia_drm` (no support for them) and the DRM awaiter target timed out.
   The live medium needs `module_blacklist=nvidia,...` on the default entry and
   an explicit NVIDIA-Open entry for Turing+ cards, which DO want the open
   module (and therefore must not carry that blacklist).
2. A broken rewrite closed every menuentry with `}}`. GRUB's own lexer rejects
   that (`script/lexer.c:grub_script_yyerror:352:syntax error. Incorrect
   command.`) and falls back to a menu whose entries are unusable — but
   `grub-script-check` reports nothing, so the bug only showed up when the ISO
   was dd'd to a USB stick and booted as a raw disk. Hence the explicit
   `check` mode below: it fails the build on `}}` closers and on any menuentry
   that is not closed exactly once.

Subcommands
-----------
    patch-grub <grub.cfg>              rewrite entries, add the NVIDIA entry
    patch-syslinux <archiso_sys-linux.cfg>   same, for the BIOS menu
    check <file-or-dir>...             fail on `}}` / unbalanced menuentry

`patch-*` are idempotent: running them twice produces the same file, which is
what phase 2 needs after a killed run.

Runs as root from inside the remaster dir (build.sh cds there); imports only
the standard library.
"""

import re
import sys
from pathlib import Path

# Kernel arguments, in the order the reference (shipped) grub.cfg has them.
# `nvidia` and friends are blacklisted by DEFAULT because the open module does
# not support pre-Turing cards, and loading it there leaves the machine without
# a DRM device; those cards belong on nouveau.
NVIDIA_BLACKLIST = "nvidia,nvidia_modeset,nvidia_uvm,nvidia_drm"
DEFAULT_BLACKLIST = NVIDIA_BLACKLIST + ",pcspkr"
# The NVIDIA-Open entry is for Turing and newer: no nvidia blacklist, and no
# `nouveau.modeset=1` either — nouveau and nvidia-open compete for the same
# device, so the entry that wants nvidia-open must not ask for nouveau.
OPEN_BLACKLIST = "pcspkr"

DEFAULT_ID = "cachyos"
LTS_ID = "cachyos-lts"
OPEN_ID = "cachyos-nvidia"
FALLBACK_ID = "cachyos-fallback"

GRUB_TITLE = "Syntropia (NVIDIA Open / Turing+)"
SYSLINUX_TITLE = "Syntropia (NVIDIA Open / Turing+, BIOS)"
OPEN_HELP = "Boot the Syntropia install medium with NVIDIA Open drivers for Turing+ GPUs."

MENUENTRY_RE = re.compile(r"^\s*menuentry\b")
MENUENTRY_ID_RE = re.compile(r"--id\s+'([^']*)'|--id\s+\"([^\"]*)\"|--id\s+(\S+)")


# ── GRUB ───────────────────────────────────────────────────────────────────

def normalise_brace(line: str) -> str:
    """Turn a `}}` closer into a single `}`.

    Only lines whose whole content is closing braces are touched, so the
    rewriter can never eat a brace that is part of a command.
    """
    match = re.match(r"^(\s*)\}+\s*$", line)
    if match and line.strip() != "}":
        return match.group(1) + "}"
    return line


def entry_blocks(lines: list[str]) -> list[tuple[int, int, str | None]]:
    """Return (start, end, id) for every menuentry block, inclusive indices."""
    blocks: list[tuple[int, int, str | None]] = []
    depth = 0
    start = None
    entry_id = None
    for index, line in enumerate(lines):
        if depth == 0:
            if MENUENTRY_RE.match(line):
                start = index
                entry_id = _menuentry_id(line)
                depth = line.count("{") - line.count("}")
                if depth <= 0:  # single-line entry (not produced by archiso)
                    blocks.append((start, index, entry_id))
                    start, depth, entry_id = None, 0, None
            continue
        depth += line.count("{") - line.count("}")
        if depth <= 0:
            blocks.append((start, index, entry_id))
            start, depth, entry_id = None, 0, None
    return blocks


def _menuentry_id(line: str) -> str | None:
    match = MENUENTRY_ID_RE.search(line)
    if not match:
        return None
    return next(group for group in match.groups() if group is not None)


def _kernel_line(lines: list[str], start: int, end: int) -> int | None:
    for index in range(start, end + 1):
        if re.match(r"^\s*linux\s", lines[index]):
            return index
    return None


def _set_module_blacklist(line: str, value: str) -> str:
    """Replace the module_blacklist token in place, or append it."""
    tokens = line.split()
    for index, token in enumerate(tokens):
        if token.startswith(("module_blacklist=", "modprobe.blacklist=")):
            tokens[index] = "module_blacklist=" + value
            break
    else:
        tokens.append("module_blacklist=" + value)
    return _indent(line) + " ".join(tokens)


def _set_nouveau_modeset(line: str, enabled: bool) -> str:
    tokens = [token for token in line.split() if not token.startswith("nouveau.modeset=")]
    if enabled:
        tokens.append("nouveau.modeset=1")
    return _indent(line) + " ".join(tokens)


def _indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


def _set_title(line: str, title: str) -> str:
    return re.sub(r'menuentry\s+"[^"]*"', f'menuentry "{title}"', line, count=1)


def _set_id(line: str, entry_id: str) -> str:
    replaced = MENUENTRY_ID_RE.sub(f"--id '{entry_id}'", line, count=1)
    if replaced == line:  # entry had no --id: add one before the block opener
        replaced = line.replace("{", f"--id '{entry_id}' {{", 1)
    return replaced


def _set_kernel_args(lines: list[str], start: int, end: int, *,
                     blacklist: str, nouveau: bool) -> None:
    index = _kernel_line(lines, start, end)
    if index is None:
        raise SystemExit(f"menuentry at line {start + 1} has no linux line")
    line = _set_module_blacklist(lines[index], blacklist)
    lines[index] = _set_nouveau_modeset(line, nouveau)


def patch_grub(path: Path) -> None:
    lines = [normalise_brace(line) for line in path.read_text().splitlines()]
    blocks = {entry_id: (start, end) for start, end, entry_id in entry_blocks(lines)}

    if DEFAULT_ID not in blocks:
        raise SystemExit(f"{path}: no menuentry with --id '{DEFAULT_ID}' found")

    # The default and LTS entries run on every machine, so they get the full
    # NVIDIA blacklist plus nouveau KMS; the nomodeset fallback is left exactly
    # as shipped (it already blacklists nvidia and sets nomodeset).
    for entry_id in (DEFAULT_ID, LTS_ID):
        if entry_id in blocks:
            _set_kernel_args(lines, *blocks[entry_id],
                             blacklist=DEFAULT_BLACKLIST, nouveau=True)

    default_start, default_end = blocks[DEFAULT_ID]
    nvidia_block = _nvidia_menuentry(lines[default_start:default_end + 1])

    if OPEN_ID in blocks:
        start, end = blocks[OPEN_ID]
        lines[start:end + 1] = nvidia_block
    else:
        # Right after the default entry: the NVIDIA-Open option is the one a
        # Turing+ owner picks instead of the default, so keep them adjacent.
        lines[default_end + 1:default_end + 1] = [""] + nvidia_block

    path.write_text("\n".join(lines) + "\n")


def _nvidia_menuentry(block: list[str]) -> list[str]:
    """Derive the NVIDIA-Open entry from the already-patched default entry."""
    derived = list(block)
    derived[0] = _set_id(_set_title(derived[0], GRUB_TITLE), OPEN_ID)
    start, end = 0, len(derived) - 1
    index = _kernel_line(derived, start, end)
    if index is None:
        raise SystemExit("default menuentry has no linux line")
    derived[index] = _set_module_blacklist(derived[index], OPEN_BLACKLIST)
    derived[index] = _set_nouveau_modeset(derived[index], False)
    return derived


# ── syslinux (BIOS path) ───────────────────────────────────────────────────

LABEL_RE = re.compile(r"^LABEL\s+(\S+)")


def label_blocks(lines: list[str]) -> list[tuple[int, int, str]]:
    """Return (start, end, label) per syslinux LABEL block, inclusive."""
    starts = [(index, LABEL_RE.match(line).group(1))
              for index, line in enumerate(lines) if LABEL_RE.match(line)]
    blocks = []
    for position, (start, label) in enumerate(starts):
        end = starts[position + 1][0] - 1 if position + 1 < len(starts) else len(lines) - 1
        # A blank line separates entries; do not carry it into the block.
        while end > start and (
            not lines[end].strip() or lines[end].lstrip().startswith("#")
        ):
            end -= 1
        blocks.append((start, end, label))
    return blocks


def _append_line(lines: list[str], start: int, end: int) -> int | None:
    for index in range(start, end + 1):
        if lines[index].startswith("APPEND "):
            return index
    return None


def patch_syslinux(path: Path) -> None:
    lines = path.read_text().splitlines()
    blocks = dict((label, (start, end)) for start, end, label in label_blocks(lines))

    default_label = "cos64"
    if default_label not in blocks:
        raise SystemExit(f"{path}: no default LABEL {default_label} block found")
    start, end = blocks[default_label]
    append_index = _append_line(lines, start, end)
    if append_index is None:
        raise SystemExit(f"{path}: LABEL {default_label} has no APPEND line")
    line = _set_module_blacklist(lines[append_index], DEFAULT_BLACKLIST)
    lines[append_index] = _set_nouveau_modeset(line, True)

    nvidia_block = _nvidia_label_block(lines[start:end + 1])

    if "cos64nv" in blocks:
        nstart, nend = blocks["cos64nv"]
        lines[nstart:nend + 1] = nvidia_block
    else:
        lines[end + 1:end + 1] = [""] + nvidia_block

    path.write_text("\n".join(lines) + "\n")


def _nvidia_label_block(block: list[str]) -> list[str]:
    """Derive the BIOS NVIDIA-Open entry from the patched default entry."""
    derived = []
    in_help = False
    for line in block:
        if line.startswith("LABEL "):
            derived.append("LABEL cos64nv")
        elif line.strip() == "TEXT HELP":
            in_help = True
            derived.append(line)
        elif line.strip() == "ENDTEXT":
            in_help = False
            derived.append(line)
        elif in_help:
            continue  # replaced by one OPEN_HELP line below
        elif line.startswith("MENU LABEL"):
            derived.append("MENU LABEL " + SYSLINUX_TITLE)
        elif line.startswith("LINUX "):
            # Turing+ cards run the current kernel, like the GRUB entry.
            derived.append(line.replace("cachyos-lts", "cachyos"))
        elif line.startswith("INITRD "):
            derived.append(line.replace("cachyos-lts", "cachyos"))
        elif line.startswith("APPEND "):
            stripped = _set_nouveau_modeset(
                _set_module_blacklist(line, OPEN_BLACKLIST), False)
            derived.append(stripped)
        else:
            derived.append(line)

    # Keep the help text structure (TEXT HELP / text / ENDTEXT) but with the
    # NVIDIA wording: the derived block dropped the original text lines.
    result = []
    for line in derived:
        result.append(line)
        if line.strip() == "TEXT HELP":
            result.append(OPEN_HELP)
    return result


# ── validation ─────────────────────────────────────────────────────────────

def validate(path: Path) -> list[str]:
    """Return the problems that make this boot config unbootable."""
    problems = []
    lines = path.read_text().splitlines()
    depth = 0
    opened_at = None
    for lineno, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("}}"):
            problems.append(
                f"{path}:{lineno}: line starts with a doubled brace — GRUB's "
                f"lexer rejects it (script/lexer.c syntax error) and a "
                f"USB-booted stick shows a broken menu; a menuentry closes "
                f"with a single closing brace")
        if depth == 0:
            if MENUENTRY_RE.match(line):
                opened_at = lineno
                depth = line.count("{") - line.count("}")
                if depth < 0:
                    problems.append(f"{path}:{lineno}: menuentry closes more braces than it opens")
                    depth, opened_at = 0, None
                elif depth == 0:
                    opened_at = None
            continue
        depth += line.count("{") - line.count("}")
        if depth < 0:
            problems.append(f"{path}:{lineno}: menuentry opened at line {opened_at} closes twice")
            depth, opened_at = 0, None
        elif depth == 0:
            opened_at = None
    if depth > 0:
        problems.append(
            f"{path}:{opened_at}: menuentry is never closed (unbalanced braces)")
    return problems


def collect(targets: list[str]) -> list[Path]:
    paths: list[Path] = []
    for target in targets:
        path = Path(target)
        if path.is_dir():
            paths.extend(sorted(path.rglob("*.cfg")))
        elif path.is_file():
            paths.append(path)
        else:
            raise SystemExit(f"no such file or directory: {target}")
    return paths


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        print("usage: iso-boot-config.py {patch-grub|patch-syslinux|check} <path>...",
              file=sys.stderr)
        return 2

    command, targets = argv[1], argv[2:]
    if command == "patch-grub":
        for target in targets:
            patch_grub(Path(target))
    elif command == "patch-syslinux":
        for target in targets:
            patch_syslinux(Path(target))
    elif command == "check":
        paths = collect(targets)
        problems = [problem for path in paths for problem in validate(path)]
        for problem in problems:
            print(problem, file=sys.stderr)
        if problems:
            print(f"boot config check failed: {len(problems)} problem(s) in {len(paths)} file(s)",
                  file=sys.stderr)
            return 1
        print(f"boot config check passed ({len(paths)} file(s))")
    else:
        print(f"unknown subcommand: {command}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
