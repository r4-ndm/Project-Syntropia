#!/bin/bash
# Syntropia ISO Build Pipeline
# ==============================
# Builds a CachyOS installer ISO with Syntropia branding slides.
#
# Usage:
#   sudo ./build.sh              # Full build (phases 1+2)
#   sudo ./build.sh --phase1     # Just the mkarchiso build (standard ISO)
#   sudo ./build.sh --phase2     # Just the slide injection into an existing ISO
#
# Requirements:
#   - archiso package (mkarchiso)
#   - Root access (sudo) for mkarchiso, mksquashfs, xorriso
#   - ~10GB free disk space for workdir
#   - ~15GB for package cache (first run only)
#
# Output: out/syntropia-YYYY.MM.DD-x86_64.iso

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
WORK_DIR="${WORK_DIR:-$REPO_ROOT/iso/work}"
OUT_DIR="${OUT_DIR:-$REPO_ROOT/iso/out}"
CACHYOS_ISO_REPO="https://github.com/CachyOS/CachyOS-Live-ISO.git"
CACHYOS_PROFILE_DIR="$WORK_DIR/CachyOS-Live-ISO/archiso"

# Branding source: slides live in the repo under Branding/ — single source of
# truth. Edit slide{1..6}.png + .jxl in calamares/slides/, nothing else.
BRANDING_SRC="$REPO_ROOT/Branding/syntropia/calamares/slides"

# Apps wizard: shipped from the app-wiz4rd RELEASE TARBALL (vendored in
# iso/vendor/, sha256-pinned) so the ISO tracks the standalone repo instead of
# an in-repo copy — the app-wiz4rd repo is the single source of truth for the
# wizard. Regenerate from the app-wiz4rd repo root — or just run its
# scripts/release.sh, which builds both artifacts and prints the sha256sums:
#   git archive --format=tar --prefix="app-wiz4rd-$APP_WIZ4RD_VERSION/" \
#     --mtime="2026-08-14 12:00:00 UTC" \
#     -o release/app-wiz4rd-$APP_WIZ4RD_VERSION.tar HEAD^{tree} -- . ':(exclude)aur' ':(exclude)scripts' ':(exclude).github'
#   (plain tar, not tar.gz — gzip output varies by zlib version; archive
#   HEAD^{tree}, not HEAD — HEAD embeds a commit-id pax comment that changes
#   the hash on every commit even when the files don't)
# then copy it into iso/vendor/ and set APP_WIZ4RD_SHA256 (sha256sum).
APP_WIZ4RD_VERSION="0.1.0"
APP_WIZ4RD_SHA256="3735eaea3d838cceef679d0bc5828eee024ab436590c53f1b94098a87946e1a4"
APP_WIZ4RD_TARBALL="$REPO_ROOT/iso/vendor/app-wiz4rd-$APP_WIZ4RD_VERSION.tar"

# hyprbars: the upstream Hyprland plugin that draws titlebars with window
# buttons. It is AUR-only (`hyprland-plugin-hyprbars`), so it cannot join the
# pacman package lists below — phase 2 builds it from the hyprland-plugins
# release matching the installed Hyprland and installs it here. The Syntropia
# Lua overlay (/etc/skel/.config/hypr/config/hyprbars.lua) loads it only when
# this module exists, so a failed build degrades to a titlebar-less desktop
# instead of a broken config.
HYPRBARS_REPO="https://github.com/hyprwm/hyprland-plugins.git"
HYPRBARS_INSTALL_PATH="/usr/lib/hyprland/hyprbars.so"

# ISO_NAME is the only thing this date is used for. It is NOT a prediction of
# what mkarchiso will name its output: mkarchiso derives that name from
# SOURCE_DATE_EPOCH, and inside a reused work dir it overrides SOURCE_DATE_EPOCH
# from <work-dir>/build_date — a file pinned by the first build in that work dir
# and never refreshed (archiso 91: "Read SOURCE_DATE_EPOCH from file early").
# On 2026-10-21 that made a full build emit cachyos-2026.08.12-x86_64.iso while
# the wrapper waited for cachyos-2026.10.21-x86_64.iso. Phase 1 now finds what
# mkarchiso produced by mtime (iso/lib/find-built-iso.sh) and renames that.
#
# SOURCE_DATE_EPOCH is deliberately NOT exported here: mkarchiso would overwrite
# it from build_date anyway, so exporting it would only *look* deterministic.
# Set it in the environment to date the Syntropia names, and delete
# iso/work/mkarchiso-work/build_date when you also want mkarchiso's own stamps
# refreshed.
ISO_DATE="${SOURCE_DATE_EPOCH:-$(date +%s)}"
ISO_DATE=$(date --date="@$ISO_DATE" +%Y.%m.%d)
ISO_NAME="syntropia-${ISO_DATE}-x86_64"

PHASE="${1:-all}"

# ── Color helpers ──────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
warn()  { echo -e "${RED}[WARN]${NC} $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }
die()   { err "$@"; }

# Detach kernel mounts that a killed run can leave inside the unsquashed
# rootfs. Two reasons this is not optional:
#   * mksquashfs would swallow the HOST's /proc and /sys into the shipped
#     squashfs (a live image with the builder's process table), and
#   * the `rm -rf rootfs` cleanup would then try to delete through them.
# Lazy unmount (`umount -l`) is the only form that works for a mount still in
# use, and it is a no-op when nothing is mounted there. Order matters:
# efivars lives under sys, so it has to go first.
lazy_umount_rootfs() {
    local rootfs="$1" mountpoint
    for mountpoint in sys/firmware/efi/efivars sys proc dev run; do
        if mountpoint -q "$rootfs/$mountpoint" 2>/dev/null; then
            umount -l "$rootfs/$mountpoint" 2>/dev/null \
                || warn "Could not lazily unmount $rootfs/$mountpoint"
        fi
    done
}

# ── Pre-flight checks ─────────────────────────────────────────
check_root() {
    if [[ $EUID -ne 0 ]]; then
        err "This script must be run as root (sudo). mkarchiso, mksquashfs, and xorriso require it."
    fi
}

check_deps() {
    for cmd in mkarchiso mksquashfs xorriso bsdtar unsquashfs git; do
        command -v "$cmd" >/dev/null || err "Missing required tool: $cmd. Install it first."
    done
    ok "All dependencies found"
}

# ── Phase 1: Standard ISO build with mkarchiso ─────────────────
phase1_build_iso() {
    info "=== Phase 1: Building standard CachyOS ISO with mkarchiso ==="

    # Clone or update the CachyOS ISO profile
    if [[ -d "$WORK_DIR/CachyOS-Live-ISO" ]]; then
        info "Updating CachyOS-Live-ISO..."
        git -C "$WORK_DIR/CachyOS-Live-ISO" pull --ff-only
    else
        info "Cloning CachyOS-Live-ISO..."
        git clone "$CACHYOS_ISO_REPO" "$WORK_DIR/CachyOS-Live-ISO"
    fi

    cd "$CACHYOS_PROFILE_DIR"

    # ── Apply Syntropia patches ──
    info "Applying Syntropia patches to profile..."

    # Patch 1: symlink packages.x86_64 → packages_desktop.x86_64
    # (mkarchiso looks for packages.x86_64 by default; CachyOS names it packages_desktop.x86_64)
    ln -sf packages_desktop.x86_64 packages.x86_64

    # Patch 1b: ship the limine package in the LIVE image. Limine is the
    # installed bootloader (NEXT_SESSION.md); the TUI installer rsyncs the live
    # rootfs onto the target, so /usr/bin/limine and /usr/share/limine/*
    # (BOOTX64.EFI, limine-bios.sys) must already be in the image — an
    # offline install cannot pacman them afterwards. packages.x86_64 is the
    # symlink created above, so this edits packages_desktop.x86_64.
    if ! grep -qx 'limine' packages.x86_64; then
        printf 'limine\n' >> packages.x86_64
        ok "limine added to the live package list"
    fi

    # Patch 1c: KWallet's PAM auto-unlock needs pam_kwallet5.so (kwallet-pam),
    # the wallet daemon it launches (kwallet: ksecretd + kwalletd6) and socat,
    # the helper its pam_kwallet_init script uses to hand the password over.
    # CachyOS pulls kwallet in as a Plasma dependency, and Plasma is no longer
    # in the list, so all three are named explicitly: without them the installed
    # system asks the user to create a NEW wallet password at first login
    # (2026-10-21 and 2026-10-25 laptop installs).
    for pkg in kwallet-pam kwallet socat; do
        if ! grep -qx "$pkg" packages.x86_64; then
            printf '%s\n' "$pkg" >> packages.x86_64
            ok "$pkg added to the live package list (keyring auto-unlock)"
        fi
    done

    # Patch 1d: Hyprland (UWSM) is the only desktop. Plasma is removed from
    # both the live image and the installed target (NEXT_SESSION.md item 4), so
    # the stock profile's KDE entries must never be pacstrapped: mkarchiso
    # installs the whole list in ONE transaction, before any of phase 2 runs,
    # so the entries are deleted from the profile here and not removed later.
    # The edits go to packages_desktop.x86_64, the real file: `sed -i` on the
    # packages.x86_64 symlink would replace the symlink itself.
    local -a plasma_pkgs=(
        kde-gtk-config plasma-desktop plasma-integration plasma-nm plasma-pa
        plasma-thunderbolt plasma-workspace polkit-kde-agent
        plasma-login-manager
    )
    local plasma_pkg
    for plasma_pkg in "${plasma_pkgs[@]}"; do
        if grep -qx "$plasma_pkg" packages_desktop.x86_64; then
            sed -i "/^${plasma_pkg}\$/d" packages_desktop.x86_64
            ok "$plasma_pkg removed from the live package list (Hyprland-only)"
        fi
    done

    # gnome-keyring conflicts with KWallet/ksecretd Secret Service ownership and
    # causes "Choose password for new keyring" prompts at login / browser startup.
    # We remove gnome-keyring from the package list entirely.
    if grep -qx 'gnome-keyring' packages_desktop.x86_64; then
        sed -i "/^gnome-keyring\$/d" packages_desktop.x86_64
        ok "gnome-keyring removed from the live package list (KWallet is the Secret Service)"
    fi

    # plasma-login-manager was the image's only display manager, so removing it
    # means shipping SDDM explicitly: the installer wires SDDM autologin into the
    # hyprland-uwsm session and the keyring PAM drop-in patches sddm/sddm-autologin.
    if ! grep -qx 'sddm' packages.x86_64; then
        printf 'sddm\n' >> packages.x86_64
        ok "sddm added to the live package list (the login manager)"
    fi

    # Patch 2: Add NoExtract for slide files in pacman.conf [options] section
    # This prevents cachyos-calamares-next package slides from conflicting with our airootfs overlay.
    # Note: We place slides in airootfs/ after this phase. During Phase 2 we overwrite them at the
    # squashfs level, which is the more reliable approach. The NoExtract is a safety net.
    if ! grep -q 'Syntropia: use our custom branding' pacman.conf; then
        python3 - "$CACHYOS_PROFILE_DIR/pacman.conf" << 'PYEOF'
import sys
with open(sys.argv[1], 'r') as f:
    content = f.read()

noextract_block = '''#NoExtract   =
# Syntropia: use our custom branding slides — skip the package's
NoExtract = usr/share/calamares/branding/cachyos/slide1.jxl
NoExtract = usr/share/calamares/branding/cachyos/slide2.jxl
NoExtract = usr/share/calamares/branding/cachyos/slide3.jxl
NoExtract = usr/share/calamares/branding/cachyos/slide4.jxl
NoExtract = usr/share/calamares/branding/cachyos/slide5.jxl
NoExtract = usr/share/calamares/branding/cachyos/slide6.jxl'''

content = content.replace('#NoExtract   =', noextract_block)
with open(sys.argv[1], 'w') as f:
    f.write(content)
PYEOF
    fi

    ok "Patches applied"

    # ── Drop the cached rootfs when the patched profile changed ──
    # mkarchiso skips every step whose marker exists in the work dir, and that
    # includes pacstrap (`base._make_packages`) and the airootfs squashfs
    # (`base._prepare_airootfs_image` / `_mkairootfs_squashfs`). Those caches are
    # older than the profile we just patched, so a "rebuild" would re-assemble an
    # ISO around an old rootfs: on 2026-10-21 a run re-used an Aug-12 squashfs
    # and shipped an image with no `limine` package at all, which then fails
    # every install. Stamp the patched inputs and throw the rootfs away when
    # they change (or when the work dir predates this stamp).
    local patch_stamp="$WORK_DIR/mkarchiso-work/syntropia-patches.sha256"
    local patch_hash
    patch_hash=$(sha256sum packages.x86_64 pacman.conf profiledef.sh | sha256sum | cut -d' ' -f1)
    if [[ -d "$WORK_DIR/mkarchiso-work" && "$(cat "$patch_stamp" 2>/dev/null || true)" != "$patch_hash" ]]; then
        warn "Patched profile changed since this work dir was built — discarding the cached rootfs and squashfs so the live image matches packages.x86_64"
        rm -rf "$WORK_DIR/mkarchiso-work"/base.* \
               "$WORK_DIR/mkarchiso-work/x86_64/airootfs" \
               "$WORK_DIR/mkarchiso-work/iso"
    fi

    # ── Re-assemble the ISO on every run ──
    # mkarchiso records completed steps as empty marker files in the work dir
    # and skips every step whose marker exists. Phase 1 renames the produced ISO
    # away (cachyos-*.iso → ${ISO_NAME}-stock.iso) after each successful run, so
    # on a second run mkarchiso would find its "ISO produced" markers, skip the
    # assembly, and exit 0 without writing anything.
    #
    # Drop exactly those two markers: `build._build_buildmode_iso` (the whole
    # buildmode) and `iso._build_iso_image` (the xorriso assembly). Everything
    # expensive — pacstrap, the airootfs squashfs, boot modes — is gated by
    # `base.*` markers, which stay, so this is a re-assembly (~minutes), not a
    # rebuild. Unconditional on purpose: the produced ISO's name cannot be
    # predicted (see the ISO_DATE note at the top), so there is no file to test
    # for before deciding.
    local renamed_iso="$OUT_DIR/${ISO_NAME}-stock.iso"
    local marker
    for marker in "$WORK_DIR/mkarchiso-work/build._build_buildmode_iso" \
                  "$WORK_DIR/mkarchiso-work/iso._build_iso_image"; do
        if [[ -e "$marker" ]]; then
            info "Clearing ISO-assembly marker $(basename "$marker") (the previous ISO was renamed away)"
            rm -f "$marker"
        fi
    done

    # ── Build with mkarchiso ──
    local run_started_at produced_iso
    run_started_at=$(date +%s)
    info "Running mkarchiso (this downloads ~990 packages on first run)..."
    mkarchiso -v -w "$WORK_DIR/mkarchiso-work" -o "$OUT_DIR" "$CACHYOS_PROFILE_DIR"

    # A keyring that cannot unlock fails silently (the user just gets a wallet
    # prompt at first login), so check the built rootfs here where the reason is
    # still on screen.
    local built_rootfs
    built_rootfs="$WORK_DIR/mkarchiso-work/x86_64/airootfs"
    if [[ -f "$built_rootfs/usr/lib/security/pam_kwallet5.so" ]] \
        && [[ -x "$built_rootfs/usr/bin/socat" ]] \
        && [[ -x "$built_rootfs/usr/bin/ksecretd" || -x "$built_rootfs/usr/bin/kwalletd6" ]]; then
        ok "Keyring PAM module + wallet daemon + socat are in the live image (wallet auto-unlock can work)"
    else
        warn "pam_kwallet5.so, the kwallet daemon or socat is missing from the live image — installs will ask to create a wallet password"
    fi

    # ── Rename whatever mkarchiso actually produced ──
    # Its output is cachyos-<iso_version>-x86_64.iso, and <iso_version> comes
    # from the work dir's build_date, so it can lag the real build date by
    # months. Take the newest cachyos-*-x86_64.iso written at or after this run
    # started (phase 2 will only ever look for ${ISO_NAME}-stock.iso).
    if ! produced_iso=$("$SCRIPT_DIR/lib/find-built-iso.sh" "$OUT_DIR" --since "$run_started_at"); then
        err "mkarchiso produced no new ISO in $OUT_DIR (see the file list above). If only an older cachyos-*.iso is listed, mkarchiso believes its work is done: rm -rf '$WORK_DIR/mkarchiso-work' and re-run phase 1."
    fi
    mv "$produced_iso" "$renamed_iso"

    # Only stamp after a successful build: a failed run must keep the cache
    # marked as suspect so the next one rebuilds the rootfs instead of trusting
    # a half-written one.
    mkdir -p "$WORK_DIR/mkarchiso-work"
    printf '%s\n' "$patch_hash" > "$patch_stamp"

    ok "Phase 1 complete: $renamed_iso (from $(basename "$produced_iso"), $(du -h "$renamed_iso" | cut -f1))"
}

# Build hyprbars into a rootfs at $HYPRBARS_INSTALL_PATH (see the constants at
# the top for why this is a source build rather than a package).
# Hyprland ships its own headers and hyprland.pc, so compiling against the
# image's Hyprland keeps the plugin's API hash in sync with the running
# compositor — no hyprpm state, no non-root build user, no AUR helper.
# Returns non-zero when the plugin could not be produced; the caller only warns.
install_hyprbars_plugin() {
    local rootfs="$1"
    local hyprland_ver tag src_dir dep
    local build_deps=(make pkgconf)
    local preinstalled_deps=()

    hyprland_ver=$(arch-chroot "$rootfs" pacman -Q hyprland 2>/dev/null | awk '{print $2}') || true
    hyprland_ver="${hyprland_ver##*:}" # drop a pkgver epoch, if any
    hyprland_ver="${hyprland_ver%%-*}"
    if [[ -z "$hyprland_ver" ]]; then
        warn "hyprland not installed in $rootfs — cannot build hyprbars"
        return 1
    fi

    # hyprland-plugins tags track Hyprland minor releases (v0.56.0 covers
    # 0.56.x). Prefer an exact release tag, fall back to the minor one.
    src_dir=$(mktemp -d)
    for tag in "v$hyprland_ver" "v${hyprland_ver%.*}.0"; do
        if git clone --depth 1 --branch "$tag" "$HYPRBARS_REPO" \
            "$src_dir/hyprland-plugins" >/dev/null 2>&1; then
            break
        fi
        rm -rf "$src_dir/hyprland-plugins"
        tag=""
    done
    if [[ -z "$tag" ]]; then
        rm -rf "$src_dir"
        warn "no hyprland-plugins release tag for Hyprland $hyprland_ver — skipping hyprbars"
        return 1
    fi

    # make + pkgconf are the only build tools missing from the live image;
    # everything else (g++, the Hyprland headers, the wayland/drm/input libs)
    # comes with the Hyprland installation itself.
    for dep in "${build_deps[@]}"; do
        if arch-chroot "$rootfs" pacman -Q "$dep" >/dev/null 2>&1; then
            preinstalled_deps+=("$dep")
        fi
    done
    if ! arch-chroot "$rootfs" pacman -S --noconfirm --needed --asdeps "${build_deps[@]}" >/dev/null 2>&1; then
        rm -rf "$src_dir"
        warn "could not install hyprbars build tools — skipping hyprbars"
        return 1
    fi

    mkdir -p "$rootfs/tmp/hyprbars-build"
    cp -a "$src_dir/hyprland-plugins/hyprbars/." "$rootfs/tmp/hyprbars-build/"
    rm -rf "$src_dir"

    local built=0 build_log
    build_log=$(mktemp)
    if arch-chroot "$rootfs" bash -c \
        'set -e; cd /tmp/hyprbars-build; make; install -Dm755 hyprbars.so "$1"' \
        _ "$HYPRBARS_INSTALL_PATH" >"$build_log" 2>&1; then
        built=1
    else
        # Surface the failure instead of hiding it: this is the one plugin the
        # ISO cannot get from a package.
        tail -n 15 "$build_log" >&2 || true
    fi
    rm -f "$build_log"
    rm -rf "$rootfs/tmp/hyprbars-build"

    # Drop the build-only tools again so the ISO stays lean; keep any that the
    # image already had for other reasons.
    for dep in "${build_deps[@]}"; do
        if [[ ! " ${preinstalled_deps[*]:-} " =~ " $dep " ]]; then
            arch-chroot "$rootfs" pacman -Rdd --noconfirm "$dep" >/dev/null 2>&1 || true
        fi
    done

    if [[ "$built" -eq 1 ]]; then
        ok "hyprbars compiled into $rootfs$HYPRBARS_INSTALL_PATH ($tag)"
    else
        warn "hyprbars build failed — ISO ships without titlebar buttons"
        return 1
    fi
}

# ── Phase 2: Inject Syntropia slides into the ISO ──────────────
phase2_inject_slides() {
    local input_iso="$OUT_DIR/${ISO_NAME}-stock.iso"
    local output_iso="$OUT_DIR/${ISO_NAME}.iso"

    if [[ ! -f "$input_iso" ]]; then
        local latest_stock
        # `|| true`: no match makes ls exit non-zero, which under pipefail would
        # abort the script here instead of reaching the error message below.
        latest_stock=$(ls -t "$OUT_DIR"/syntropia-*-stock.iso 2>/dev/null | head -1 || true)
        if [[ -n "$latest_stock" && -f "$latest_stock" ]]; then
            input_iso="$latest_stock"
            output_iso="${latest_stock/-stock.iso/.iso}"
            info "Auto-detected latest stock ISO: $(basename "$input_iso")"
        else
            # A phase 1 that died between mkarchiso and the rename leaves the
            # stock ISO under mkarchiso's own name — name it instead of only
            # reporting "not found".
            local leftover
            leftover=$(ls -t "$OUT_DIR"/cachyos-*-x86_64.iso 2>/dev/null | head -1 || true)
            if [[ -n "$leftover" ]]; then
                err "Stock ISO not found: $input_iso. $leftover is a cachyos-*.iso from $(date --date="@$(stat -c %Y "$leftover")" '+%Y-%m-%d %H:%M') — if that is the phase-1 output you want, rename it (mv '$leftover' '$input_iso') or just re-run --phase1 with the current build.sh."
            fi
            err "Stock ISO not found: $input_iso. Run --phase1 first."
        fi
    fi

    info "=== Phase 2: Injecting Syntropia branding slides ==="

    # Check we have slides to inject
    if [[ ! -f "$BRANDING_SRC/slide1.jxl" ]]; then
        err "Branding slides not found at $BRANDING_SRC. Run from repo root."
    fi

    local remaster_dir="$WORK_DIR/remaster"
    rm -rf "$remaster_dir"
    mkdir -p "$remaster_dir"
    cd "$remaster_dir"

    # Step 1: Extract ISO
    info "Extracting ISO..."
    bsdtar -xf "$input_iso"
    ok "ISO extracted"

    # Step 1.5: Extract EFI boot partition from stock ISO for UEFI El Torito boot
    info "Extracting EFI boot partition from stock ISO..."
    local efiboot_img="$WORK_DIR/efiboot.img"
    rm -f "$efiboot_img"
    local efi_start efi_size
    efi_start=$(sfdisk -d "$input_iso" 2>/dev/null | grep -i 'type=ef' | sed -n 's/.*start=[[:space:]]*\([0-9]*\).*/\1/p')
    efi_size=$(sfdisk -d "$input_iso" 2>/dev/null | grep -i 'type=ef' | sed -n 's/.*size=[[:space:]]*\([0-9]*\).*/\1/p')
    if [[ -n "$efi_start" && -n "$efi_size" ]]; then
        dd if="$input_iso" of="$efiboot_img" bs=512 skip="$efi_start" count="$efi_size" status=none
        ok "EFI boot partition extracted ($(du -h "$efiboot_img" | cut -f1))"
    else
        err "Could not locate EFI system partition (type=ef) in $input_iso"
    fi

    # Read original UUID / modification date from stock ISO to keep initramfs/GRUB matching
    local orig_uuid orig_mod_date
    orig_uuid=$(blkid -s UUID -o value "$input_iso" 2>/dev/null || echo "")
    if [[ -n "$orig_uuid" ]]; then
        orig_mod_date="${orig_uuid//-/}"
        info "Stock ISO UUID: $orig_uuid (modification date: $orig_mod_date)"
    else
        warn "Could not read stock ISO UUID via blkid"
    fi

    # Step 2: Unsquash the rootfs
    info "Unsquashing rootfs (this takes ~30s)..."
    unsquashfs -d rootfs arch/x86_64/airootfs.sfs
    ok "Rootfs unsquashed ($(du -sh rootfs | cut -f1))"

    # Step 2.5: the stock image must already carry the current live package
    # set. Phase 2 swaps files but cannot install packages, and the TUI runner
    # needs limine's payloads in the live rootfs (it rsyncs them to the target,
    # and aborts when they are absent). A stale stock ISO remasters perfectly
    # and then cannot install anything, so stop here with the reason instead.
    # Guard lives in iso/lib/verify-live-image.sh so it is testable on its own.
    info "Verifying the stock image carries the current live package set..."
    if ! "$SCRIPT_DIR/lib/verify-live-image.sh" "$remaster_dir/rootfs" "$input_iso"; then
        err "Stale stock ISO — refusing to remaster an image that cannot install (see above)."
    fi
    ok "Stock image is current (limine package + payloads present)"

    # The wallet auto-unlock chain lives in the live package set too: phase 2 can
    # inject the PAM config and the runner but cannot install pam_kwallet5.so or
    # socat. Warn instead of failing — an online install can pacman them into the
    # target itself, and the runner says so when it cannot.
    if [[ ! -f "$remaster_dir/rootfs/usr/lib/security/pam_kwallet5.so" ]] \
        || [[ ! -x "$remaster_dir/rootfs/usr/bin/socat" ]] \
        || [[ ! -x "$remaster_dir/rootfs/usr/bin/ksecretd" && ! -x "$remaster_dir/rootfs/usr/bin/kwalletd6" ]]; then
        warn "Stock image lacks kwallet-pam/kwallet/socat — offline installs will ask to create a wallet password (needs a phase-1 rebuild)"
    fi

    # Step 3: Swap in our amended slides
    info "Injecting Syntropia slides..."
    local cal_dir="rootfs/usr/share/calamares/branding/cachyos"
    cp "$BRANDING_SRC"/slide{1,2,3,4,5,6}.jxl "$cal_dir/"
    ok "Slides injected"

    # Step 3.3: Protect our amended slides from the live boot-time package
    # update. CachyOS's "Launch Installer" (calamares-online.sh) runs
    # `pacman -Sy --noconfirm cachyos-calamares-next` before starting
    # Calamares, which force-upgrades the package and re-extracts the STOCK
    # branding over our injected slides (observed: cachyos-calamares-next
    # 3.4.2-7 -> 3.4.2-11 at live boot clobbered slides 1-6).
    #
    # IMPORTANT: NoUpgrade/NoExtract are ONLY honored inside the [options]
    # section of pacman.conf. An earlier version appended these lines at the
    # END of the file (after the [cachyos]/[core]/[extra]/[multilib] repo
    # sections) — pacman silently ignored them, so the boot-time update
    # re-extracted the stock slides anyway. We now replace the commented
    # `#NoUpgrade   =` / `#NoExtract   =` placeholders that live INSIDE
    # [options], which is where pacman actually reads them.
    if ! grep -q 'Syntropia: keep our amended slides' "rootfs/etc/pacman.conf"; then
        python3 - "rootfs/etc/pacman.conf" << 'PYEOF'
import sys
path = sys.argv[1]
with open(path, 'r') as f:
    content = f.read()

noupgrade_block = '''#NoUpgrade   =
# Syntropia: keep our amended slides even when cachyos-calamares-next is
# force-updated at live boot (calamares-online.sh runs pacman -Sy for it).
# NOTE: must stay inside the [options] section — pacman ignores these after
# the first repo section (this was the bug: appending at EOF did nothing).
NoUpgrade = usr/share/calamares/branding/cachyos/slide1.jxl
NoUpgrade = usr/share/calamares/branding/cachyos/slide2.jxl
NoUpgrade = usr/share/calamares/branding/cachyos/slide3.jxl
NoUpgrade = usr/share/calamares/branding/cachyos/slide4.jxl
NoUpgrade = usr/share/calamares/branding/cachyos/slide5.jxl
NoUpgrade = usr/share/calamares/branding/cachyos/slide6.jxl
# ... and the Calamares settings we patch below (else the update also
# wipes our install-time wizard-copy hook) + pacstrap.conf (paru added
# to basePackages so every install ships it — see the pacstrap patch).
NoUpgrade = usr/share/calamares/settings_online.conf
NoUpgrade = usr/share/calamares/settings_offline.conf
NoUpgrade = etc/calamares/modules/pacstrap.conf
NoUpgrade = etc/calamares/modules/users.conf'''
noextract_block = '''#NoExtract   =
# Syntropia: never extract the package's own slide files either
# (belt-and-braces on top of NoUpgrade, both inside [options]).
NoExtract = usr/share/calamares/branding/cachyos/slide1.jxl
NoExtract = usr/share/calamares/branding/cachyos/slide2.jxl
NoExtract = usr/share/calamares/branding/cachyos/slide3.jxl
NoExtract = usr/share/calamares/branding/cachyos/slide4.jxl
NoExtract = usr/share/calamares/branding/cachyos/slide5.jxl
NoExtract = usr/share/calamares/branding/cachyos/slide6.jxl'''

# Only patch once (idempotent): guard on the marker comment, not the
# placeholder — the block itself starts with '#NoUpgrade   =', so checking
# for the placeholder alone would re-patch every run.
marker = 'Syntropia: keep our amended slides'
if marker not in content:
    if '#NoUpgrade   =' in content:
        content = content.replace('#NoUpgrade   =', noupgrade_block, 1)
    if '#NoExtract   =' in content:
        content = content.replace('#NoExtract   =', noextract_block, 1)
with open(path, 'w') as f:
    f.write(content)
PYEOF
        ok "NoUpgrade+NoExtract set inside [options] (survives live boot package update)"
    else
        ok "NoUpgrade already present for slide files"
    fi

    # Step 3.5: Configure direct TUI Omarchy-style installer on tty1
    info "Configuring direct TUI Omarchy-style installer on tty1 (masking graphical display managers)..."
    mkdir -p "rootfs/etc/systemd/system"
    ln -sf /dev/null "rootfs/etc/systemd/system/display-manager.service"
    ln -sf /dev/null "rootfs/etc/systemd/system/sddm.service"
    rm -f "rootfs/etc/systemd/system/default.target"
    ln -sf /usr/lib/systemd/system/multi-user.target "rootfs/etc/systemd/system/default.target"
    rm -f "rootfs/usr/local/bin/start-plasma" "rootfs/usr/local/bin/start-gui"

    # 2-4. Install the setup TUI, the progress dashboard and the install runner.
    #
    # These are REAL FILES in iso/installer/ (plus iso/installer/lib/), not
    # heredocs pasted into this script: they are the most-edited part of the
    # install flow, and as files they can be syntax-checked, dry-run and tested
    # (see phase1/tests/test_installer_tui.py). build.sh only ships them.
    info "Installing Syntropia installer scripts (iso/installer/)..."
    local installer_src="$REPO_ROOT/iso/installer"
    local script lib
    [[ -d "$installer_src/lib" ]] || err "iso/installer/lib missing — cannot build the install UI"
    for script in syntropia-install syntropia-install-runner syntropia-install-dashboard; do
        [[ -f "$installer_src/$script" ]] || err "iso/installer/$script missing"
        install -Dm755 "$installer_src/$script" "rootfs/usr/local/bin/$script"
    done
    for lib in "$installer_src"/lib/*.sh; do
        install -Dm644 "$lib" "rootfs/usr/local/lib/syntropia-installer/$(basename "$lib")"
    done
    ok "Installer UI, dashboard, runner and libraries installed"
    cp "rootfs/usr/local/bin/syntropia-install" "rootfs/root/.automated_script.sh"
    chmod +x "rootfs/root/.automated_script.sh"

    # Install profile.d launcher so tty1 launches installer immediately
    mkdir -p "rootfs/etc/profile.d"
    cat > "rootfs/etc/profile.d/syntropia-live-installer.sh" << 'EOF'
CUR_TTY=$(tty 2>/dev/null || echo "")
if [[ ("$CUR_TTY" == "/dev/tty1" || "$CUR_TTY" == "/dev/console") && -z "${SYNTROPIA_INSTALLER_LAUNCHED:-}" ]]; then
    export SYNTROPIA_INSTALLER_LAUNCHED=1
    exec /usr/local/bin/syntropia-install
fi
EOF
    chmod +x "rootfs/etc/profile.d/syntropia-live-installer.sh"

    # Also hook into liveuser, skel, and root bashrc/profile for tty1
    for d in "rootfs/etc/skel" "rootfs/home/liveuser" "rootfs/root"; do
        if [[ -d "$d" ]]; then
            echo 'CUR_TTY=$(tty 2>/dev/null || echo ""); [[ ("$CUR_TTY" == /dev/tty1 || "$CUR_TTY" == /dev/console) && -z "${SYNTROPIA_INSTALLER_LAUNCHED:-}" ]] && export SYNTROPIA_INSTALLER_LAUNCHED=1 && exec /usr/local/bin/syntropia-install' >> "$d/.bash_profile" 2>/dev/null || true
            echo 'CUR_TTY=$(tty 2>/dev/null || echo ""); [[ ("$CUR_TTY" == /dev/tty1 || "$CUR_TTY" == /dev/console) && -z "${SYNTROPIA_INSTALLER_LAUNCHED:-}" ]] && export SYNTROPIA_INSTALLER_LAUNCHED=1 && exec /usr/local/bin/syntropia-install' >> "$d/.bashrc" 2>/dev/null || true
        fi
    done
    ok "Direct TUI Omarchy-style installer configured to launch on tty1"

    # Step 3.6: Ship the apps wizard into /etc/syntropia/ so the first-boot
    # "pick your favorites" dialog is available on freshly-installed systems.
    # The wizard is shipped from the app-wiz4rd RELEASE TARBALL (vendored in
    # iso/vendor/, sha256-pinned) — the standalone app-wiz4rd repo is the
    # single source of truth, so there is no in-repo copy that can drift.
    # The wizard resolves the catalog as: --config, ~/.config/syntropia/apps.list
    # (user override), /etc/syntropia/apps.list (shipped here), bundled fallback.
    info "Shipping apps wizard from app-wiz4rd $APP_WIZ4RD_VERSION tarball..."
    local syn_dir="rootfs/etc/syntropia"
    local wiz_x wiz_sha
    [[ -f "$APP_WIZ4RD_TARBALL" ]] \
        || err "app-wiz4rd tarball missing: $APP_WIZ4RD_TARBALL — regenerate it (see APP_WIZ4RD_* at top)"
    wiz_sha="$(sha256sum "$APP_WIZ4RD_TARBALL" | awk '{print $1}')"
    [[ "$wiz_sha" == "$APP_WIZ4RD_SHA256" ]] \
        || err "app-wiz4rd tarball sha256 mismatch — regenerate it and update APP_WIZ4RD_SHA256"
    wiz_x="$(mktemp -d /tmp/app-wiz4rd.XXXXXX)"
    bsdtar -xf "$APP_WIZ4RD_TARBALL" -C "$wiz_x"
    local wizard_src="$wiz_x/app-wiz4rd-$APP_WIZ4RD_VERSION"
    mkdir -p "$syn_dir"
    cp "$wizard_src/app-wiz4rd" "$syn_dir/app-wiz4rd"
    cp "$REPO_ROOT/phase1/wizard/apps.list" "$syn_dir/apps.list"
    chmod +x "$syn_dir/app-wiz4rd"

    # The TUI dialog (dialog/syntropia-apps-tui) is the wizard's only
    # frontend — a static binary with zero runtime deps. Ship its source AND
    # a freshly built binary. CGO_ENABLED=0 keeps it a real static binary (a
    # cgo build links glibc); built here with the ISO toolchain's go.
    if [[ -d "$wizard_src/dialog" ]]; then
        cp -r "$wizard_src/dialog" "$syn_dir/dialog"
        rm -f "$syn_dir/dialog/syntropia-apps-tui"   # never ship a stale binary
        if command -v go >/dev/null 2>&1; then
            ( cd "$syn_dir/dialog" && CGO_ENABLED=0 go build -o syntropia-apps-tui . ) \
                && ok "TUI dialog built + shipped (static binary)" \
                || warn "TUI dialog build failed — wizard will try to build it on first run"
        else
            warn "go not found — TUI dialog source shipped but not built; wizard will build it on first run"
        fi
    else
        warn "wizard dialog/ dir missing — TUI not shipped"
    fi

    # Calamares shellprocess hook helpers: both hooks run their shell logic
    # through scripts because the module macro-expands commands with
    # KWordMacroExpander('$') — bare $vars in a command string are treated as
    # undefined macros and abort the job (see the hook comment).
    cp "$SCRIPT_DIR/hook-scripts/hook-branding-users.sh" "$syn_dir/"
    cp "$SCRIPT_DIR/hook-scripts/hook-limine.sh" "$syn_dir/"
    chmod +x "$syn_dir/hook-branding-users.sh" "$syn_dir/hook-limine.sh"

    # First-boot autostart entry: shipped as a template in /etc/syntropia/ —
    # NOT /etc/xdg/autostart/ — so the wizard does NOT fire in the live
    # session. Step 3.7 copies it into the INSTALLED system's autostart dir,
    # which is where it belongs (the standalone wizard has no live-env guard
    # by design; the live/installed gating lives here, not in the wizard).
    sed "s|@SCRIPT@|/etc/syntropia/app-wiz4rd|" \
        "$wizard_src/syntropia-apps.desktop" \
        > "$syn_dir/syntropia-apps.desktop"

    # App-menu launcher. The autostart entry is one-shot, so the wizard must also
    # be reachable by hand — that is how picks queued during an offline install
    # get finished after connecting (app-wiz4rd retries its pending queue on
    # start, and `--resume` installs it without the picker). The tarball's
    # launcher has a bare `app-wiz4rd` Exec; point it at the shipped path.
    mkdir -p "rootfs/usr/share/applications"
    sed "s|^Exec=app-wiz4rd$|Exec=/etc/syntropia/app-wiz4rd|" \
        "$wizard_src/app-wiz4rd.desktop" \
        > "rootfs/usr/share/applications/syntropia-apps.desktop"
    chmod 644 "rootfs/usr/share/applications/syntropia-apps.desktop"
    rm -rf "$wiz_x"
    ok "Apps wizard shipped (/etc/syntropia/ from app-wiz4rd tarball)"

    # Step 3.6b: Ship Hyprland Noctalia overlay & Syntropia tools
    info "Shipping Hyprland Noctalia overlay & Syntropia tools..."
    if [[ -d "$REPO_ROOT/iso/profiles/hyprland" ]]; then
        mkdir -p "$syn_dir/profiles/hyprland"
        cp -r "$REPO_ROOT/iso/profiles/hyprland/." "$syn_dir/profiles/hyprland/"
        if [[ -d "$REPO_ROOT/iso/profiles/hyprland/bin" ]]; then
            mkdir -p "rootfs/usr/local/bin"
            cp -a "$REPO_ROOT/iso/profiles/hyprland/bin/"* "rootfs/usr/local/bin/" 2>/dev/null || true
            chmod +x "rootfs/usr/local/bin"/syntropia-* 2>/dev/null || true
        fi
        ok "Hyprland Noctalia overlay shipped (/etc/syntropia/profiles/hyprland)"
    fi

    # Step 3.6b2: Chromium-family sandbox helper fix.
    #
    # Brave is installed by the apps wizard (paru/AUR `brave-bin`), not by the
    # installer, so the fix has to be waiting for it in the target. A pacman
    # hook is the one place that applies to every install path (wizard, manual
    # `paru -S`, future brew) — the wizard itself is a sha256-pinned vendored
    # tarball from the app-wiz4rd repo and is not ours to edit here.
    # chrome-sandbox must be root:root 4755 or Brave refuses to start; without
    # the setuid bit the browser is dead on arrival (2026-10-25 laptop install).
    info "Installing chrome-sandbox (Brave/Chromium) post-install fix..."
    install -Dm755 "$SCRIPT_DIR/hook-scripts/hook-chrome-sandbox.sh" \
        "rootfs/usr/local/bin/syntropia-fix-chrome-sandbox"
    mkdir -p "rootfs/etc/pacman.d/hooks"
    cat > "rootfs/etc/pacman.d/hooks/syntropia-chrome-sandbox.hook" << 'HOOKEOF'
[Trigger]
Operation = Install
Operation = Upgrade
Type = Path
Target = opt/brave.com/brave/chrome-sandbox
Target = usr/lib/brave/chrome-sandbox
Target = usr/lib/brave-bin/chrome-sandbox
Target = opt/google/chrome/chrome-sandbox
Target = usr/lib/chromium/chrome-sandbox

[Action]
Description = Syntropia: make chrome-sandbox a root-owned setuid helper (Brave/Chromium)
When = PostTransaction
Exec = /usr/local/bin/syntropia-fix-chrome-sandbox
HOOKEOF
    ok "chrome-sandbox fix hooked into pacman (carried into the installed target)"

    # Step 3.6b3: SSH setup helper for fresh installs (opt-in via wizard or CLI).
    info "Installing SSH setup helper (syntropia-ssh-setup)..."
    install -Dm755 "$SCRIPT_DIR/installer/lib/ssh-setup.sh" \
        "rootfs/usr/local/bin/syntropia-ssh-setup"
    ok "syntropia-ssh-setup installed to /usr/local/bin/syntropia-ssh-setup"

    # Step 3.6c: Pre-install Hyprland Noctalia packages into the ISO rootfs
    info "Pre-installing Hyprland Noctalia packages into ISO rootfs..."
    local hypr_pkgs=(
        cachyos-hypr-noctalia noctalia alacritty kitty
    )
    if command -v pacman >/dev/null 2>&1; then
        # Ensure DNS works inside rootfs chroot during build
        local resolv_backup=""
        if [[ -L "rootfs/etc/resolv.conf" ]]; then
            resolv_backup=$(readlink "rootfs/etc/resolv.conf")
            rm -f "rootfs/etc/resolv.conf"
        elif [[ -f "rootfs/etc/resolv.conf" ]]; then
            resolv_backup="file"
            mv "rootfs/etc/resolv.conf" "rootfs/etc/resolv.conf.bak"
        fi
        if [[ -f /run/systemd/resolve/resolv.conf ]]; then
            cp -L /run/systemd/resolve/resolv.conf "rootfs/etc/resolv.conf" 2>/dev/null || true
        else
            echo "nameserver 1.1.1.1" > "rootfs/etc/resolv.conf"
        fi
        echo -e "nameserver 1.1.1.1\nnameserver 8.8.8.8" >> "rootfs/etc/resolv.conf"

        # Populate host pacman keyring into rootfs so pacman can verify signatures
        if [[ -d /etc/pacman.d/gnupg ]]; then
            mkdir -p "rootfs/etc/pacman.d/gnupg"
            cp -a /etc/pacman.d/gnupg/. "rootfs/etc/pacman.d/gnupg/" 2>/dev/null || true
            rm -f "rootfs/etc/pacman.d/gnupg/S."*
            chmod 700 "rootfs/etc/pacman.d/gnupg"
        fi

        # Temporarily back up pacman.conf and ensure packages can be installed smoothly
        local pacman_conf_bak="rootfs/etc/pacman.conf.syntropia-bak"
        if [[ -f "rootfs/etc/pacman.conf" ]]; then
            cp "rootfs/etc/pacman.conf" "$pacman_conf_bak"
            sed -i 's/^SigLevel.*/SigLevel = Optional TrustAll/' "rootfs/etc/pacman.conf"
            sed -i 's/^LocalFileSigLevel.*/LocalFileSigLevel = Optional TrustAll/' "rootfs/etc/pacman.conf"
        fi

        info "Running pacman inside rootfs to bake Hyprland Noctalia suite..."
        # cachyos-hypr-noctalia conflicts with cachyos-kde-settings (both provide
        # cachyos-desktop-settings). Remove the KDE package first so the install
        # proceeds non-interactively.
        pacman -r "rootfs" -Rdd --noconfirm cachyos-kde-settings 2>/dev/null || true
        arch-chroot "rootfs" pacman -Rdd --noconfirm cachyos-kde-settings 2>/dev/null || true
        # Fix gstreamer/gst-plugins-base version conflict (1.28.6 vs 1.28.7):
        # remove the old libraries so 1.28.7 installs cleanly.
        pacman -r "rootfs" -Rdd --noconfirm \
            gst-plugins-base gst-plugins-good gst-plugins-base-libs gstreamer \
            2>/dev/null || true
        arch-chroot "rootfs" pacman -Rdd --noconfirm \
            gst-plugins-base gst-plugins-good gst-plugins-base-libs gstreamer \
            2>/dev/null || true
        arch-chroot "rootfs" pacman -Sy --noconfirm --needed --overwrite '*' "${hypr_pkgs[@]}" \
            || die "Could not pre-install Hyprland packages into rootfs"

        # cachyos-hypr-noctalia brings gnome-keyring as a dependency, but KWallet
        # (ksecretd) is Syntropia's Secret Service provider. Remove gnome-keyring
        # from the live rootfs so it does not compete or prompt for passwords.
        pacman -r "rootfs" -Rdd --noconfirm gnome-keyring 2>/dev/null || true
        arch-chroot "rootfs" pacman -Rdd --noconfirm gnome-keyring 2>/dev/null || true
        rm -f rootfs/usr/share/dbus-1/services/org.gnome.keyring*.service \
              rootfs/usr/share/dbus-1/services/org.freedesktop.secrets.service \
              rootfs/usr/share/xdg-desktop-portal/portals/gnome-keyring.portal \
              rootfs/etc/xdg/autostart/gnome-keyring*.desktop \
              rootfs/etc/systemd/user/sockets.target.wants/gnome-keyring-daemon.socket

        # Titlebar window buttons (hyprbars). Built here, while DNS and the
        # permissive pacman.conf from above are still in place.
        install_hyprbars_plugin "rootfs" || warn "Continuing without hyprbars (no titlebar buttons)"

        # Clean downloaded pacman cache from rootfs to keep ISO size lean
        rm -rf rootfs/var/cache/pacman/pkg/* 2>/dev/null || true

        # Restore original pacman.conf
        if [[ -f "$pacman_conf_bak" ]]; then
            mv "$pacman_conf_bak" "rootfs/etc/pacman.conf"
        fi

        # Restore original resolv.conf
        rm -f "rootfs/etc/resolv.conf"
        if [[ "$resolv_backup" == "file" ]]; then
            mv "rootfs/etc/resolv.conf.bak" "rootfs/etc/resolv.conf"
        elif [[ -n "$resolv_backup" ]]; then
            ln -sf "$resolv_backup" "rootfs/etc/resolv.conf"
        else
            ln -sf ../run/systemd/resolve/stub-resolv.conf "rootfs/etc/resolv.conf"
        fi

        if [[ -f "rootfs/usr/share/wayland-sessions/hyprland-uwsm.desktop" || -f "rootfs/usr/share/wayland-sessions/hyprland.desktop" || -f "rootfs/usr/bin/hyprland" ]]; then
            ok "Hyprland Noctalia packages successfully pre-installed in ISO rootfs"
        else
            die "Hyprland binary not found in rootfs after installation attempt"
        fi

        # Deploy Syntropia Hyprland & Noctalia overlay into live rootfs /etc/skel
        if [[ -d "$REPO_ROOT/iso/profiles/hyprland/.config" ]]; then
            mkdir -p "rootfs/etc/skel/.config"
            cp -r "$REPO_ROOT/iso/profiles/hyprland/.config/"* "rootfs/etc/skel/.config/" 2>/dev/null || true
            mkdir -p "rootfs/etc/skel/.config/noctalia" "rootfs/etc/skel/.local/state/noctalia"
            touch "rootfs/etc/skel/.config/noctalia/.setup-complete" "rootfs/etc/skel/.local/state/noctalia/.setup-complete"
            for n_cfg in "rootfs/etc/skel/.config/noctalia/config.toml" "rootfs/home/liveuser/.config/noctalia/config.toml"; do
                if [[ -f "$n_cfg" ]]; then
                    grep -q '^setup_wizard_enabled' "$n_cfg" || sed -i '/^\[shell\]/a setup_wizard_enabled = false' "$n_cfg"
                fi
            done
            if [[ -d "rootfs/home/liveuser" ]]; then
                mkdir -p "rootfs/home/liveuser/.config/noctalia" "rootfs/home/liveuser/.local/state/noctalia"
                touch "rootfs/home/liveuser/.config/noctalia/.setup-complete" "rootfs/home/liveuser/.local/state/noctalia/.setup-complete"
            fi
            ok "Syntropia Hyprland Noctalia overlay deployed to rootfs/etc/skel/.config"
        fi
    fi


    # Step 3.7: Make the wizard survive the INSTALL — Calamares builds a
    # fresh /etc for the target and does NOT copy our /etc/syntropia or the
    # autostart entry (observed: first boot of an installed system had no
    # wizard). Add a shellprocess step that runs in the live env (not the
    # chroot) right before umount and copies both into the target root.
    info "Wiring wizard copy into Calamares install..."
    cat > "rootfs/etc/calamares/modules/shellprocess_syntropia_wizard.conf" << 'WIZCONF'
---
dontChroot: true
timeout: 120
script:
    # Every command tees its full output (stdout+stderr) to a persistent log
    # on the TARGET (/var/log/syntropia-hooks.log of the installed system), so
    # a failed install leaves the real error on disk instead of only in the
    # live env's RAM. set -o pipefail keeps the original exit code so a
    # failing command still aborts the install as before.
    - command: "bash -c 'set -o pipefail; { echo \"=== syntropia_wizard:start $(date) ===\"; mkdir -p ${ROOT}/etc/syntropia && cp -a /etc/syntropia/. ${ROOT}/etc/syntropia/ && mkdir -p ${ROOT}/etc/xdg/autostart && cp -a /etc/syntropia/syntropia-apps.desktop ${ROOT}/etc/xdg/autostart/; echo \"=== syntropia_wizard:exit $? ===\"; } 2>&1 | tee -a ${ROOT}/var/log/syntropia-hooks.log'"
      timeout: 120
      verbose: true
WIZCONF

    # Register the instance and add it to the exec sequence, in BOTH the
    # online and offline settings (calamares-online.sh copies settings_online
    # to /etc/calamares/settings.conf at launch; both are NoUpgrade-protected
    # above so the boot-time package update can't clobber them).
    python3 - "rootfs" << 'PYEOF'
import sys, pathlib
root = pathlib.Path(sys.argv[1])
for name in ("settings_online.conf", "settings_offline.conf"):
    p = root / "usr/share/calamares" / name
    if not p.exists():
        continue
    text = p.read_text()
    marker = "# Syntropia: copy the apps wizard into the installed system"
    if marker in text:
        continue
    instance = (
        "\n- id:       syntropia_wizard\n"
        "  module:   shellprocess\n"
        "  config:   shellprocess_syntropia_wizard.conf\n"
    )
    text = text.replace("\n\nsequence:", instance + "\nsequence:")
    text = text.replace("- shellprocess@enable_ufw",
                        "- shellprocess@enable_ufw\n  - shellprocess@syntropia_wizard")
    p.write_text(text)
PYEOF
    # Replace the stock CachyOS first-boot welcome: cachyos-hello auto-opens
    # for new users via /etc/skel/.config/autostart/. Drop that entry so OUR
    # wizard (shipped via /etc/xdg/autostart above) is the first-boot picker.
    # cachyos-hello stays installed and available from the app menu.
    rm -f rootfs/etc/skel/.config/autostart/cachyos-hello.desktop
    ok "Wizard copy wired into Calamares; cachyos-hello first-run removed"

    # Step 3.7b: Ship paru and limine with EVERY install. The Calamares
    # bootloader step and a future `limine bios-install` need the package on
    # the target, and the first-boot wizard must never show the "paru is not
    # installed" bootstrap. The installed system is NOT a copy of the live
    # rootfs — Calamares pacstraps a fresh base from pacstrap.conf's
    # basePackages (paru/limine live only in the live packages list, so they
    # never reach the target). Add both to basePackages here;
    # NoUpgrade-protected above so the live-boot cachyos-calamares-next
    # update can't revert it (same pattern as the settings files).
    info "Adding paru + limine to pacstrap basePackages..."
    local pacstrap_conf="rootfs/etc/calamares/modules/pacstrap.conf"
    if [[ -f "$pacstrap_conf" ]]; then    # Insert into the basePackages list ONLY (the file has a second list,
    # postInstallFiles, whose entries are also '  - ' — appending after the
    # last such line would put a package in the WRONG list). Scan forward from
    # 'basePackages:' until the next top-level key and append there.
    python3 - "$pacstrap_conf" << 'PYEOF'
import sys, re
path = sys.argv[1]
with open(path) as f:
    lines = f.readlines()
start = next(i for i, l in enumerate(lines) if l.strip() == 'basePackages:')
insert_at = None
for i in range(start + 1, len(lines)):
    l = lines[i]
    if re.match(r'^[A-Za-z][A-Za-z0-9]*:', l):  # next top-level key
        insert_at = i
        break
assert insert_at is not None, "basePackages list has no end in pacstrap.conf"
added = []
for pkg in ("paru", "limine"):
    if f"  - {pkg}\n" in lines:
        continue
    lines.insert(insert_at, f"  - {pkg}\n")
    insert_at += 1
    added.append(pkg)
with open(path, 'w') as f:
    f.writelines(lines)
print(", ".join(added) if added else "none")
PYEOF
        ok "paru + limine in pacstrap basePackages (every install ships them)"
    else
        ok "pacstrap.conf missing — paru/limine left out of the target package set"
    fi

    # Step 3.8: Ship the terminal ASCII-art branding so fresh installs show
    # the Syntropia logo in fastfetch's fish greeting WITHOUT needing
    # `syntropia transform` first (observed: a fresh install ran stock
    # fastfetch because /usr/share/syntropia/logo.txt + the fastfetch config
    # only exist after transform). We ship the same files transform writes:
    #   /usr/share/syntropia/logo.txt            (the 4* triangle art)
    #   /usr/share/syntropia/branding/fastfetch-color.json (color map)
    #   /etc/skel/.config/fastfetch/config.jsonc (fastfetch picks this up
    #       automatically on login; fish_greeting runs `fastfetch`)
    # The fastfetch config is generated by the repo's OWN build_fastfetch_conf
    # (imported from phase1/cli) so the ISO and `syntropia transform` can't
    # drift apart — same single source of truth.
    info "Shipping terminal ASCII-art branding (fastfetch logo)..."
    local brand_src="$REPO_ROOT/Branding/syntropia"
    local logo_dir="rootfs/usr/share/syntropia"
    mkdir -p "$logo_dir/branding"
    cp "$brand_src/logo.txt" "$logo_dir/logo.txt"
    cp "$brand_src/fastfetch-color.json" "$logo_dir/branding/fastfetch-color.json"
    # Start-menu (Kickoff) icon: ships as menu-icon.png and gets installed
    # into the hicolor theme + repointed in the panel config by the branding
    # hook (single source of truth with apply_menu_icon in branding.py).
    cp "$brand_src/menu-icon.png" "$logo_dir/branding/menu-icon.png"
    # Desktop wallpaper: referenced by the Hyprland profile's hyprpaper.conf
    # and hyprlock.conf (/usr/share/syntropia/branding/wallpaper.png).
    cp "$brand_src/wallpaper.png" "$logo_dir/branding/wallpaper.png"
    # KSplash theme: ships as splash/ (Splash.qml + images) and gets installed
    # into the target's look-and-feel + ksplashrc by the branding hook (single
    # source of truth with apply_splash in branding.py).
    cp -r "$brand_src/splash" "$logo_dir/branding/splash"
    mkdir -p "rootfs/etc/skel/.local/share/plasma/look-and-feel/org.syntropia.desktop/contents/splash"
    cp -a "$brand_src/splash/." "rootfs/etc/skel/.local/share/plasma/look-and-feel/org.syntropia.desktop/contents/splash/"
    mkdir -p "rootfs/etc/skel/.config"
    printf '[KSplash]\nEngine=none\nTheme=None\n' > "rootfs/etc/skel/.config/ksplashrc"
    # Plymouth boot animation: ships as plymouth/ (triangle particle swarm) and
    # gets installed to /usr/share/plymouth/themes/syntropia + set active by the
    # branding hook (single source of truth with apply_plymouth).
    cp -r "$brand_src/plymouth" "$logo_dir/branding/plymouth"
    mkdir -p "rootfs/usr/share/plymouth/themes/syntropia"
    cp -a "$brand_src/plymouth/." "rootfs/usr/share/plymouth/themes/syntropia/"
    mkdir -p "rootfs/etc/plymouth"
    printf '[Daemon]\nTheme=syntropia\n' > "rootfs/etc/plymouth/plymouthd.conf"
    mkdir -p "rootfs/etc/skel/.config/fastfetch"
    # Run from the remaster dir (cwd) but import the repo's config builder
    # via PYTHONPATH — same single source of truth as `syntropia transform`.
    # NOTE: python3 -c only runs the FIRST argument; later args become
    # sys.argv and silently produce empty output. Use a heredoc instead so
    # the whole program is one stdin stream.
    PYTHONPATH="$REPO_ROOT/phase1/cli:$REPO_ROOT/phase1/cli/transform" python3 - \
        "$REPO_ROOT/Branding/syntropia/fastfetch-color.json" \
      > rootfs/etc/skel/.config/fastfetch/config.jsonc 2>/dev/null << 'PYEOF' || true
import json, sys
from syntropia_transform.transform import build_fastfetch_conf
cm = json.load(open(sys.argv[1]))
print(build_fastfetch_conf(cm), end="")
PYEOF
    if [[ -s rootfs/etc/skel/.config/fastfetch/config.jsonc ]]; then
        ok "ASCII art shipped (/usr/share/syntropia/ + skel fastfetch config)"
    else
        warn "fastfetch config empty — ASCII art not shipped"
    fi

    # os-release + lsb-release: extract the pinned identity from transform.py
    # (single source of truth — test_transform.py asserts OS_RELEASE_CONTENT)
    # so the ISO and `syntropia transform` can never disagree on the name.
    info "Generating os-release + lsb-release from transform.py..."
    python3 - "$REPO_ROOT/phase1/cli/transform/syntropia_transform/transform.py" "$logo_dir/branding" << 'PYEOF'
import ast, pathlib, sys
src = pathlib.Path(sys.argv[1]).read_text()
out = pathlib.Path(sys.argv[2])
content = None
for node in ast.parse(src).body:
    if isinstance(node, ast.Assign) and any(
        getattr(t, "id", "") == "OS_RELEASE_CONTENT" for t in node.targets
    ):
        if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
            content = node.value.value
        elif isinstance(node.value, ast.Tuple):
            content = "".join(
                elt.value for elt in node.value.elts
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            )
        break
if content is None:
    sys.exit("OS_RELEASE_CONTENT not found in transform.py")
(out / "os-release").write_text(content)
(out / "lsb-release").write_text(
    "LSB_VERSION=1.4\n"
    'DISTRIB_ID="CachyOS"\n'
    "DISTRIB_RELEASE=rolling\n"
    'DISTRIB_DESCRIPTION="CachyOS Syntropia"\n'
    'DISTRIB_CODENAME="syntropia"\n'
)
PYEOF
    if [[ -s "$logo_dir/branding/os-release" ]]; then
        ok "os-release + lsb-release generated"
    else
        err "os-release generation failed"
    fi

    # Default hostname: Calamares auto-suggests "cachyos-${cpu}" — rebrand the
    # default to "syntropia-${cpu}" (the user can still type their own).
    local users_conf="rootfs/etc/calamares/modules/users.conf"
    if [[ -f "$users_conf" ]]; then
        sed -i 's/template: "cachyos-/template: "syntropia-/' "$users_conf"
        ok "users.conf hostname default -> syntropia"
    else
        warn "users.conf not found — hostname default left as cachyos"
    fi

    # Step 3.9: Make the branding survive the INSTALL too — Calamares builds
    # the target from packages and does NOT copy unpacakged files like our
    # /usr/share/syntropia. Extend the existing shellprocess hook (which runs
    # in the live env, not the chroot) to copy the logo + skel config into the
    # target root as well.
    info "Wiring branding copy into Calamares install..."
    cat > "rootfs/etc/calamares/modules/shellprocess_syntropia_branding.conf" << 'BRANDCONF'
---
dontChroot: true
timeout: 180
script:
    # 1) copy the logo + fastfetch config into the target's /usr/share and
    #    /etc/skel (for FUTURE users), and
    # 2) also copy the fastfetch config + fish greeting into EXISTING target
    #    user homes. Calamares creates the user BEFORE this hook runs, so
    #    skel-only writes never reach the first user (observed: fresh install
    #    had /etc/skel/.config/fastfetch but an empty ~/.config/fastfetch).
    # Every command tees to /var/log/syntropia-hooks.log on the target (see
    # the wizard hook for why).
    #
    # !!! IMPORTANT — Calamares macro-expands every command string with
    # KWordMacroExpander('$'), which expands BARE $word (not only ${word}).
    # Any shell variable written as $foo in a command is treated as an
    # undefined macro and the WHOLE job fails with "Missing variables" BEFORE
    # running anything. Never put bare $vars in a hook command — put shell
    # logic in a script (see /etc/syntropia/hook-branding-users.sh below).
    - command: "bash -c 'set -o pipefail; { echo \"=== syntropia_branding:start $(date) ===\"; mkdir -p ${ROOT}/usr/share/syntropia/branding && cp -a /usr/share/syntropia/. ${ROOT}/usr/share/syntropia/ && cp -a /usr/share/syntropia/branding/os-release ${ROOT}/etc/os-release && cp -a /usr/share/syntropia/branding/lsb-release ${ROOT}/etc/lsb-release && mkdir -p ${ROOT}/etc/skel/.config/fastfetch && cp -a /etc/skel/.config/fastfetch/config.jsonc ${ROOT}/etc/skel/.config/fastfetch/; echo \"=== syntropia_branding:exit $? ===\"; } 2>&1 | tee -a ${ROOT}/var/log/syntropia-hooks.log'"
      timeout: 120
      verbose: true
    - command: "bash -c 'set -o pipefail; { echo \"=== syntropia_branding:home-users:start $(date) ===\"; bash /etc/syntropia/hook-branding-users.sh \"${ROOT}\"; echo \"=== syntropia_branding:home-users:exit $? ===\"; } 2>&1 | tee -a ${ROOT}/var/log/syntropia-hooks.log'"
      timeout: 60
      verbose: true
BRANDCONF
    python3 - "rootfs" << 'PYEOF'
import sys, pathlib
root = pathlib.Path(sys.argv[1])
for name in ("settings_online.conf", "settings_offline.conf"):
    p = root / "usr/share/calamares" / name
    if not p.exists():
        continue
    text = p.read_text()
    marker = "# Syntropia: copy the terminal branding into the installed system"
    if marker in text:
        continue
    instance = (
        "\n- id:       syntropia_branding\n"
        "  module:   shellprocess\n"
        "  config:   shellprocess_syntropia_branding.conf\n"
    )
    text = text.replace("\n\nsequence:", instance + "\nsequence:")
    text = text.replace("- shellprocess@syntropia_wizard",
                        "- shellprocess@syntropia_wizard\n  - shellprocess@syntropia_branding")
    p.write_text(text)
PYEOF
    ok "Branding copy wired into Calamares"

    # Step 3.9b: Verify the Limine install the Calamares bootloader module made.
    # That module is CachyOS' (limine.conf + `limine bios-install` + efibootmgr),
    # so the check runs immediately after it and before umount: a disk that
    # would not boot fails the install here, with the reason on the target in
    # /var/log/syntropia-hooks.log, instead of at the next reboot. The checks
    # are in hook-limine.sh.
    info "Wiring the Limine bootloader check into Calamares install..."
    cat > "rootfs/etc/calamares/modules/shellprocess_syntropia_limine.conf" << 'LIMINECONF'
---
dontChroot: true
timeout: 180
script:
    # Runs in the LIVE env with ${ROOT} = the target mount point. All logic is
    # in /etc/syntropia/hook-limine.sh — a command string cannot hold shell
    # variables (KWordMacroExpander expands them, see the branding hook).
    # A non-zero exit aborts the install on purpose: an unbootable disk is
    # worse than a failed install.
    - command: "bash /etc/syntropia/hook-limine.sh ${ROOT}"
      timeout: 180
      verbose: true
LIMINECONF
    python3 - "rootfs" << 'PYEOF'
import sys, pathlib
root = pathlib.Path(sys.argv[1])
for name in ("settings_online.conf", "settings_offline.conf"):
    p = root / "usr/share/calamares" / name
    if not p.exists():
        continue
    text = p.read_text()
    if "- id:       syntropia_limine" in text:
        continue
    instance = (
        "\n- id:       syntropia_limine\n"
        "  module:   shellprocess\n"
        "  config:   shellprocess_syntropia_limine.conf\n"
    )
    text = text.replace("\n\nsequence:", instance + "\nsequence:")
    # Right after the bootloader module — that is the step this verifies.
    if "- shellprocess@syntropia_limine" not in text:
        text = text.replace("- bootloader\n",
                            "- bootloader\n  - shellprocess@syntropia_limine\n", 1)
    p.write_text(text)
PYEOF
    ok "Limine bootloader check wired into Calamares"

    # Step 3.85: Rebrand Calamares installer, strip generic multi-OS chooser, and disable cachyos-hello
    info "Patching Calamares to offer Syntropia only (removing generic multi-OS/desktop choosers)..."
    for bdesc in rootfs/usr/share/calamares/branding/*/branding.desc rootfs/etc/calamares/branding/*/branding.desc; do
        if [[ -f "$bdesc" ]]; then
            sed -i 's/productName: .*/productName: Syntropia OS/' "$bdesc"
            sed -i 's/shortProductName: .*/shortProductName: Syntropia/' "$bdesc"
            sed -i 's/versionedName: .*/versionedName: Syntropia OS/' "$bdesc"
            sed -i 's/shortVersionedName: .*/shortVersionedName: Syntropia/' "$bdesc"
            sed -i 's/bootloaderEntryName: .*/bootloaderEntryName: Syntropia/' "$bdesc"
            sed -i 's/windowPlacement: .*/windowPlacement: center/' "$bdesc"
            sed -i 's/windowExpanding: .*/windowExpanding: normal/' "$bdesc"
        fi
    done

    # Center installer windows via KWin window manager rules and configuration
    info "Configuring KWin to center installer windows..."
    for kwin_dir in "rootfs/etc/skel/.config" "rootfs/home/liveuser/.config"; do
        mkdir -p "$kwin_dir"
        if [[ -f "$kwin_dir/kwinrc" ]] && grep -q '\[Windows\]' "$kwin_dir/kwinrc"; then
            sed -i '/\[Windows\]/a Placement=Centered' "$kwin_dir/kwinrc"
        else
            printf '\n[Windows]\nPlacement=Centered\n' >> "$kwin_dir/kwinrc"
        fi
        cat > "$kwin_dir/kwinrulesrc" << 'EOF'
[1]
Description=Center Calamares Installer
clientmachine=localhost
clientmachinematch=0
placement=3
placementrule=2
wmclass=calamares
wmclassmatch=1
EOF
    done
    ok "KWin configured to open installer in center of screen"

    # Configure the Calamares bootloader module for LIMINE — the same
    # bootloader syntropia-install-runner installs (see NEXT_SESSION.md), so
    # both install paths produce a Limine-booting system.
    #
    # This block used to force systemd-boot as a workaround for the 82%
    # "Configuring Limine bootloader & kernel" freeze. That freeze
    # was the limine package missing from the image, not Limine being broken:
    # the live rootfs (Patch 1b) and pacstrap basePackages (Step 3.7b) now both
    # ship it. Forcing the value (instead of trusting CachyOS' default) keeps a
    # future upstream default change from silently putting systemd-boot back on
    # Calamares installs.
    #
    # CachyOS' partition.conf keys off this choice too (`bootloaderOverrides:
    # name: limine` → ESP at /boot, matching the runner's layout), which is why
    # the loader must be selected here and not only at install time.
    info "Configuring Calamares bootloader module for Limine..."
    for bconf in rootfs/etc/calamares/modules/bootloader.conf rootfs/usr/share/calamares/modules/bootloader.conf; do
        if [[ -f "$bconf" ]]; then
            sed -i 's/efiBootLoader: .*/efiBootLoader: "limine"/' "$bconf"
            # The bootloader picker (packagechooser instance) is removed from the
            # exec sequence, so its global-storage override is never set; an
            # empty value means "use efiBootLoader" unambiguously.
            sed -i 's/efiBootLoaderVar: .*/efiBootLoaderVar: ""/' "$bconf"
            # EFI directory under the ESP (\EFI\syntropia\) + NVRAM label source.
            sed -i 's/efiBootloaderId: .*/efiBootloaderId: "syntropia"/' "$bconf"
            sed -i 's/installEFIFallback: .*/installEFIFallback: true/' "$bconf"
            # Boot-menu background: the Syntropia wallpaper instead of CachyOS'.
            # Wallpaper.png is in the live rootfs (Step 3.8 ships it).
            sed -i 's|limineSplashLogo: .*|limineSplashLogo: "/usr/share/syntropia/branding/wallpaper.png"|' "$bconf"
        fi
    done
    ok "Calamares bootloader configured to Limine"

    # Configure unpackfs to copy both default and LTS kernels
    for uconf in rootfs/etc/calamares/modules/unpackfs.conf rootfs/usr/share/calamares/modules/unpackfs.conf; do
        if [[ -f "$uconf" ]] && ! grep -q 'vmlinuz-linux-cachyos-lts' "$uconf"; then
            python3 - "$uconf" << 'PYEOF'
import sys
p = sys.argv[1]
with open(p) as f:
    text = f.read()
target = 'destination: "/boot/vmlinuz-linux-cachyos"'
lts_entry = '''    -   source: "/run/archiso/bootmnt/arch/boot/x86_64/vmlinuz-linux-cachyos-lts"
        sourcefs: "file"
        destination: "/boot/vmlinuz-linux-cachyos-lts"
        optional: true'''
if target in text:
    text = text.replace(target, target + "\n" + lts_entry)
    with open(p, "w") as f:
        f.write(text)
PYEOF
        fi
    done

    # Remove packagechooser (desktop/bootloader) and netinstall from Calamares sequence
    python3 - "rootfs" << 'PYEOF'
import sys, pathlib
root = pathlib.Path(sys.argv[1])
for name in ("settings_online.conf", "settings_offline.conf", "settings.conf"):
    p = root / "usr/share/calamares" / name
    if not p.exists():
        continue
    lines = p.read_text().splitlines()
    filtered = []
    for line in lines:
        stripped = line.strip()
        if stripped in ("- packagechooser@desktop", "- packagechooser@bootloader", "- netinstall", "packagechooser@desktop", "packagechooser@bootloader", "netinstall"):
            continue
        filtered.append(line)
    p.write_text("\n".join(filtered) + "\n")

pk = root / "etc/calamares/modules/packagechooser_desktop.conf"
if pk.exists():
    pk_text = """---
mode: required
method: legacy
default: Syntropia-Desktop
items:
    - id: Syntropia-Desktop
      name: "Syntropia OS"
      description: "Syntropia OS with customized desktop, CLI brews, and dark theme."
      screenshot: "/etc/calamares/images/kde.webp"
"""
    pk.write_text(pk_text)
PYEOF

    # Configure finished page to keep restart unchecked so user can read USB removal prompt
    for fconf in rootfs/etc/calamares/modules/finished.conf rootfs/usr/share/calamares/modules/finished.conf; do
        if [[ -f "$fconf" ]]; then
            sed -i 's/notifyOnFinished: .*/notifyOnFinished: true/' "$fconf"
            sed -i 's/restartNowMode: .*/restartNowMode: user-unchecked/' "$fconf"
        fi
    done

    # Patch calamares-online.sh launcher to use offline unpackfs & drop live-boot pacman clobber
    if [[ -f "rootfs/usr/local/bin/calamares-online.sh" ]]; then
        sed -i 's/sudo pacman -Sy --noconfirm cachyos-calamares-next/# skipped offline/' "rootfs/usr/local/bin/calamares-online.sh"
        sed -i 's/sudo pacman -Sy --noconfirm archlinux-keyring cachyos-keyring/# skipped offline/' "rootfs/usr/local/bin/calamares-online.sh"
        sed -i 's/local mode="online"/local mode="offline"/' "rootfs/usr/local/bin/calamares-online.sh"
        ok "calamares-online.sh patched (offline unpackfs default, zero network stall)"
    fi

    # Clean up any desktop / autostart installer icons from rootfs
    rm -f rootfs/home/liveuser/Desktop/install-syntropia.desktop
    rm -f rootfs/etc/skel/Desktop/install-syntropia.desktop
    rm -f rootfs/home/liveuser/.config/autostart/install-syntropia.desktop
    rm -f rootfs/etc/skel/.config/autostart/install-syntropia.desktop
    rm -f rootfs/home/liveuser/.config/autostart/cachyos-hello.desktop
    rm -f rootfs/etc/skel/.config/autostart/cachyos-hello.desktop
    rm -f rootfs/etc/xdg/autostart/cachyos-hello.desktop
    ok "Live desktop icons removed; multi-OS chooser removed; cachyos-hello disabled"

    # Step 3.94: Patch the live image's DRM module awaiter generator.
    # CachyOS's generator (shipped by the live image) cannot see a
    # `module_blacklist=` on the kernel command line, so on the default entry —
    # which blacklists the nvidia modules — it still puts nvidia_drm in the DRM
    # target and the target times out without a display (pre-Turing cards have
    # no nvidia-open support at all). iso/lib/drm-module-awaiter-generator is
    # that generator patched to honour the cmdline blacklist, force nouveau when
    # nvidia is blacklisted, detect pre-Turing GPUs via sysfs, and generate no
    # target at all under `nomodeset`. It was an untracked leftover of the lost
    # boot fix; shipping it from here is what makes it part of the build.
    local awaiter_src="$SCRIPT_DIR/lib/drm-module-awaiter-generator"
    local awaiter_dst="rootfs/usr/lib/systemd/system-generators/drm-module-awaiter-generator"
    if [[ -f "$awaiter_src" ]]; then
        install -Dm755 "$awaiter_src" "$awaiter_dst"
        ok "DRM module awaiter patched (cmdline blacklist + nomodeset aware)"
    else
        warn "iso/lib/drm-module-awaiter-generator missing — live NVIDIA fallback stays stock"
    fi

    # Step 3.95: Optimize ISO bootloader (faster boot, lower timeout, Syntropia title, direct multi-user)
    info "Patching ISO bootloader configurations..."
    if [[ -f "boot/grub/grub.cfg" ]]; then
        sed -i 's/timeout=10/timeout=2/' "boot/grub/grub.cfg"
        sed -i 's/Welcome to CachyOS/Welcome to Syntropia/' "boot/grub/grub.cfg"
        sed -i 's/menuentry "CachyOS LTS Kernel"/menuentry "Syntropia (LTS Kernel)"/' "boot/grub/grub.cfg"
        sed -i 's/menuentry "CachyOS Legacy Hardware (GPU nomodeset)"/menuentry "Syntropia (Safe Graphics \/ nomodeset)"/' "boot/grub/grub.cfg"
        sed -i 's/menuentry "CachyOS"/menuentry "Syntropia"/' "boot/grub/grub.cfg"
        sed -i -E 's/copytoram=auto/copytoram=auto systemd.unit=multi-user.target/g' "boot/grub/grub.cfg"
        if [[ -n "${orig_uuid:-}" ]]; then
            sed -i -E "s/archisosearchuuid=[^ ]+/archisosearchuuid=$orig_uuid/g" "boot/grub/grub.cfg"
        fi
        # Kernel arguments + the NVIDIA-Open entry. Done in one pass in
        # iso/lib/iso-boot-config.py because it is structural (entry blocks),
        # not line-oriented: the default entry gets the full nvidia blacklist
        # (pre-Turing cards have no nvidia-open support and hang without a
        # DRM device), the LTS entry mirrors it, the Turing+ entry drops it,
        # and `nomodeset` stays exactly as shipped. The same pass normalises
        # any `}}` menuentry closer — the USB-boot bug, which
        # grub-script-check does NOT report.
        "$SCRIPT_DIR/lib/iso-boot-config.py" patch-grub boot/grub/grub.cfg \
            || err "Could not patch boot/grub/grub.cfg (GRUB kernel args + NVIDIA entry)"
        ok "ISO GRUB configuration optimized (timeout 2s, direct multi-user, UUID synced, NVIDIA entries)"
    fi
    if [[ -f "boot/syslinux/archiso_sys.cfg" ]]; then
        sed -i 's/TIMEOUT 150/TIMEOUT 30/' "boot/syslinux/archiso_sys.cfg"
        ok "ISO Syslinux timeout set to 3s"
    fi
    for f in boot/syslinux/archiso_*.cfg; do
        if [[ -f "$f" ]]; then
            sed -i 's/MENU LABEL CachyOS default (x86_64, BIOS)/MENU LABEL Syntropia default (x86_64, BIOS)/g' "$f"
            sed -i 's/MENU LABEL CachyOS Fallback (nomodeset, BIOS)/MENU LABEL Syntropia Fallback (nomodeset, BIOS)/g' "$f"
            sed -i 's/MENU TITLE CachyOS/MENU TITLE Syntropia/g' "$f"
            sed -i 's/Boot the CachyOS install medium/Boot the Syntropia install medium/g' "$f"
            sed -i 's/install CachyOS/install Syntropia/g' "$f"
            sed -i -E 's/copytoram=auto/copytoram=auto systemd.unit=multi-user.target/g' "$f"
            if [[ -n "${orig_uuid:-}" ]]; then
                sed -i -E "s/archisosearchuuid=[^ ]+/archisosearchuuid=$orig_uuid/g" "$f"
            fi
        fi
    done
    ok "ISO Syslinux rebranded to Syntropia"

    # BIOS path: the same entries as GRUB, in the menu archiso_sys.cfg
    # includes (archiso_sys-linux.cfg holds the LABEL blocks). Runs after the
    # rebranding loop above so the derived NVIDIA entry inherits the Syntropia
    # labels, UUID and multi-user target.
    if [[ -f "boot/syslinux/archiso_sys-linux.cfg" ]]; then
        "$SCRIPT_DIR/lib/iso-boot-config.py" patch-syslinux boot/syslinux/archiso_sys-linux.cfg \
            || err "Could not patch boot/syslinux/archiso_sys-linux.cfg (BIOS kernel args + NVIDIA entry)"
        ok "BIOS (syslinux) entries patched (same NVIDIA blacklist as GRUB)"
    else
        warn "boot/syslinux/archiso_sys-linux.cfg missing — BIOS menu not patched"
    fi

    # Guard: the boot configs about to be packed must be valid. `grub-script-check`
    # is NOT enough — it accepts the `}}` closers that broke every USB boot
    # (2026-10-24), so the check below looks for exactly that shape and for a
    # menuentry that never closes, and names the file and line.
    info "Validating bootloader configuration syntax..."
    "$SCRIPT_DIR/lib/iso-boot-config.py" check boot \
        || err "Invalid bootloader configuration — refusing to build an unbootable ISO (see the file:line above)"
    ok "Boot configs validated (single-brace menuentry closers, no doubled-brace lines)"

    # Step 4: Repack squashfs with zstd (9x faster page decompression than xz)
    info "Repacking squashfs with zstd (high decompression throughput)..."
    rm -f arch/x86_64/airootfs.sfs
    # A killed run leaves the chroot mounts behind; repacking over them would
    # pull the host's /proc and /sys into the image (~100 MB of nonsense and an
    # unbootable live system). Drop them before the pack AND before any cleanup
    # that ever touches the rootfs.
    lazy_umount_rootfs rootfs
    local nproc_limit
    nproc_limit="$(nproc 2>/dev/null || echo 4)"
    nproc_limit=$(( nproc_limit > 4 ? 4 : nproc_limit ))
    # zstd level 15, not 19: -19 costs ~45-70 min of the build on the 16 GB /
    # 4-core box for a compression gain that live boot never notices (boot time
    # is dominated by single-threaded kernel page decompression, which is the
    # same at both levels). The excludes keep the kernel filesystems out of the
    # pack even if a mount survives the lazy unmount.
    mksquashfs rootfs/ arch/x86_64/airootfs.sfs \
        -comp zstd -Xcompression-level 15 -b 1M -noappend \
        -processors "$nproc_limit" -mem 4G \
        -e proc sys dev run
    ok "Squashfs repacked ($(du -sh arch/x86_64/airootfs.sfs | cut -f1))"

    # Step 4.5: Kernel mounts can reappear between the pack and the cleanup
    # (a failed mksquashfs leaves the tree mounted); unmount again so the
    # `rm -rf` below deletes the rootfs, not the host's /proc and /sys.
    lazy_umount_rootfs rootfs

    # Step 5: Update checksum
    cd arch/x86_64
    sha512sum airootfs.sfs > airootfs.sha512
    cd "$remaster_dir"
    ok "Checksum updated"

    # Step 5.5: Remove the unsquashed rootfs to keep ISO size reasonable
    # (the remaster dir becomes the ISO root; we only need the packaged sfs)
    info "Cleaning up unsquashed rootfs..."
    lazy_umount_rootfs rootfs
    rm -rf rootfs
    ok "Cleaned rootfs ($(du -sh . | cut -f1) remaining)"

    # Step 6: Rebuild hybrid ISO with xorriso
    info "Rebuilding ISO with xorriso..."
    local xorriso_args=(
        -as mkisofs
        -iso-level 3
        -full-iso9660-filenames
        -joliet
        -joliet-long
        -rational-rock
        -volid "SYNTROPIA"
        -appid "Syntropia Live/Rescue DVD"
        -publisher "Syntropia OS"
        -eltorito-boot boot/syslinux/isolinux.bin
        -eltorito-catalog boot/syslinux/boot.cat
        -no-emul-boot -boot-load-size 4 -boot-info-table
        -isohybrid-mbr boot/syslinux/isohdpfx.bin
        -partition_offset 16
        -append_partition 2 0xef "$efiboot_img"
        -isohybrid-gpt-basdat
        -eltorito-alt-boot
        -e '--interval:appended_partition_2:all::'
        -no-emul-boot
    )

    if [[ -n "${orig_mod_date:-}" ]]; then
        xorriso_args+=( --modification-date="$orig_mod_date" )
    fi

    xorriso "${xorriso_args[@]}" -output "$output_iso" .
    rm -f "$efiboot_img"

    verify_installer_libs "$output_iso"

    ok "Phase 2 complete: $output_iso ($(du -h "$output_iso" | cut -f1))"
    info "Your Syntropia-branded CachyOS installer ISO is ready!"
    info "  $output_iso"
}

# ── Installer-lib staleness guard ─────────────────────────────
# The Oct-26 laptop failure shipped an ISO whose embedded keyring.sh predated
# the repo fix — the stick tested an old installer while the tree said FIXED.
# After every ISO is assembled, pull the embedded installer libs back out of
# the image and byte-compare them with the repo copies. A mismatch fails the
# build instead of masquerading as a fix on the next install.
verify_installer_libs() {
    local output_iso="$1"
    local extract_dir lib rel
    extract_dir="$(mktemp -d /tmp/syntropia-verify.XXXXXX)"
    info "Verifying embedded installer libraries match the repo..."
    bsdtar -xf "$output_iso" -C "$extract_dir" arch/x86_64/airootfs.sfs
    local -a paths=()
    for lib in "$SCRIPT_DIR"/installer/lib/*.sh; do
        paths+=("usr/local/lib/syntropia-installer/$(basename "$lib")")
    done
    paths+=("usr/local/bin/syntropia-ssh-setup")
    unsquashfs -n -f -d "$extract_dir/rootfs" \
        "$extract_dir/arch/x86_64/airootfs.sfs" "${paths[@]}" >/dev/null 2>&1
    for lib in "$SCRIPT_DIR"/installer/lib/*.sh; do
        rel="usr/local/lib/syntropia-installer/$(basename "$lib")"
        [[ -f "$extract_dir/rootfs/$rel" ]] \
            || err "ISO verification: $rel missing from the built image"
        cmp -s "$lib" "$extract_dir/rootfs/$rel" \
            || err "stale installer lib in the built ISO: iso/installer/lib/$(basename "$lib") does not match what shipped — the image would install yesterday's installer. Rebuild from the current tree."
    done
    rel="usr/local/bin/syntropia-ssh-setup"
    [[ -f "$extract_dir/rootfs/$rel" ]] \
        || err "ISO verification: $rel missing from the built image"
    cmp -s "$SCRIPT_DIR/installer/lib/ssh-setup.sh" "$extract_dir/rootfs/$rel" \
        || err "stale installer helper in the built ISO: $rel does not match iso/installer/lib/ssh-setup.sh — the image would install yesterday's helper. Rebuild from the current tree."
    rm -rf "$extract_dir"
    ok "embedded installer libs match the repo ($(basename -a "$SCRIPT_DIR"/installer/lib/*.sh | tr '\n' ' ')usr/local/bin/syntropia-ssh-setup)"
}

# ── Main ───────────────────────────────────────────────────────
main() {
    check_root
    check_deps

    mkdir -p "$WORK_DIR" "$OUT_DIR"

    case "$PHASE" in
        --phase1|phase1)
            phase1_build_iso
            ;;
        --phase2|phase2)
            phase2_inject_slides
            ;;
        all|--all)
            # Clean any previous remaster workdir
            rm -rf "$WORK_DIR/remaster"
            phase1_build_iso
            phase2_inject_slides
            ;;
        *)
            echo "Usage: sudo ./build.sh [--phase1|--phase2|all]"
            echo ""
            echo "  all       Full pipeline: build stock ISO, inject Syntropia slides (default)"
            echo "  --phase1  Only run mkarchiso build (produces standard CachyOS ISO)"
            echo "  --phase2  Only inject slides into an existing stock ISO"
            exit 1
            ;;
    esac
}

main
