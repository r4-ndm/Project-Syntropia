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
# wipes our install-time wizard-copy hook).
NoUpgrade = usr/share/calamares/settings_online.conf
NoUpgrade = usr/share/calamares/settings_offline.conf'''
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

    # Step 3.5: Ensure the display manager is wired up so the live desktop
    # auto-starts (the CachyOS profile's dmcheck script creates this symlink,
    # but our mkarchiso build doesn't run it; the original CachyOS ISO ships
    # the link pre-baked). Without it, the live ISO boots to a bare tty1
    # console with no desktop and "Launch Installer" is unreachable.
    info "Wiring display-manager.service -> plasmalogin.service..."
    if [[ -f "rootfs/usr/lib/systemd/system/plasmalogin.service" ]]; then
        ln -sf /usr/lib/systemd/system/plasmalogin.service \
            "rootfs/etc/systemd/system/display-manager.service"
        ok "display-manager.service symlink created"
    else
        # Fallback: try SDDM if plasmalogin isn't present
        if [[ -f "rootfs/usr/lib/systemd/system/sddm.service" ]]; then
            ln -sf /usr/lib/systemd/system/sddm.service \
                "rootfs/etc/systemd/system/display-manager.service"
            ok "display-manager.service symlink created (sddm)"
        else
            warn "No display-manager service found; live desktop won't auto-start!"
        fi
    fi

    # Step 3.6: Ship the apps wizard into /etc/syntropia/ so the first-boot
    # "pick your favorites" dialog is available on freshly-installed systems.
    # The wizard resolves the catalog as: --config, ~/.config/syntropia/apps.list
    # (user override), /etc/syntropia/apps.list (shipped here), bundled fallback.
    info "Shipping apps wizard to /etc/syntropia/..."
    local wizard_src="$REPO_ROOT/phase1/wizard"
    local syn_dir="rootfs/etc/syntropia"
    mkdir -p "$syn_dir"
    cp "$wizard_src/syntropia-apps-wizard.sh" "$syn_dir/"
    cp "$wizard_src/syntropia-apps-dialog.py" "$syn_dir/"
    cp "$wizard_src/apps.list" "$syn_dir/"
    chmod +x "$syn_dir/syntropia-apps-wizard.sh"

    # Calamares shellprocess hook helper: the branding hook runs its shell
    # logic through this script because the module macro-expands commands
    # with KWordMacroExpander('$') — bare $vars in a command string are
    # treated as undefined macros and abort the job (see the hook comment).
    cp "$SCRIPT_DIR/hook-scripts/hook-branding-users.sh" "$syn_dir/"
    chmod +x "$syn_dir/hook-branding-users.sh"

    # First-boot autostart entry → /etc/xdg/autostart/: shows the dialog once
    # at first login (the wizard self-disables via its --once done-marker).
    mkdir -p rootfs/etc/xdg/autostart
    sed "s|@SCRIPT@|/etc/syntropia/syntropia-apps-wizard.sh|" \
        "$wizard_src/syntropia-apps.desktop" \
        > rootfs/etc/xdg/autostart/syntropia-apps.desktop
    ok "Apps wizard shipped (/etc/syntropia/ + first-boot autostart)"

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
    - command: "bash -c 'set -o pipefail; { echo \"=== syntropia_wizard:start $(date) ===\"; mkdir -p ${ROOT}/etc/syntropia && cp -a /etc/syntropia/. ${ROOT}/etc/syntropia/ && mkdir -p ${ROOT}/etc/xdg/autostart && cp -a /etc/xdg/autostart/syntropia-apps.desktop ${ROOT}/etc/xdg/autostart/; echo \"=== syntropia_wizard:exit $? ===\"; } 2>&1 | tee -a ${ROOT}/var/log/syntropia-hooks.log'"
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
    mkdir -p "rootfs/etc/skel/.config/fastfetch"
    # Run from the remaster dir (cwd) but import the repo's config builder
    # via PYTHONPATH — same single source of truth as `syntropia transform`.
    # NOTE: python3 -c only runs the FIRST argument; later args become
    # sys.argv and silently produce empty output. Use a heredoc instead so
    # the whole program is one stdin stream.
    PYTHONPATH="$REPO_ROOT/phase1/cli" python3 - \
        "$REPO_ROOT/Branding/syntropia/fastfetch-color.json" \
      > rootfs/etc/skel/.config/fastfetch/config.jsonc 2>/dev/null << 'PYEOF' || true
import json, sys
from syntropia.transform import build_fastfetch_conf
cm = json.load(open(sys.argv[1]))
print(build_fastfetch_conf(cm), end="")
PYEOF
    if [[ -s rootfs/etc/skel/.config/fastfetch/config.jsonc ]]; then
        ok "ASCII art shipped (/usr/share/syntropia/ + skel fastfetch config)"
    else
        warn "fastfetch config empty — ASCII art not shipped"
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
    - command: "bash -c 'set -o pipefail; { echo \"=== syntropia_branding:start $(date) ===\"; mkdir -p ${ROOT}/usr/share/syntropia/branding && cp -a /usr/share/syntropia/. ${ROOT}/usr/share/syntropia/ && mkdir -p ${ROOT}/etc/skel/.config/fastfetch && cp -a /etc/skel/.config/fastfetch/config.jsonc ${ROOT}/etc/skel/.config/fastfetch/; echo \"=== syntropia_branding:exit $? ===\"; } 2>&1 | tee -a ${ROOT}/var/log/syntropia-hooks.log'"
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
