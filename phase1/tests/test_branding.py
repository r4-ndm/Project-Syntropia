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
    lines = ["GRUB_DEFAULT=0", "GRUB_TIMEOUT='5'", "GRUB_CMDLINE_LINUX_DEFAULT='quiet splash'"]
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


# --- GRUB ---------------------------------------------------------------


def test_grub_comments_out_background_sets_gfxmode_bgrt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """GRUB gets clean background + GFXMODE=1920x1080 + bgrt_disable."""
    calls: list = []
    monkeypatch.setattr(B, "run_command", noop_run(calls))
    paths = make_paths(tmp_path)
    grub_default = make_grub_default(tmp_path, theme=None)
    grub_default.write_text(
        grub_default.read_text(encoding="utf-8")
        + 'GRUB_BACKGROUND="/boot/grub/splash.png"\nGRUB_GFXMODE=auto\n',
        encoding="utf-8",
    )
    B.Branding(paths, dry_run=False).apply_grub()
    content = grub_default.read_text(encoding="utf-8")
    assert "#GRUB_BACKGROUND commented out" in content
    assert 'GRUB_BACKGROUND="/boot/grub/splash.png"' not in content
    assert "GRUB_GFXMODE=1920x1080" in content
    assert "GRUB_GFXMODE=auto" not in content
    assert "bgrt_disable" in content
    assert any(
        str(c[0]).endswith("grub-mkconfig") and str(c[-1]).endswith("grub.cfg")
        for c in calls
    )


def test_grub_already_clean_is_noop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """When already clean, do nothing."""
    calls: list = []
    monkeypatch.setattr(B, "run_command", noop_run(calls))
    paths = make_paths(tmp_path)
    make_grub_default(tmp_path, theme=None)
    B.Branding(paths, dry_run=False).apply_grub()
    first_calls = len(calls)
    B.Branding(paths, dry_run=False).apply_grub()
    assert len(calls) == first_calls


def test_grub_skips_without_default_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """If /etc/default/grub doesn't exist, skip gracefully."""
    monkeypatch.setattr(B, "run_command", noop_run([]))
    paths = make_paths(tmp_path)
    B.Branding(paths, dry_run=False).apply_grub()


def test_grub_dry_run_changes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Dry-run must not modify /etc/default/grub or call grub-mkconfig."""
    calls: list = []

    def boom(cmd: list):
        calls.append(cmd)
        raise AssertionError("dry-run must not execute commands")

    monkeypatch.setattr(B, "run_command", boom)
    paths = make_paths(tmp_path)
    grub_default = make_grub_default(tmp_path, theme=None)
    grub_default.write_text(
        grub_default.read_text(encoding="utf-8")
        + 'GRUB_BACKGROUND="/boot/grub/splash.png"\n',
        encoding="utf-8",
    )
    original = grub_default.read_text(encoding="utf-8")
    B.Branding(paths, dry_run=True).apply_grub()
    assert grub_default.read_text(encoding="utf-8") == original
    assert calls == []


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


# --- runner -------------------------------------------------------------


def test_apply_all_skips_without_assets(tmp_path: Path, capsys: pytest.CaptureFixture):
    paths = make_paths(tmp_path, assets=tmp_path / "nope")
    B.Branding(paths, dry_run=False).apply_all()
    out = capsys.readouterr().out
    assert "not found" in out
