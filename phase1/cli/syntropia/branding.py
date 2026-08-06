"""syntropia branding — install the amended visual assets.

Consumes the asset set produced from the CachyOS official branding
(see ``Branding/`` and the extracted reference set) and installs it:

* **Plymouth boot splash** — a complete theme (``plymouth/`` dir with
  ``animation-*.png`` frames, a ``*.plymouth`` theme file, etc.) installed
  as the ``syntropia`` theme and selected as default.
* **GRUB splash** — ``grub/splash.png`` (1920x1080 boot menu background),
  wired into the active theme's ``desktop-image`` (or ``GRUB_BACKGROUND``),
  followed by a ``grub-mkconfig`` regeneration so it actually displays.
* **Wallpaper** — ``wallpaper.png`` copied to the user's backgrounds dir
  and applied best-effort on GNOME/KDE.

Safety contract mirrors ``transform.py``: ``--check`` never modifies
anything, steps are idempotent (marker-based), and the runner stops at the
first error.
"""

from __future__ import annotations

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
        if (theme_dir / MARKER).exists():
            self.log("plymouth", f"{theme_dir} already branded, skipping")
            return
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
            # Rewrite the theme's display name whatever the original was.
            content = re.sub(r"(?m)^\s*Name=.*$", "Name=Syntropia", content)
            target_descriptor.write_text(content, encoding="utf-8")
            descriptor.unlink()
        (theme_dir / MARKER).write_text("branded by syntropia\n", encoding="utf-8")
        if shutil.which("plymouth-set-default-theme"):
            # Best-effort: installing the theme is the asset work; selecting it
            # as default can fail on non-root/broken initramfs — warn, don't abort.
            result = run_command(["plymouth-set-default-theme", PLYMOUTH_THEME_NAME])
            if result.returncode != 0:
                self.log(
                    "plymouth",
                    f"warning: could not set default theme: "
                    f"{result.stdout.strip() or result.stderr.strip()}",
                )

    # -- GRUB splash ------------------------------------------------------

    def _grub_asset(self) -> Path | None:
        candidate = self.paths.assets_dir / "grub" / "splash.png"
        if candidate.is_file():
            return candidate
        candidate = self.paths.assets_dir / "grub-splash.png"
        return candidate if candidate.is_file() else None

    def _grub_theme_background(self) -> Path | None:
        """Where the active GRUB theme loads its background from, if any.

        Reads ``GRUB_THEME=`` from ``/etc/default/grub`` and then the theme's
        ``theme.txt`` ``desktop-image`` directive. On themed setups (CachyOS
        ships a theme by default) this file — not ``/boot/grub/splash.png`` —
        is what actually renders as the GRUB menu background.
        """
        default_cfg = self.paths.grub_default
        if not default_cfg.is_file():
            return None
        theme_line: str | None = None
        try:
            for line in default_cfg.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("GRUB_THEME=") and not stripped.startswith("#"):
                    theme_line = stripped
                    break
        except OSError:
            return None
        if theme_line is None:
            return None
        theme_txt = Path(theme_line.split("=", 1)[1].strip().strip('\"\''))
        if not theme_txt.is_file():
            return None
        try:
            for line in theme_txt.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("desktop-image:"):
                    image = line.split(":", 1)[1].strip().strip('\"\'')
                    return theme_txt.parent / image
        except OSError:
            return None
        return None

    def _wire_grub_background(self, asset: Path, target: Path) -> None:
        """Point GRUB at the new splash image.

        If a theme is active, replace the file the theme's ``desktop-image``
        references. Otherwise ensure ``GRUB_BACKGROUND`` points at ``target``
        in ``/etc/default/grub``.
        """
        theme_bg = self._grub_theme_background()
        if theme_bg is not None and theme_bg.resolve() != target.resolve():
            bg_backup = theme_bg.with_name(theme_bg.name + ".syntropia.bak")
            self._would("grub", f"point theme background {theme_bg.name} -> {asset.name}")
            if self.dry_run:
                return
            if theme_bg.exists():
                shutil.copy2(theme_bg, bg_backup)
            shutil.copy2(asset, theme_bg)
            return
        default_cfg = self.paths.grub_default
        if not default_cfg.is_file():
            self.log(
                "grub",
                "no GRUB_THEME and no /etc/default/grub — skipping background wiring",
            )
            return
        try:
            content = default_cfg.read_text(encoding="utf-8")
        except OSError:
            return
        lines = content.splitlines()
        replaced = False
        new_lines: list[str] = []
        for line in lines:
            if line.strip().startswith("GRUB_BACKGROUND="):
                new_lines.append(f'GRUB_BACKGROUND="{target}"')
                replaced = True
            else:
                new_lines.append(line)
        if not replaced:
            new_lines.append(f'GRUB_BACKGROUND="{target}"')
        if "\n".join(new_lines) == content:
            self.log("grub", "GRUB_BACKGROUND already points at the splash")
            return
        self._would("grub", f"set GRUB_BACKGROUND={target} in {default_cfg}")
        if self.dry_run:
            return
        default_cfg.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    def _regenerate_grub_config(self) -> None:
        """Run ``grub-mkconfig`` so the new background actually takes effect."""
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
        asset = self._grub_asset()
        if asset is None:
            self.log("grub", "no grub splash asset found, skipping")
            return
        target = self.paths.grub_splash
        backup = target.with_name(target.name + ".syntropia.bak")
        marker = target.with_name(target.name + MARKER)
        if marker.exists():
            self.log("grub", "already branded (marker present), skipping")
            return
        self._would("grub", f"install {asset.name} -> {target}")
        if not self.dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                # First branding run: preserve whatever was there (e.g. stock splash).
                shutil.copy2(target, backup)
            shutil.copy2(asset, target)
            marker.write_text("branded by syntropia\n", encoding="utf-8")
            self.log(
                "grub",
                f"installed {target}"
                + (f" (original preserved as {backup.name})" if backup.exists() else ""),
            )
        self._wire_grub_background(asset, target)
        self._regenerate_grub_config()

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
            self.log("wallpaper", f"{target} already installed, skipping")
            return
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
