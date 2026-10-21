#!/bin/bash
# Find the ISO that mkarchiso just wrote.
# ======================================
# mkarchiso names its output cachyos-<iso_version>-x86_64.iso, and <iso_version>
# is NOT the build date. The CachyOS profile computes it from SOURCE_DATE_EPOCH,
# and mkarchiso overrides that epoch from <work-dir>/build_date — a file written
# on the FIRST build of a work dir and reused forever after (archiso 91: see
# "Read SOURCE_DATE_EPOCH from file early"). build.sh used to predict "today",
# so a full build on 2026-10-21 produced cachyos-2026.08.12-x86_64.iso and the
# wrapper failed with "did not produce expected output: cachyos-2026.10.21...".
#
# Don't predict: ask the filesystem. The caller passes the time it started
# mkarchiso, and the newest matching ISO written at or after that moment is the
# one this run produced.
#
# Usage:
#   find-built-iso.sh <out-dir> [--since <epoch-seconds>]
#
#   <out-dir>   the directory mkarchiso was given with -o
#   --since     ignore ISOs modified before <epoch> (i.e. leftovers from an
#               earlier run, which mkarchiso may leave behind when it decides
#               its work is already done)
#
# Prints the absolute-ish path (newest mtime first, ties broken by name so the
# result is deterministic) and exits 0.
# Exit 1 when nothing matches — the reason, plus every *.iso it did find with
# its mtime, goes to stderr, because "mkarchiso produced nothing" is otherwise
# indistinguishable from "we looked in the wrong place".
# Exit 2 on a bad invocation.
#
# Called by iso/build.sh phase 1; tested by phase1/tests/test_phase1_stock_iso.py.

set -euo pipefail

usage="usage: find-built-iso.sh <out-dir> [--since <epoch-seconds>]"

out_dir="${1:-}"
if [[ -z "$out_dir" ]]; then
    echo "$usage" >&2
    exit 2
fi
shift

since=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --since)
            since="${2:-}"
            if [[ ! "$since" =~ ^[0-9]+$ ]]; then
                echo "$usage: --since needs a whole number of seconds since the epoch" >&2
                exit 2
            fi
            shift 2
            ;;
        *)
            echo "$usage: unexpected argument '$1'" >&2
            exit 2
            ;;
    esac
done

if [[ ! -d "$out_dir" ]]; then
    echo "find-built-iso: $out_dir is not a directory" >&2
    exit 2
fi

find_args=( "$out_dir" -maxdepth 1 -type f -name 'cachyos-*-x86_64.iso' )
if [[ -n "$since" ]]; then
    # find's -newermt is strictly greater, so compare against since-1 to mean
    # "modified at or after <since>" (mtime is whole seconds).
    find_args+=( -newermt "@$(( since > 0 ? since - 1 : 0 ))" )
fi

# mtime as a sortable number first, then the name; `tail -1` keeps the newest.
newest=$(
    find "${find_args[@]}" -printf '%T@\t%p\n' \
        | sort -k1,1n -k2,2 \
        | tail -n 1 \
        | cut -f2- \
        || true
)

if [[ -n "$newest" ]]; then
    printf '%s\n' "$newest"
    exit 0
fi

if [[ -n "$since" ]]; then
    printf 'find-built-iso: no cachyos-*-x86_64.iso in %s was written at or after %s\n' \
        "$out_dir" "$(date --date="@$since" '+%Y-%m-%d %H:%M:%S')" >&2
else
    printf 'find-built-iso: no cachyos-*-x86_64.iso in %s\n' "$out_dir" >&2
fi

# Name what is there: usually either the previously built ISO (left in place
# because mkarchiso skipped assembly) or nothing but Syntropia-branded files.
if compgen -G "$out_dir/*.iso" >/dev/null; then
    printf '  ISO files present (newest last):\n' >&2
    while IFS=$'\t' read -r _mtime path; do
        [[ -n "$path" ]] || continue
        printf '    %s  %s\n' \
            "$(date --date="@${_mtime%%.*}" '+%Y-%m-%d %H:%M:%S')" "$path" >&2
    done < <(find "$out_dir" -maxdepth 1 -type f -name '*.iso' -printf '%T@\t%p\n' | sort -k1,1n -k2,2)
fi

exit 1
