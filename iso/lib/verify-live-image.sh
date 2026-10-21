#!/bin/bash
# Phase-2 guard: refuse to remaster a stock ISO whose live image is stale.
# ======================================================================
# `--phase2` only remasters an existing stock ISO. It can swap branding, the
# installer scripts and config files, but it CANNOT install packages. The
# stock image must therefore already carry the current live package set —
# today that is `limine`, which patch 1b appends to packages.x86_64.
# `usr/share/limine/{BOOTX64.EFI,limine-bios.sys}` is what
# syntropia-install-runner copies to the ESP; without it the runner aborts and
# the ISO installs nothing.
#
# Learned the hard way (2026-10-21 VM test): a --phase2 run against the
# Aug-12 stock image produced an ISO with the new installer, hooks and Limine
# config — but no limine package, because phase 1 never re-ran. Every install
# died at "Installing Limine", 20 minutes into a VM test.
#
# Usage: verify-live-image.sh <unsquashed-rootfs> [<stock-iso>]
#   0  the image carries the current live package set
#   1  stale image (every reason is printed on stderr)
#   2  bad invocation (no rootfs — unsquashfs has not run)
set -u

ROOTFS="${1:-}"
ISO_LABEL="${2:-the stock ISO}"

if [[ -z "$ROOTFS" || ! -d "$ROOTFS" ]]; then
    echo "verify-live-image: no unsquashed rootfs at '${ROOTFS:-}'" >&2
    exit 2
fi

missing=()
# The package itself (pacman's local database), then the two payloads the
# installer copies. Both are checked: a stray payload without the package
# means the image was hand-edited and will not survive a kernel update.
if ! compgen -G "$ROOTFS/var/lib/pacman/local/limine-[0-9]*" >/dev/null; then
    missing+=("package limine is not installed in the live image")
fi
for required in usr/share/limine/BOOTX64.EFI usr/share/limine/limine-bios.sys; do
    if [[ ! -f "$ROOTFS/$required" ]]; then
        missing+=("$required is missing")
    fi
done

if (( ${#missing[@]} == 0 )); then
    exit 0
fi

{
    echo "Stale stock image: ${ISO_LABEL} predates the current live package set."
    printf '  - %s\n' "${missing[@]}"
    echo
    echo "Phase 2 only remasters an existing image — it cannot install packages,"
    echo "and the installer needs limine (BOOTX64.EFI + limine-bios.sys) in the"
    echo "live rootfs to produce a bootable system. Rebuild the stock image:"
    echo
    echo "  sudo iso/build.sh      # phase 1 must run to pick up the patched package list"
    echo
    echo "Then rerun --phase2, or simply use the full build."
} >&2
exit 1
