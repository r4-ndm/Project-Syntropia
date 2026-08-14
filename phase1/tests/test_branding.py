"""Tests for syntropia.branding — the amended-assets install engine."""

from pathlib import Path

import pytest

from syntropia_transform import branding as B


def make_assets(tmp_path: Path) -> Path:
    """Create an asset set: plymouth theme, wallpaper."""
    assets = tmp_path / "assets"
    (assets / "plymouth").mkdir(parents=True)
    (assets / "plymouth" / "cachyos.plymouth").write_text(
        "[Plymouth Theme]\nName=Syntropia\n", encoding="utf-8"
    )
    (assets / "plymouth" / "animation-0001.png").write_bytes(b"frame1")
    (assets / "wallpaper.png").write_bytes(b"wallpaper")
    return assets


def make_paths(tmp_path: Path, assets: Path | None = None) -> B.BrandingPaths:
    return B.BrandingPaths(
        home=tmp_path / "home",
        assets_dir=assets or make_assets(tmp_path),
        plymouth_themes_dir=tmp_path / "plymouth-themes",
    )


def make_branding(
    tmp_path: Path, *, dry_run: bool = False, is_plasma: bool = True
) -> B.Branding:
    return B.Branding(make_paths(tmp_path), dry_run=dry_run, is_plasma=is_plasma)


def noop_run(calls: list) -> callable:
    class _Fake:
        returncode = 0
        stdout = ""
        stderr = ""
    def _run(cmd: list) -> _Fake:
        calls.append(cmd)
        return _Fake()
    return _run


# --- asset detection ----------------------------------------------------


def test_has_assets_true(tmp_path: Path):
    assert make_branding(tmp_path).has_assets()


def test_has_assets_false_when_missing(tmp_path: Path):
    paths = make_paths(tmp_path, assets=tmp_path / "does-not-exist")
    assert not B.Branding(paths, dry_run=False).has_assets()


# --- Plymouth -----------------------------------------------------------


def test_plymouth_installs_theme_and_marker(tmp_path: Path):
    branding = make_branding(tmp_path, dry_run=False)
    branding.apply_plymouth()
    theme_dir = branding.paths.plymouth_theme_dir
    assert (theme_dir / "animation-0001.png").read_bytes() == b"frame1"
    assert (theme_dir / B.MARKER).exists()


def test_plymouth_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls: list = []
    monkeypatch.setattr(B, "run_command", noop_run(calls))
    branding = make_branding(tmp_path, dry_run=False)
    branding.apply_plymouth()
    branding.apply_plymouth()  # second run must skip
    theme_dir = branding.paths.plymouth_theme_dir
    assert len(list(theme_dir.glob("animation-*.png"))) == 1


def test_plymouth_dry_run_changes_nothing(tmp_path: Path):
    branding = make_branding(tmp_path, dry_run=True)
    branding.apply_plymouth()
    assert not branding.paths.plymouth_theme_dir.exists()


def test_plymouth_skips_without_assets(tmp_path: Path):
    paths = make_paths(tmp_path, assets=tmp_path / "nope")
    branding = B.Branding(paths, dry_run=False)
    branding.apply_plymouth()  # no crash, just skipped


def test_plymouth_refreshes_when_assets_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A branding update with new frames re-applies instead of skipping."""
    monkeypatch.setattr(B, "run_command", noop_run([]))
    branding = make_branding(tmp_path, dry_run=False)
    branding.apply_plymouth()
    theme_dir = branding.paths.plymouth_theme_dir
    assert (theme_dir / "animation-0001.png").read_bytes() == b"frame1"

    # Ship a new frame — the next run must refresh the theme.
    (branding.paths.assets_dir / "plymouth" / "animation-0001.png").write_bytes(
        b"frame1-NEW"
    )
    branding.apply_plymouth()
    assert (theme_dir / "animation-0001.png").read_bytes() == b"frame1-NEW"
    # Marker carries the new assets hash, so a third run skips again.
    marker = theme_dir / B.MARKER
    assert marker.read_text(encoding="utf-8").strip() == B._dir_hash(
        branding.paths.assets_dir / "plymouth"
    )
    branding.apply_plymouth()
    assert (theme_dir / "animation-0001.png").read_bytes() == b"frame1-NEW"


def test_plymouth_legacy_marker_triggers_refresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """A pre-hash marker ('branded by syntropia') is refreshed once."""
    monkeypatch.setattr(B, "run_command", noop_run([]))
    branding = make_branding(tmp_path, dry_run=False)
    theme_dir = branding.paths.plymouth_theme_dir
    theme_dir.mkdir(parents=True)
    (theme_dir / "animation-0001.png").write_bytes(b"old-frame")
    (theme_dir / B.MARKER).write_text("branded by syntropia\n", encoding="utf-8")

    branding.apply_plymouth()
    assert (theme_dir / "animation-0001.png").read_bytes() == b"frame1"


def test_plymouth_refresh_dry_run_changes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Dry-run with changed assets reports but never writes."""
    calls: list = []
    monkeypatch.setattr(B, "run_command", noop_run(calls))
    branding = make_branding(tmp_path, dry_run=False)
    branding.apply_plymouth()
    (branding.paths.assets_dir / "plymouth" / "animation-0001.png").write_bytes(
        b"frame1-NEW"
    )

    def boom(cmd: list):
        raise AssertionError("dry-run must not execute commands")

    monkeypatch.setattr(B, "run_command", boom)
    theme_dir = branding.paths.plymouth_theme_dir
    before = (theme_dir / "animation-0001.png").read_bytes()
    calls_before = len(calls)
    B.Branding(branding.paths, dry_run=True).apply_plymouth()
    assert (theme_dir / "animation-0001.png").read_bytes() == before
    assert (theme_dir / B.MARKER).exists()
    assert len(calls) == calls_before  # dry-run added no commands


# --- Wallpaper ----------------------------------------------------------


def test_wallpaper_installed_and_idempotent(tmp_path: Path):
    branding = make_branding(tmp_path, dry_run=False)
    branding.apply_wallpaper()
    assert branding.paths.wallpaper_target.read_bytes() == b"wallpaper"
    branding.apply_wallpaper()  # second run skips
    assert branding.paths.wallpaper_target.read_bytes() == b"wallpaper"


def test_wallpaper_dry_run_changes_nothing(tmp_path: Path):
    branding = make_branding(tmp_path, dry_run=True)
    branding.apply_wallpaper()
    assert not branding.paths.wallpaper_target.exists()


def test_wallpaper_refreshes_when_asset_changes(tmp_path: Path):
    branding = make_branding(tmp_path, dry_run=False)
    branding.apply_wallpaper()
    assert branding.paths.wallpaper_target.read_bytes() == b"wallpaper"

    (branding.paths.assets_dir / "wallpaper.png").write_bytes(b"wallpaper-NEW")
    branding.apply_wallpaper()
    assert branding.paths.wallpaper_target.read_bytes() == b"wallpaper-NEW"
    # Third run is a skip again (content matches).
    branding.apply_wallpaper()
    assert branding.paths.wallpaper_target.read_bytes() == b"wallpaper-NEW"


# --- start-menu icon ---------------------------------------------------

APP = "[Containments][23][Applets][24][Configuration][General]\nicon=org.cachyos.hello\n"


def _make_menu_assets(tmp_path: Path, paths: B.BrandingPaths) -> None:
    (paths.assets_dir / "menu-icon.png").write_bytes(b"menu-icon")
    home = paths.home
    (home / ".config").mkdir(parents=True, exist_ok=True)
    (home / ".config" / "plasma-org.kde.plasma.desktop-appletsrc").write_text(
        APP, encoding="utf-8"
    )


def test_menu_icon_installed_and_appletsrc_repointed(tmp_path: Path):
    branding = make_branding(tmp_path, dry_run=False)
    _make_menu_assets(tmp_path, branding.paths)
    branding.apply_menu_icon()
    assert branding.paths.menu_icon_target.read_bytes() == b"menu-icon"
    content = branding.paths.appletsrc_path.read_text(encoding="utf-8")
    assert "icon=syntropia-menu" in content
    assert "icon=org.cachyos.hello" not in content


def test_menu_icon_idempotent(tmp_path: Path):
    branding = make_branding(tmp_path, dry_run=False)
    _make_menu_assets(tmp_path, branding.paths)
    branding.apply_menu_icon()
    branding.apply_menu_icon()
    assert branding.paths.menu_icon_target.read_bytes() == b"menu-icon"
    assert branding.paths.appletsrc_path.read_text(encoding="utf-8").count("syntropia-menu") == 1


def test_menu_icon_dry_run_changes_nothing(tmp_path: Path):
    branding = make_branding(tmp_path, dry_run=True)
    _make_menu_assets(tmp_path, branding.paths)
    branding.apply_menu_icon()
    assert not branding.paths.menu_icon_target.exists()
    assert branding.paths.appletsrc_path.read_text(encoding="utf-8") == APP


def test_menu_icon_skips_without_asset(tmp_path: Path):
    branding = make_branding(tmp_path, dry_run=False)
    branding.apply_menu_icon()  # no menu-icon.png in assets — no crash
    assert not branding.paths.menu_icon_target.exists()


def test_menu_icon_skips_without_appletsrc(tmp_path: Path):
    branding = make_branding(tmp_path, dry_run=False)
    (branding.paths.assets_dir / "menu-icon.png").write_bytes(b"menu-icon")
    branding.apply_menu_icon()  # no appletsrc file — icon still installs, no repoint
    assert branding.paths.menu_icon_target.read_bytes() == b"menu-icon"


# --- login splash ------------------------------------------------------

def _make_splash_assets(paths: B.BrandingPaths) -> None:
    splash = paths.assets_dir / "splash"
    (splash / "images").mkdir(parents=True)
    (splash / "Splash.qml").write_text("// syntropia splash", encoding="utf-8")
    (splash / "images" / "logo.png").write_bytes(b"logo")


def test_splash_installed_and_selected(tmp_path: Path):
    branding = make_branding(tmp_path, dry_run=False)
    _make_splash_assets(branding.paths)
    branding.apply_splash()
    theme_dir = branding.paths.splash_theme_dir
    assert (theme_dir / "Splash.qml").exists()
    assert (theme_dir / "images" / "logo.png").read_bytes() == b"logo"
    assert "Theme=org.syntropia.desktop" in branding.paths.ksplashrc_path.read_text(
        encoding="utf-8"
    )


def test_splash_idempotent(tmp_path: Path):
    branding = make_branding(tmp_path, dry_run=False)
    _make_splash_assets(branding.paths)
    branding.apply_splash()
    branding.apply_splash()  # second run skips
    assert branding.paths.ksplashrc_path.read_text(encoding="utf-8").count(
        "org.syntropia.desktop"
    ) == 1


def test_splash_dry_run_changes_nothing(tmp_path: Path):
    branding = make_branding(tmp_path, dry_run=True)
    _make_splash_assets(branding.paths)
    branding.apply_splash()
    assert not branding.paths.splash_theme_dir.exists()
    assert not branding.paths.ksplashrc_path.exists()


def test_splash_skips_without_asset(tmp_path: Path):
    branding = make_branding(tmp_path, dry_run=False)
    branding.apply_splash()  # no splash/ dir in assets
    assert not branding.paths.splash_theme_dir.exists()


def test_splash_refreshes_when_assets_change(tmp_path: Path):
    branding = make_branding(tmp_path, dry_run=False)
    _make_splash_assets(branding.paths)
    branding.apply_splash()
    (branding.paths.assets_dir / "splash" / "Splash.qml").write_text(
        "// edited", encoding="utf-8"
    )
    branding.apply_splash()
    assert (
        branding.paths.splash_theme_dir / "Splash.qml"
    ).read_text(encoding="utf-8") == "// edited"


# --- Plasma-only gating -------------------------------------------------


def test_menu_icon_skips_when_not_plasma(tmp_path: Path):
    branding = make_branding(tmp_path, dry_run=False, is_plasma=False)
    _make_menu_assets(tmp_path, branding.paths)
    branding.apply_menu_icon()
    assert not branding.paths.menu_icon_target.exists()
    assert "icon=syntropia-menu" not in branding.paths.appletsrc_path.read_text(
        encoding="utf-8"
    )


def test_splash_skips_when_not_plasma(tmp_path: Path):
    branding = make_branding(tmp_path, dry_run=False, is_plasma=False)
    _make_splash_assets(branding.paths)
    branding.apply_splash()
    assert not branding.paths.splash_theme_dir.exists()
    assert not branding.paths.ksplashrc_path.exists()


# --- runner -------------------------------------------------------------


def test_apply_all_skips_without_assets(tmp_path: Path, capsys: pytest.CaptureFixture):
    paths = make_paths(tmp_path, assets=tmp_path / "nope")
    B.Branding(paths, dry_run=False).apply_all()
    out = capsys.readouterr().out
    assert "not found" in out
