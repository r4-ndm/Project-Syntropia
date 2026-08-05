"""Tests for syntropia.branding — the amended-assets install engine."""

from pathlib import Path

import pytest

from syntropia import branding as B


def make_assets(tmp_path: Path) -> Path:
    """Create an asset set: plymouth theme, grub splash, wallpaper."""
    assets = tmp_path / "assets"
    (assets / "plymouth").mkdir(parents=True)
    (assets / "plymouth" / "cachyos.plymouth").write_text(
        "[Plymouth Theme]\nName=Syntropia\n", encoding="utf-8"
    )
    (assets / "plymouth" / "animation-0001.png").write_bytes(b"frame1")
    (assets / "grub").mkdir()
    (assets / "grub" / "splash.png").write_bytes(b"grub-splash")
    (assets / "wallpaper.png").write_bytes(b"wallpaper")
    return assets


def make_paths(tmp_path: Path, assets: Path | None = None) -> B.BrandingPaths:
    return B.BrandingPaths(
        home=tmp_path / "home",
        assets_dir=assets or make_assets(tmp_path),
        plymouth_themes_dir=tmp_path / "plymouth-themes",
        grub_splash=tmp_path / "boot" / "grub" / "splash.png",
    )


def make_branding(tmp_path: Path, *, dry_run: bool = False) -> B.Branding:
    return B.Branding(make_paths(tmp_path), dry_run=dry_run)


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


# --- GRUB ---------------------------------------------------------------


def test_grub_installs_and_backs_up_existing(tmp_path: Path):
    paths = make_paths(tmp_path)
    paths.grub_splash.parent.mkdir(parents=True)
    paths.grub_splash.write_bytes(b"stock-cachyos-splash")  # pre-existing
    branding = B.Branding(paths, dry_run=False)
    branding.apply_grub()
    assert paths.grub_splash.read_bytes() == b"grub-splash"
    backup = paths.grub_splash.with_name("splash.png.syntropia.bak")
    assert backup.read_bytes() == b"stock-cachyos-splash"


def test_grub_idempotent_via_marker(tmp_path: Path):
    branding = make_branding(tmp_path, dry_run=False)
    branding.apply_grub()
    branding.apply_grub()
    marker = branding.paths.grub_splash.with_name("splash.png" + B.MARKER)
    assert marker.exists()


def test_grub_dry_run_changes_nothing(tmp_path: Path):
    branding = make_branding(tmp_path, dry_run=True)
    branding.apply_grub()
    assert not branding.paths.grub_splash.exists()


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


# --- runner -------------------------------------------------------------


def test_apply_all_skips_without_assets(tmp_path: Path, capsys: pytest.CaptureFixture):
    paths = make_paths(tmp_path, assets=tmp_path / "nope")
    B.Branding(paths, dry_run=False).apply_all()
    out = capsys.readouterr().out
    assert "not found" in out
