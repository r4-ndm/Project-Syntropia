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

# Branding source: slides live in the repo under Branding/
BRANDING_SRC="$REPO_ROOT/Branding/syntropia/calamares/usr/share/calamares/branding/cachyos"

ISO_DATE="${SOURCE_DATE_EPOCH:-$(date +%s)}"
ISO_DATE=$(date --date="@$ISO_DATE" +%Y.%m.%d)
ISO_NAME="syntropia-${ISO_DATE}-x86_64"

PHASE="${1:-all}"

# ── Color helpers ──────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}[INFO]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

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

    # ── Build with mkarchiso ──
    info "Running mkarchiso (this downloads ~990 packages on first run)..."
    mkarchiso -v -w "$WORK_DIR/mkarchiso-work" -o "$OUT_DIR" "$CACHYOS_PROFILE_DIR"

    # mkarchiso names it cachyos-YYYY.MM.DD-x86_64.iso — rename to syntropia
    local stock_iso="$OUT_DIR/cachyos-${ISO_DATE}-x86_64.iso"
    local renamed_iso="$OUT_DIR/${ISO_NAME}-stock.iso"
    if [[ -f "$stock_iso" ]]; then
        mv "$stock_iso" "$renamed_iso"
        ok "Phase 1 complete: $renamed_iso ($(du -h "$renamed_iso" | cut -f1))"
    else
        err "mkarchiso did not produce expected output: $stock_iso"
    fi
}

# ── Phase 2: Inject Syntropia slides into the ISO ──────────────
phase2_inject_slides() {
    local input_iso="$OUT_DIR/${ISO_NAME}-stock.iso"
    local output_iso="$OUT_DIR/${ISO_NAME}.iso"

    if [[ ! -f "$input_iso" ]]; then
        err "Stock ISO not found: $input_iso. Run --phase1 first."
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

    # Step 2: Unsquash the rootfs
    info "Unsquashing rootfs (this takes ~30s)..."
    unsquashfs -d rootfs arch/x86_64/airootfs.sfs
    ok "Rootfs unsquashed ($(du -sh rootfs | cut -f1))"

    # Step 3: Swap in our amended slides
    info "Injecting Syntropia slides..."
    local cal_dir="rootfs/usr/share/calamares/branding/cachyos"
    cp "$BRANDING_SRC"/slide{1,2,3,4,5,6}.jxl "$cal_dir/"
    ok "Slides injected"

    # Step 4: Repack squashfs
    info "Repacking squashfs (this takes ~5 min)..."
    rm -f arch/x86_64/airootfs.sfs
    mksquashfs rootfs/ arch/x86_64/airootfs.sfs \
        -comp xz -b 1M -Xbcj x86 -Xdict-size 1M -noappend
    ok "Squashfs repacked ($(du -sh arch/x86_64/airootfs.sfs | cut -f1))"

    # Step 5: Update checksum
    cd arch/x86_64
    sha512sum airootfs.sfs > airootfs.sha512
    cd "$remaster_dir"
    ok "Checksum updated"

    # Step 5.5: Remove the unsquashed rootfs to keep ISO size reasonable
    # (the remaster dir becomes the ISO root; we only need the packaged sfs)
    info "Cleaning up unsquashed rootfs..."
    rm -rf rootfs
    ok "Cleaned rootfs ($(du -sh . | cut -f1) remaining)"

    # Step 6: Rebuild hybrid ISO with xorriso
    info "Rebuilding ISO with xorriso..."
    local efi_file
    efi_file=$(ls EFI/BOOT/ | grep -i 'BOOTx64\.EFI$' | head -1)
    if [[ -z "$efi_file" ]]; then
        efi_file=$(ls EFI/BOOT/ | grep -i '\.efi$' | head -1)
        info "Using EFI bootloader: $efi_file"
    fi

    xorriso -as mkisofs \
        -iso-level 3 \
        -full-iso9660-filenames \
        -volid "SYNTROPIA" \
        -eltorito-boot boot/syslinux/isolinux.bin \
        -eltorito-catalog boot/syslinux/boot.cat \
        -no-emul-boot -boot-load-size 4 -boot-info-table \
        -isohybrid-mbr boot/syslinux/isohdpfx.bin \
        -eltorito-alt-boot \
        -e "EFI/BOOT/$efi_file" \
        -no-emul-boot \
        -output "$output_iso" \
        .

    ok "Phase 2 complete: $output_iso ($(du -h "$output_iso" | cut -f1))"
    info "Your Syntropia-branded CachyOS installer ISO is ready!"
    info "  $output_iso"
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
