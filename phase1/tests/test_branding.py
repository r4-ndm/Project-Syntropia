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
        grub_cfg=tmp_path / "boot" / "grub" / "grub.cfg",
        grub_default=tmp_path / "etc" / "default" / "grub",
    )


def make_grub_default(tmp_path: Path, *, theme: Path | None = None) -> Path:
    """Write a fake /etc/default/grub; uses a temp theme if given."""
    path = tmp_path / "etc" / "default" / "grub"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["GRUB_DEFAULT=0", "GRUB_TIMEOUT='5'"]
    if theme is not None:
        lines.append(f"GRUB_THEME='{theme}'")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def make_theme(tmp_path: Path, bg_name: str = "background.png") -> Path:
    """Create a GRUB theme dir whose theme.txt loads bg_name."""
    theme_dir = tmp_path / "grub-theme"
    theme_dir.mkdir(parents=True)
    (theme_dir / "theme.txt").write_text(
        f'desktop-image: "{bg_name}"\n', encoding="utf-8"
    )
    (theme_dir / bg_name).write_bytes(b"stock-theme-bg")
    return theme_dir / "theme.txt"


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


def test_grub_installs_and_backs_up_existing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(B, "run_command", noop_run([]))
    paths = make_paths(tmp_path)
    paths.grub_splash.parent.mkdir(parents=True)
    paths.grub_splash.write_bytes(b"stock-cachyos-splash")  # pre-existing
    branding = B.Branding(paths, dry_run=False)
    branding.apply_grub()
    assert paths.grub_splash.read_bytes() == b"grub-splash"
    backup = paths.grub_splash.with_name("splash.png.syntropia.bak")
    assert backup.read_bytes() == b"stock-cachyos-splash"


def test_grub_idempotent_via_marker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(B, "run_command", noop_run([]))
    branding = make_branding(tmp_path, dry_run=False)
    branding.apply_grub()
    branding.apply_grub()
    marker = branding.paths.grub_splash.with_name("splash.png" + B.MARKER)
    assert marker.exists()


def test_grub_dry_run_changes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    calls: list = []

    def boom(cmd: list):
        calls.append(cmd)
        raise AssertionError("dry-run must not execute commands")

    monkeypatch.setattr(B, "run_command", boom)
    branding = make_branding(tmp_path, dry_run=True)
    branding.apply_grub()
    assert not branding.paths.grub_splash.exists()
    assert calls == []  # grub-mkconfig must not run in dry-run


def test_grub_replaces_theme_background_and_regenerates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    calls: list = []
    monkeypatch.setattr(B, "run_command", noop_run(calls))
    paths = make_paths(tmp_path)
    theme_txt = make_theme(tmp_path)
    make_grub_default(tmp_path, theme=theme_txt)
    B.Branding(paths, dry_run=False).apply_grub()
    # The theme's desktop-image file is what GRUB actually renders.
    theme_bg = theme_txt.parent / "background.png"
    assert theme_bg.read_bytes() == b"grub-splash"
    assert (theme_bg.with_name("background.png.syntropia.bak")).read_bytes() == b"stock-theme-bg"
    # grub-mkconfig ran against our grub.cfg.
    assert any(
        str(c[0]).endswith("grub-mkconfig") and c[-1].endswith("grub.cfg") for c in calls
    )


def test_grub_sets_grub_background_when_no_theme(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(B, "run_command", noop_run([]))
    paths = make_paths(tmp_path)
    grub_default = make_grub_default(tmp_path, theme=None)
    B.Branding(paths, dry_run=False).apply_grub()
    content = grub_default.read_text(encoding="utf-8")
    assert f'GRUB_BACKGROUND="{paths.grub_splash}"' in content


def test_grub_background_wiring_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(B, "run_command", noop_run([]))
    paths = make_paths(tmp_path)
    make_grub_default(tmp_path, theme=None)
    branding = B.Branding(paths, dry_run=False)
    branding.apply_grub()
    content = paths.grub_default.read_text(encoding="utf-8")
    assert content.count("GRUB_BACKGROUND=") == 1  # second wiring must not duplicate


def test_grub_dry_run_reports_steps_without_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    def boom(cmd: list):
        raise AssertionError("dry-run must not execute commands")

    monkeypatch.setattr(B, "run_command", boom)
    paths = make_paths(tmp_path)
    theme_txt = make_theme(tmp_path)
    make_grub_default(tmp_path, theme=theme_txt)
    B.Branding(paths, dry_run=True).apply_grub()
    # Nothing written, theme background untouched.
    assert (theme_txt.parent / "background.png").read_bytes() == b"stock-theme-bg"
    assert not paths.grub_splash.exists()


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
