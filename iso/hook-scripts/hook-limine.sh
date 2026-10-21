#!/bin/bash
# hook-limine.sh — verify (and where it is safe, repair) the Limine install
# that Calamares' bootloader module produced.
# ======================================================================
# Runs from shellprocess_syntropia_limine with dontChroot: true, so it executes
# in the LIVE environment with $1 = ROOT = the target mount point, immediately
# after the Calamares `bootloader` module and before anything unmounts.
#
# Why it exists: syntropia-install-runner installs Limine itself and aborts
# when it cannot (see iso/installer/lib/bootloader.sh). The Calamares path
# delegates to CachyOS' limine module, which historically fell over on the
# 82% "Configuring Limine bootloader & kernel" step because the limine package
# was missing from the image. build.sh now ships it in the live rootfs and in
# pacstrap basePackages, but a silent fallback to another loader would still
# look like a successful install and only show up at the next boot, so the
# pieces a Limine boot cannot do without are checked here:
#
#   UEFI : <ESP>/limine.conf with a menu entry
#          + a Limine EFI executable on the ESP (BOOTX64.EFI)
#   BIOS : limine-bios.sys on the boot volume
#          + a GPT "BIOS boot" (ef02) partition for Limine's stage 2
#          + `limine bios-install` re-run (idempotent, same command the TUI
#            runner uses)
#
# Missing payload files are copied from the limine package (cheap, safe).
# Partitioning problems are reported and fail the install — this hook never
# repartitions a disk.
#
# Env overrides exist for tests: SYNTROPIA_EFIVARS_DIR (firmware type),
# SYNTROPIA_LIMINE_ESP / _DISK / _BIN (skip device discovery).
set -u

ROOT="${1:-/}"
EFIVARS_DIR="${SYNTROPIA_EFIVARS_DIR:-/sys/firmware/efi/efivars}"
LOG_PREFIX="syntropia-limine"
BIOS_BOOT_GUID="21686148-6449-6e6f-744e-656564454649"   # GPT type ef02

say()  { printf '%s: %s\n' "$LOG_PREFIX" "$*"; }
warn() { printf '%s: warning: %s\n' "$LOG_PREFIX" "$*" >&2; }
fail() { printf '%s: ERROR: %s\n' "$LOG_PREFIX" "$*" >&2; exit 1; }

[[ -d "$ROOT" ]] || fail "target root '$ROOT' is not a directory"

# Keep a copy on the installed system next to the other hook logs.
if [[ -d "$ROOT/var/log" ]] && command -v tee >/dev/null 2>&1; then
    exec > >(tee -a "$ROOT/var/log/syntropia-hooks.log") 2>&1
fi

CONF=""
for candidate in "$ROOT/boot/limine.conf" "$ROOT/boot/limine/limine.conf" \
                 "$ROOT/boot/efi/limine.conf"; do
    if [[ -f "$candidate" ]]; then
        CONF="$candidate"
        break
    fi
done
[[ -n "$CONF" ]] || fail "no limine.conf in the target — the Calamares bootloader step did not install Limine"
grep -q '^/' "$CONF" || fail "$CONF has no menu entry"
say "limine.conf present: $CONF"

BOOT_DIR="$(dirname "$CONF")"

# Payload source: the target's limine package (basePackages ships it), then the
# live image.
limine_payload() {
    local name="$1" candidate
    for candidate in "$ROOT/usr/share/limine/$name" "/usr/share/limine/$name"; do
        if [[ -f "$candidate" ]]; then
            printf '%s' "$candidate"
            return 0
        fi
    done
    return 1
}

uefi=0
[[ -d "$EFIVARS_DIR" ]] && uefi=1

# --- UEFI: the ESP must carry Limine's EFI executable ---------------------
if (( uefi )); then
    efi_found=""
    for candidate in "$BOOT_DIR/EFI/BOOT/BOOTX64.EFI" \
                     "$BOOT_DIR/EFI/limine/BOOTX64.EFI" \
                     "$BOOT_DIR/EFI/syntropia/BOOTX64.EFI"; do
        if [[ -f "$candidate" ]]; then
            efi_found="$candidate"
            break
        fi
    done
    if [[ -z "$efi_found" ]]; then
        src="$(limine_payload BOOTX64.EFI)" \
            || fail "no Limine EFI executable on the ESP and none in the image to repair it from"
        install -Dm644 "$src" "$BOOT_DIR/EFI/BOOT/BOOTX64.EFI"
        warn "ESP had no Limine EFI executable — repaired /EFI/BOOT/BOOTX64.EFI from $src"
    else
        say "UEFI payload present: $efi_found"
    fi
fi

# --- BIOS: stage 2 on the boot volume, in an ef02 partition, installed -----
if (( ! uefi )); then
    if [[ ! -f "$BOOT_DIR/limine-bios.sys" ]]; then
        src="$(limine_payload limine-bios.sys)" \
            || fail "limine-bios.sys missing from the boot volume and not available in the image"
        install -Dm644 "$src" "$BOOT_DIR/limine-bios.sys"
        warn "limine-bios.sys was missing — copied from $src"
    else
        say "BIOS stage 2 payload present: $BOOT_DIR/limine-bios.sys"
    fi

    esp_dev="${SYNTROPIA_LIMINE_ESP:-}"
    if [[ -z "$esp_dev" ]]; then
        esp_dev="$(findmnt -no SOURCE --target "$BOOT_DIR" 2>/dev/null || true)"
    fi
    disk="${SYNTROPIA_LIMINE_DISK:-}"
    if [[ -z "$disk" && -n "$esp_dev" ]]; then
        disk="$(lsblk -no PKNAME "$esp_dev" 2>/dev/null | head -n1)"
        [[ -n "$disk" ]] && disk="/dev/$disk"
    fi

    if [[ -z "$disk" ]]; then
        warn "cannot determine the disk holding $BOOT_DIR — Limine's BIOS stage 2 was not verified"
    else
        bios_part="$(lsblk -no PARTN,PARTTYPE "$disk" 2>/dev/null \
            | awk -v g="$BIOS_BOOT_GUID" 'tolower($2) == g { print $1; exit }')"
        [[ -n "$bios_part" ]] \
            || fail "no GPT 'BIOS boot' (ef02) partition on $disk — Limine's BIOS stage 2 has nowhere to live, so the disk would not boot on BIOS firmware"
        say "BIOS boot partition: ${disk}${bios_part}"

        limine_bin="${SYNTROPIA_LIMINE_BIN:-}"
        if [[ -z "$limine_bin" ]]; then
            for candidate in "$ROOT/usr/bin/limine" /usr/bin/limine; do
                if [[ -x "$candidate" ]]; then
                    limine_bin="$candidate"
                    break
                fi
            done
        fi
        if [[ -z "$limine_bin" ]]; then
            warn "no limine binary available — skipped 'limine bios-install' (Calamares' bootloader step already ran it)"
        else
            # Same command the TUI runner uses, and idempotent: it rewrites the
            # MBR code and stage 2 rather than appending anything.
            "$limine_bin" bios-install "$disk" "$bios_part" \
                || fail "'$limine_bin bios-install $disk $bios_part' failed — the disk would not boot on BIOS firmware"
            say "limine bios-install $disk $bios_part: ok"
        fi
    fi
fi

say "Limine bootloader verified"
exit 0
