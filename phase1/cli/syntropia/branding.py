"""syntropia branding — install the amended visual assets.

Consumes the asset set produced from the CachyOS official branding
(see ``Branding/`` and the extracted reference set) and installs it:

* **Plymouth boot splash** — the main branding surface. A complete theme
  (``plymouth/`` dir with ``animation-*.png`` frames, a ``*.plymouth`` theme
  file, etc.) installed as the ``syntropia`` theme and selected as default.
  ``wallpaper.png`` is also copied as the Plymouth background image so the
  full-color splash renders during boot (unlike GRUB's 16-bit framebuffer).
* **GRUB** — the boot menu keeps a clean dark background (no custom splash)
  because GRUB's 16-bit colour depth posterizes subtle gradients. Plymouth
  handles the branding at full 24-bit colour later in the boot chain.
* **Wallpaper** — ``wallpaper.png`` copied to the user's backgrounds dir
  and applied best-effort on GNOME/KDE.

Safety contract mirrors ``transform.py``: ``--check`` never modifies
anything, steps are idempotent (marker-based), and the runner stops at the
first error.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

MARKER = ".syntropia-branded"

PLYMOUTH_THEME_NAME = "syntropia"


class BrandingError(Exception):
    """A branding step failed or the asset set is incomplete."""


def run_command(cmd: list[str]) -> subprocess.CompletedProcess:
    """Run a command and capture output. Wrapped for test mocking."""
    return subprocess.run(cmd, capture_output=True, text=True)


def _dir_hash(directory: Path) -> str:
    """Content hash of every file under ``directory`` (paths + bytes).

    Lets the idempotency check be content-based: a branding package
    update that ships new assets re-applies them instead of skipping on
    a stale marker/presence check.
    """
    hasher = hashlib.sha256()
    for path in sorted(p for p in directory.rglob("*") if p.is_file()):
        hasher.update(path.relative_to(directory).as_posix().encode("utf-8"))
        hasher.update(path.read_bytes())
    return hasher.hexdigest()


def _file_hash(path: Path) -> str:
    """Content hash of a single file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass
class BrandingPaths:
    """Every filesystem path branding touches (injectable for tests)."""

    home: Path
    assets_dir: Path
    plymouth_themes_dir: Path = Path("/usr/share/plymouth/themes")
    grub_splash: Path = Path("/boot/grub/splash.png")
    grub_cfg: Path = Path("/boot/grub/grub.cfg")
    grub_default: Path = Path("/etc/default/grub")
    backgrounds_dir: Path | None = None  # default: ~/.local/share/backgrounds/syntropia

    @property
    def wallpaper_dir(self) -> Path:
        return self.backgrounds_dir or self.home / ".local" / "share" / "backgrounds" / "syntropia"

    @property
    def wallpaper_target(self) -> Path:
        return self.wallpaper_dir / "wallpaper.png"

    @property
    def plymouth_theme_dir(self) -> Path:
        return self.plymouth_themes_dir / PLYMOUTH_THEME_NAME


@dataclass
class Branding:
    """Installs the amended visual assets. See module docstring."""

    paths: BrandingPaths
    dry_run: bool = False

    # -- helpers ----------------------------------------------------------

    def log(self, action: str, message: str) -> None:
        prefix = "[CHECK]" if self.dry_run else "[APPLY]"
        print(f"{prefix} branding/{action}: {message}")

    def _would(self, action: str, message: str) -> None:
        self.planned += 1
        self.log(action, message)

    def __post_init__(self) -> None:
        self.planned = 0

    def has_assets(self) -> bool:
        return self.paths.assets_dir.is_dir()

    # -- Plymouth boot splash ---------------------------------------------

    def _plymouth_assets(self) -> Path | None:
        candidate = self.paths.assets_dir / "plymouth"
        if candidate.is_dir():
            return candidate
        return None

    def apply_plymouth(self) -> None:
        assets = self._plymouth_assets()
        if assets is None:
            self.log("plymouth", "no 'plymouth/' asset dir found, skipping")
            return
        theme_dir = self.paths.plymouth_theme_dir
        marker = theme_dir / MARKER
        if marker.exists():
            installed_hash = marker.read_text(encoding="utf-8").strip()
            if installed_hash == _dir_hash(assets):
                self.log(
                    "plymouth",
                    f"{theme_dir} already branded (assets unchanged), skipping",
                )
                return
            # Assets changed (or a legacy marker without a hash) — refresh
            # so a branding package update actually lands.
            self.log("plymouth", f"{theme_dir} branded but assets changed — refreshing")
        self._would("plymouth", f"install Syntropia boot splash theme to {theme_dir}")
        if self.dry_run:
            return
        shutil.rmtree(theme_dir, ignore_errors=True)
        shutil.copytree(assets, theme_dir)
        # Plymouth matches themes by a descriptor named <theme>.plymouth, so
        # rename whatever descriptor shipped (e.g. cachyos.plymouth).
        descriptor = next(theme_dir.glob("*.plymouth"), None)
        if descriptor is None:
            raise BrandingError(
                "plymouth asset dir must contain a *.plymouth theme descriptor"
            )
        target_descriptor = theme_dir / f"{PLYMOUTH_THEME_NAME}.plymouth"
        if descriptor != target_descriptor:
            content = descriptor.read_text(encoding="utf-8")
            # Rewrite the theme name and fix inherited CachyOS paths.
            content = re.sub(r"(?m)^\s*Name=.*$", "Name=Syntropia", content)
            content = re.sub(
                r"(?m)^\s*ImageDir=.*$",
                f"ImageDir={theme_dir}",
                content,
            )
            # Disable firmware background so our wallpaper shows instead.
            content = re.sub(
                r"(?m)^\s*UseFirmwareBackground=.*$",
                "UseFirmwareBackground=false",
                content,
            )
            target_descriptor.write_text(content, encoding="utf-8")
            descriptor.unlink()
        # Copy wallpaper as the Plymouth background image (full 24-bit colour
        # — unlike GRUB's 16-bit framebuffer which posterizes dark gradients).
        wallpaper = self._wallpaper_asset()
        if wallpaper:
            bg = theme_dir / "background.png"
            if not bg.exists():
                shutil.copy2(wallpaper, bg)
                self.log("plymouth", f"installed background from {wallpaper.name}")
        (theme_dir / MARKER).write_text(_dir_hash(assets) + "\n", encoding="utf-8")
        if shutil.which("plymouth-set-default-theme"):
            result = run_command(["plymouth-set-default-theme", PLYMOUTH_THEME_NAME])
            if result.returncode != 0:
                self.log(
                    "plymouth",
                    "warning: could not set default theme: "
                    f"{result.stdout.strip() or result.stderr.strip()}",
                )

    # -- GRUB (clean background, no splash) -------------------------------

    def _regenerate_grub_config(self) -> None:
        """Run ``grub-mkconfig`` so any /etc/default/grub edits take effect."""
        grub_mkconfig = shutil.which("grub-mkconfig")
        if grub_mkconfig is None:
            self.log("grub", "grub-mkconfig not found, skipping config regeneration")
            return
        cfg = self.paths.grub_cfg
        self._would("grub", f"regenerate GRUB config ({cfg.name}) via grub-mkconfig")
        if self.dry_run:
            return
        result = run_command([grub_mkconfig, "-o", str(cfg)])
        if result.returncode != 0:
            self.log(
                "grub",
                "warning: grub-mkconfig failed: "
                f"{result.stdout.strip() or result.stderr.strip()}",
            )
            return
        self.log("grub", f"regenerated {cfg}")

    def apply_grub(self) -> None:
        """Ensure clean GRUB: no splash, native resolution, BGRT disabled.

        * Comments out GRUB_BACKGROUND (Plymouth handles branding).
        * Pins GFXMODE=1920x1080 so menu text is crisp.
        * Adds bgrt_disable to kernel cmdline so the motherboard's firmware
          logo never appears — Plymouth shows our wallpaper from frame one.
        """
        default_cfg = self.paths.grub_default
        if not default_cfg.is_file():
            self.log("grub", "/etc/default/grub not found, skipping")
            return

        try:
            content = default_cfg.read_text(encoding="utf-8")
        except OSError:
            return

        lines = content.splitlines()
        new_lines: list[str] = []
        changed = False

        for line in lines:
            stripped = line.strip()
            # Comment out any active GRUB_BACKGROUND (Plymouth has the splash).
            if stripped.startswith("GRUB_BACKGROUND=") and not stripped.startswith("#"):
                new_lines.append("#GRUB_BACKGROUND commented out — Plymouth handles branding")
                changed = True
            # Pin GFXMODE to native resolution.
            elif stripped.startswith("GRUB_GFXMODE=") and not stripped.startswith("#"):
                if stripped != "GRUB_GFXMODE=1920x1080":
                    new_lines.append("GRUB_GFXMODE=1920x1080")
                    changed = True
                else:
                    new_lines.append(line)
            # Ensure bgrt_disable is in kernel cmdline (suppresses firmware logo).
            elif stripped.startswith("GRUB_CMDLINE_LINUX_DEFAULT=") and not stripped.startswith("#"):
                if "bgrt_disable" not in stripped:
                    new_lines.append(stripped.rstrip("'\"") + " bgrt_disable'")
                    changed = True
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)

        if changed:
            self._would("grub", "clean GRUB + GFXMODE=1920x1080 + bgrt_disable")
            if not self.dry_run:
                default_cfg.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
                self._regenerate_grub_config()
        else:
            self.log("grub", "already clean (no splash, GFXMODE=1920x1080, bgrt_disable)")

    # -- Wallpaper --------------------------------------------------------

    def _wallpaper_asset(self) -> Path | None:
        candidate = self.paths.assets_dir / "wallpaper.png"
        return candidate if candidate.is_file() else None

    def apply_wallpaper(self) -> None:
        asset = self._wallpaper_asset()
        if asset is None:
            self.log("wallpaper", "no wallpaper.png asset found, skipping")
            return
        target = self.paths.wallpaper_target
        if target.exists():
            if _file_hash(target) == _file_hash(asset):
                self.log("wallpaper", f"{target} already installed (up to date), skipping")
                return
            # A branding package update changed the wallpaper — refresh it.
            self.log("wallpaper", f"{target} differs from asset — refreshing")
        self._would("wallpaper", f"install {asset.name} -> {target}")
        if self.dry_run:
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(asset, target)
        self._apply_wallpaper_best_effort(target)

    def _apply_wallpaper_best_effort(self, target: Path) -> None:
        """Set the wallpaper on GNOME/KDE if the tooling is present."""
        uri = target.as_uri()
        if os.environ.get("XDG_CURRENT_DESKTOP", "").upper() == "GNOME":
            run_command(["gsettings", "set", "org.gnome.desktop.background", "picture-uri", uri])
            run_command(
                ["gsettings", "set", "org.gnome.desktop.background", "picture-uri-dark", uri]
            )
        elif os.environ.get("XDG_CURRENT_DESKTOP", "").upper() == "KDE":
            run_command(["plasma-apply-wallpaperimage", str(target)])

    # -- runner -----------------------------------------------------------

    def apply_all(self) -> None:
        if not self.has_assets():
            self.log("assets", f"{self.paths.assets_dir} not found, skipping all branding")
            return
        self.apply_plymouth()
        self.apply_grub()
        self.apply_wallpaper()
