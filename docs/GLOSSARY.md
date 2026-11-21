# 📖 Syntropia Glossary

The project's own words. Use them verbatim in code, commits, and replies —
they replace a paragraph of explanation each.

| Term | Means |
|------|-------|
| **Final Boss / L5** | The human owner. Final authority; can override any rule. |
| **Syntropia** | The OS this repo builds: CachyOS + branding + wizard + audio layer. |
| **transform** | `syntropia transform` — re-brands a *running* CachyOS in place. Destructive-ish: snapshot + `--check` first. |
| **brew** | A `.brew` TOML manifest for a **Windows** app/plugin installed through Wine. Unrelated to Homebrew. |
| **brew registry** | Local clone at `~/.config/syntropia/brews/` plus a shared GitHub registry — AUR-style. |
| **stock ISO** | Unbranded output of build phase 1 (`syntropia-*-stock.iso`), input to phase 2. |
| **phase 1 / phase 2** (build) | mkarchiso build, then squashfs remaster. Not the same as project phases below. |
| **Phase 1–4** (project) | 1 = the OS/product (now), 2 = AI integration, 3 = swarm, 4 = vision. |
| **airootfs** | The live system's root filesystem inside the ISO; what phase 2 unsquashes. |
| **app-wiz4rd** | First-boot app picker. Lives in its own repo, shipped here as a sha-pinned tarball. |
| **apps.list** | The wizard's catalog, `category\|name\|package\|description[|aliases]`. |
| **TUI installer** | The tty1 installer (`syntropia-install`, `-runner`, `-dashboard`). Primary install path. |
| **runner** | `syntropia-install-runner` — the destructive backend that partitions, copies, and installs Limine. |
| **overlay** | `iso/profiles/hyprland/` — Syntropia's additions on top of stock Hyprland/Noctalia config. |
| **Noctalia** | The Rust desktop shell (bar, launcher, notifications) replacing Waybar/SwayNC/Rofi. |
| **UWSM** | Universal Wayland Session Manager; how CachyOS starts Hyprland. |
| **Limine** | The installed bootloader, UEFI and BIOS. Entry name `/+CachyOS Syntropia`. |
| **ksecretd** | KWallet 6 daemon that owns `org.freedesktop.secrets`; unlocked via PAM. |
| **hook** | A shellprocess run at install time (`iso/hook-scripts/`), not a git hook. |
| **laptop** | The real hardware test target (`r5@192.168.1.22`). The build host is *not* a test target. |
