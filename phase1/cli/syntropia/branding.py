"""syntropia branding — install the amended visual assets.

Consumes the asset set produced from the CachyOS official branding
(see ``Branding/`` and the extracted reference set) and installs it:

* **Plymouth boot splash** — the main branding surface. A complete theme
  (``plymouth/`` dir with the 88-frame triangle ``animation-*.png`` swarm, a
  ``*.plymouth`` theme file, etc.) installed as the ``syntropia`` theme and
  selected as default.
* **GRUB** — deliberately left as vanilla CachyOS: the stock boot menu and
  kernel command line are untouched.
* **Wallpaper** — ``wallpaper.png`` copied to the user's backgrounds dir
  and applied best-effort on KDE Plasma.

Safety contract mirrors ``transform.py``: ``--check`` never modifies
anything, steps are idempotent (marker-based), and the runner stops at the
first error.
"""

from __future__ import annotations

import hashlib
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
    backgrounds_dir: Path | None = None  # default: ~/.local/share/backgrounds/syntropia
    icons_dir: Path | None = None  # default: ~/.local/share/icons/hicolor
    appletsrc: Path | None = None  # default: ~/.config/plasma-org.kde.plasma.desktop-appletsrc
    lookfeel_dir: Path | None = None  # default: ~/.local/share/plasma/look-and-feel
    ksplashrc: Path | None = None  # default: ~/.config/ksplashrc

    @property
    def splash_theme_dir(self) -> Path:
        base = self.lookfeel_dir or self.home / ".local" / "share" / "plasma" / "look-and-feel"
        return base / "org.syntropia.desktop" / "contents" / "splash"

    @property
    def ksplashrc_path(self) -> Path:
        return self.ksplashrc or self.home / ".config" / "ksplashrc"

    @property
    def wallpaper_dir(self) -> Path:
        return self.backgrounds_dir or self.home / ".local" / "share" / "backgrounds" / "syntropia"

    @property
    def wallpaper_target(self) -> Path:
        return self.wallpaper_dir / "wallpaper.png"

    @property
    def menu_icon_dir(self) -> Path:
        return self.icons_dir or self.home / ".local" / "share" / "icons" / "hicolor"

    @property
    def menu_icon_target(self) -> Path:
        return self.menu_icon_dir / "256x256" / "apps" / "syntropia-menu.png"

    @property
    def appletsrc_path(self) -> Path:
        return self.appletsrc or self.home / ".config" / "plasma-org.kde.plasma.desktop-appletsrc"

    @property
    def plymouth_theme_dir(self) -> Path:
        return self.plymouth_themes_dir / PLYMOUTH_THEME_NAME


@dataclass
class Branding:
    """Installs the amended visual assets. See module docstring."""

    paths: BrandingPaths
    dry_run: bool = False
    is_plasma: bool | None = None  # None = auto-detect; Syntropia targets Plasma only.

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

    def _is_plasma(self) -> bool:
        """Syntropia branding is Plasma-only.

        Auto-detect via the plasmashell binary (robust under sudo, which
        strips XDG_CURRENT_DESKTOP); tests pin it via the is_plasma field.
        """
        if self.is_plasma is not None:
            return self.is_plasma
        return shutil.which("plasmashell") is not None

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
        # The triangle swarm runs on the theme's black background (same as
        # CachyOS's cachyos-bootanimation) — no wallpaper overlay.
        (theme_dir / MARKER).write_text(_dir_hash(assets) + "\n", encoding="utf-8")
        if shutil.which("plymouth-set-default-theme"):
            result = run_command(["plymouth-set-default-theme", PLYMOUTH_THEME_NAME])
            if result.returncode != 0:
                self.log(
                    "plymouth",
                    "warning: could not set default theme: "
                    f"{result.stdout.strip() or result.stderr.strip()}",
                )

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
        """Set the wallpaper on Plasma (the only target desktop)."""
        if not self._is_plasma():
            return
        if shutil.which("plasma-apply-wallpaperimage") is None:
            return
        run_command(["plasma-apply-wallpaperimage", str(target)])

    # -- start-menu icon ---------------------------------------------------

    def _menu_icon_asset(self) -> Path | None:
        candidate = self.paths.assets_dir / "menu-icon.png"
        return candidate if candidate.is_file() else None

    def apply_menu_icon(self) -> None:
        """Replace the CachyOS start-menu (Kickoff) icon with the Syntropia mark.

        Plasma-only (Syntropia targets the KDE Plasma edition). The stock
        CachyOS panel points ``icon=org.cachyos.hello`` in the Kickoff applet
        config. We ship ``menu-icon.png`` into the hicolor icon theme as
        ``syntropia-menu`` and repoint the panel config at it — instead of
        overwriting ``org.cachyos.hello`` (a package file that an update
        would revert).
        """
        if not self._is_plasma():
            self.log(
                "menu-icon", "Syntropia branding is Plasma-only — skipping start-menu icon"
            )
            return
        asset = self._menu_icon_asset()
        if asset is None:
            self.log("menu-icon", "no menu-icon.png asset found, skipping")
            return
        target = self.paths.menu_icon_target
        if target.exists() and _file_hash(target) == _file_hash(asset):
            self.log("menu-icon", f"{target} already installed (up to date), skipping")
        else:
            self._would("menu-icon", f"install {asset.name} -> {target}")
            if not self.dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(asset, target)

        appletsrc = self.paths.appletsrc_path
        if not appletsrc.exists():
            self.log("menu-icon", f"{appletsrc} not found, skipping panel repoint")
            return
        content = appletsrc.read_text(encoding="utf-8")
        if "icon=syntropia-menu" in content:
            self.log("menu-icon", f"{appletsrc} already points at syntropia-menu, skipping")
            return
        if "icon=org.cachyos.hello" not in content:
            self.log("menu-icon", f"{appletsrc} has no cachyos menu icon ref, skipping")
            return
        self._would("menu-icon", f"repoint {appletsrc}: org.cachyos.hello -> syntropia-menu")
        if not self.dry_run:
            appletsrc.write_text(
                content.replace("icon=org.cachyos.hello", "icon=syntropia-menu"),
                encoding="utf-8",
            )

    # -- login splash (KSplash) -------------------------------------------

    def _splash_asset_dir(self) -> Path | None:
        candidate = self.paths.assets_dir / "splash"
        return candidate if candidate.is_dir() else None

    def apply_splash(self) -> None:
        """Install the Syntropia KSplash theme and select it in ksplashrc.

        Plasma-only (Syntropia targets the KDE Plasma edition). Ships the
        ``splash/`` asset dir (Splash.qml + images) to a custom
        ``org.syntropia.desktop`` look-and-feel splash and points ksplashrc
        at it. The QML shows the triangle mark first, then the Plasma logo,
        then fades out as the session becomes ready.
        """
        if not self._is_plasma():
            self.log("splash", "Syntropia branding is Plasma-only — skipping KSplash")
            return
        asset_dir = self._splash_asset_dir()
        if asset_dir is None:
            self.log("splash", "no splash/ asset dir found, skipping")
            return
        theme_dir = self.paths.splash_theme_dir
        if theme_dir.is_dir() and _dir_hash(theme_dir) == _dir_hash(asset_dir):
            self.log("splash", f"{theme_dir} already installed (up to date), skipping")
        else:
            self._would("splash", f"install splash theme -> {theme_dir}")
            if not self.dry_run:
                if theme_dir.exists():
                    shutil.rmtree(theme_dir)
                shutil.copytree(asset_dir, theme_dir)

        ksplashrc = self.paths.ksplashrc_path
        content = ksplashrc.read_text(encoding="utf-8") if ksplashrc.exists() else ""
        if "Theme=org.syntropia.desktop" in content:
            self.log("splash", f"{ksplashrc} already points at syntropia, skipping")
            return
        self._would("splash", f"select org.syntropia.desktop in {ksplashrc}")
        if not self.dry_run:
            ksplashrc.parent.mkdir(parents=True, exist_ok=True)
            ksplashrc.write_text(
                "[KSplash]\nEngine=KSplashQML\nTheme=org.syntropia.desktop\n",
                encoding="utf-8",
            )

    # -- runner -----------------------------------------------------------

    def apply_all(self) -> None:
        if not self.has_assets():
            self.log("assets", f"{self.paths.assets_dir} not found, skipping all branding")
            return
        self.apply_plymouth()
        self.apply_wallpaper()
        self.apply_menu_icon()
        self.apply_splash()
