"""syntropia wine-helper — the Wine/yabridge install engine.

Drives ``syntropia install <brew>`` end to end:

1. checks the toolchain (wine, winetricks, yabridgectl, yabridge-host.exe)
2. provisions the isolated Wine prefix (``wineboot -u``)
3. persists DLL overrides into the prefix registry
4. runs the manifest's winetricks packages
5. registers VST3 plugin dirs with ``yabridgectl``
6. runs the manifest's install commands (with ``$WINEPREFIX`` set)
7. re-syncs yabridgectl so the freshly copied VST3 gets bridged

Safety contract (see agent-rules/transform-safety.md):

* ``--check`` (dry-run) only prints the plan — nothing runs.
* Real runs require explicit ``--yes`` (enforced in the CLI layer).
* Every step is idempotent — safe to run twice.
* The runner stops at the first error.
"""

from __future__ import annotations

import os
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from .brew import Brew, DEFAULT_SOURCE_LOOK_IN, WINE_BUILD_BIN_DIRS
from .process import expand_path, run_command
from .vendor import VendorError, link_vendor_data

if TYPE_CHECKING:
    from .progress import ProgressBar, StepProgress

DLL_OVERRIDES_REGKEY = r"HKCU\Software\Wine\DllOverrides"

# The install pipeline only invokes wine/winetricks/yabridgectl; yabridge-host
# is the yabridge package's artifact on CachyOS (whose build omits the standalone
# `yabridge` daemon binary — a packaging quirk, not required to install VST3s).
TOOLCHAIN = ("wine", "winetricks", "yabridgectl", "yabridge-host.exe")

# The install pipeline, in order: (display label, progress description).
# This is the single source of truth — the CLI derives its progress display
# from it, and run_all maps each label to its step method via _STEP_METHODS.
# Add a new step here and in _STEP_METHODS; never in cli.py.
STEP_LABELS: list[tuple[str, str]] = [
    ("Toolchain", "Checking wine, winetricks, yabridge"),
    ("Prefix", "Provisioning Wine prefix"),
    ("Overrides", "Applying DLL overrides"),
    ("Winetricks", "Installing winetricks packages"),
    ("Yabridge", "Registering plugin directories"),
    ("Source", "Finding installer file"),
    ("Install", "Running install commands"),
    ("Vendor", "Linking vendor data (Arturia etc.)"),
    ("Sync", "Syncing yabridge plugins"),
]

# STEP_LABELS label -> WineInstaller method that performs the step.
_STEP_METHODS: dict[str, str] = {
    "Toolchain": "step_toolchain",
    "Prefix": "step_prefix",
    "Overrides": "step_overrides",
    "Winetricks": "step_winetricks",
    "Yabridge": "step_yabridge",
    "Source": "step_source",
    "Install": "step_install",
    "Vendor": "step_vendor_data",
    "Sync": "step_yabridge_sync",
}


class WineHelperError(Exception):
    """An install step failed or the install was refused."""


@dataclass
class WineInstaller:
    """Executes a single :class:`~syntropia.brew.Brew` manifest."""

    brew: Brew
    dry_run: bool = False
    home: Path | None = None

    def __post_init__(self) -> None:
        if self.home is None:
            self.home = Path(os.path.expanduser("~"))

    # -- helpers ----------------------------------------------------------

    @property
    def prefix(self) -> Path:
        return expand_path(self.brew.wine_prefix, self.home)

    def prefix_is_provisioned(self) -> bool:
        return (self.prefix / "system.reg").exists()

    def _wine_bin_dir(self) -> str | None:
        """Resolve a custom Wine build path from the brew's wine_version.

        Returns a directory to prepend to PATH, or None to use system Wine.
        The known-build table lives in brew.WINE_BUILD_BIN_DIRS.
        """
        return WINE_BUILD_BIN_DIRS.get(self.brew.wine_version)

    def toolchain_missing(self) -> list[str]:
        wine_dir = self._wine_bin_dir()
        if wine_dir:
            saved_path = os.environ.get("PATH", "")
            os.environ["PATH"] = f"{wine_dir}:{saved_path}"
            try:
                return [tool for tool in TOOLCHAIN if shutil.which(tool) is None]
            finally:
                os.environ["PATH"] = saved_path
        return [tool for tool in TOOLCHAIN if shutil.which(tool) is None]

    _source_path: Path | None = field(default=None, init=False)

    def build_env(self) -> dict[str, str]:
        env = dict(os.environ)
        wine_dir = self._wine_bin_dir()
        if wine_dir:
            env["PATH"] = f"{wine_dir}:{env.get('PATH', '')}"
        env.update(self.brew.environment)
        # Engine invariants must win — a manifest cannot clobber the prefix it
        # itself declared.
        env["WINEPREFIX"] = str(self.prefix)
        env["WINEARCH"] = self.brew.wine_arch
        parts = [f"{dll}={mode}" for dll, mode in self.brew.wine_overrides.items()]
        existing = env.get("WINEDLLOVERRIDES", "").strip()
        if existing:
            parts.append(existing)
        if parts:
            env["WINEDLLOVERRIDES"] = ",".join(parts)
        # Expose the resolved source path so install commands can use it.
        if self._source_path is not None:
            env["SYNTROPIA_SOURCE"] = str(self._source_path)
        return env

    _progress_detail: str = ""
    _progress: "StepProgress | None" = None

    def _detail(self, text: str) -> None:
        """Set the progress detail for the current step (used by run_all)."""
        self._progress_detail = text

    def _elapsed(self) -> None:
        """Background timer that updates the progress label with elapsed time."""
        start = time.monotonic()
        while getattr(self, "_elapsed_running", True):
            elapsed = int(time.monotonic() - start)
            mins, secs = divmod(elapsed, 60)
            label = f"Running ({mins}m {secs}s elapsed)"
            if self._progress is not None:
                self._progress.update_label(label)
            time.sleep(5)

    _quiet: bool = False

    def log(self, action: str, message: str) -> None:
        if self._quiet:
            return  # progress tracker is active — detail goes via _detail()
        prefix = "[CHECK]" if self.dry_run else "[APPLY]"
        print(f"{prefix} {action}: {message}")

    def _would(self, action: str, message: str) -> None:
        self.log(action, message)

    # -- steps ------------------------------------------------------------

    def step_toolchain(self) -> None:
        missing = self.toolchain_missing()
        if missing:
            # Dry-run reports the gap and shows the rest of the plan; a real
            # run cannot proceed without the toolchain.
            self.log(
                "toolchain",
                "missing tools: "
                + ", ".join(missing)
                + " (run 'sudo syntropia transform' to install the audio stack)",
            )
            self._detail("run 'sudo syntropia transform' first")
            if not self.dry_run:
                raise WineHelperError(
                    "missing tools: "
                    + ", ".join(missing)
                    + " — run 'sudo syntropia transform' to install the audio stack first"
                )
            return
        self.log("toolchain", "wine, winetricks, yabridge, yabridgectl all present")
        self._detail("wine, winetricks, yabridge present")

    def _ensure_prefix_ownership(self) -> None:
        """Chown the prefix to the current user if it's owned by someone else.

        This prevents the "not owned by you" Wine error when a prefix was
        created by root (e.g. during a previous ``sudo`` run or by a guest
        agent) and the current user subsequently tries to use it.
        """
        if not self.prefix.exists():
            return
        try:
            current_uid = os.getuid()
            prefix_stat = self.prefix.stat()
            if prefix_stat.st_uid != current_uid:
                # Recursive chown of the whole prefix tree.
                run_command(["chown", "-R", str(current_uid), str(self.prefix)])
                self.log("prefix", f"re-owned {self.prefix} to uid {current_uid}")
        except OSError:
            pass

    def step_prefix(self) -> None:
        if self.prefix_is_provisioned():
            self._ensure_prefix_ownership()
            self.log("prefix", f"{self.prefix} already provisioned, skipping")
            self._detail("already provisioned")
            return
        self._would("prefix", f"provision Wine prefix at {self.prefix} (wineboot -u)")
        if self.dry_run:
            self._detail(f"would provision {self.prefix}")
            return
        self.prefix.parent.mkdir(parents=True, exist_ok=True)
        result = run_command(["wineboot", "-u"], env=self.build_env())
        if result.returncode != 0:
            raise WineHelperError(
                f"wineboot failed: {result.stdout.strip() or result.stderr.strip()}"
            )
        self._detail("provisioned")

    def step_overrides(self) -> None:
        if not self.brew.wine_overrides:
            self.log("overrides", "no DLL overrides declared in manifest")
            self._detail("none declared")
            return
        self._would(
            "overrides",
            f"persist {len(self.brew.wine_overrides)} DLL override(s) into prefix registry",
        )
        if self.dry_run:
            self._detail(f"would apply {len(self.brew.wine_overrides)} overrides")
            return
        for dll, mode in self.brew.wine_overrides.items():
            result = run_command(
                [
                    "wine",
                    "reg",
                    "add",
                    DLL_OVERRIDES_REGKEY,
                    "/v",
                    dll,
                    "/d",
                    mode,
                    "/f",
                ],
                env=self.build_env(),
            )
            if result.returncode != 0:
                raise WineHelperError(
                    f"wine reg add {dll} failed: {result.stdout.strip() or result.stderr.strip()}"
                )
        self._detail(f"{len(self.brew.wine_overrides)} applied")

    def step_winetricks(self) -> None:
        if not self.brew.winetricks_packages:
            self.log("winetricks", "no winetricks packages declared in manifest")
            self._detail("none declared")
            return
        self._would(
            "winetricks", "install: " + ", ".join(self.brew.winetricks_packages)
        )
        if self.dry_run:
            self._detail(", ".join(self.brew.winetricks_packages) + " (dry-run)")
            return
        result = run_command(
            ["winetricks", "-q", *self.brew.winetricks_packages], env=self.build_env()
        )
        if result.returncode != 0:
            raise WineHelperError(
                f"winetricks failed: {result.stdout.strip() or result.stderr.strip()}"
            )
        self._detail(", ".join(self.brew.winetricks_packages))

    def step_yabridge(self) -> None:
        if not self.brew.yabridge_enabled:
            self.log("yabridge", "disabled in manifest")
            self._detail("disabled")
            return
        for plugin_dir in self.brew.plugin_dirs:
            # yabridgectl is a Rust binary — it does not expand ``~`` itself,
            # so resolve the path here (yabridgectl add can also take relative
            # paths, but an absolute one is unambiguous).
            resolved = expand_path(plugin_dir, self.home)
            self._would("yabridge", f"add plugin dir {resolved}")
            if not self.dry_run:
                result = run_command(
                    ["yabridgectl", "add", str(resolved)], env=self.build_env()
                )
                if result.returncode != 0:
                    raise WineHelperError(
                        f"yabridgectl add {resolved} failed: "
                        f"{result.stdout.strip() or result.stderr.strip()}"
                    )
        self._detail(f"{len(self.brew.plugin_dirs)} dirs")

    def step_yabridge_sync(self) -> None:
        """Bridge everything currently in the registered plugin dirs.

        Runs after the install commands — bridging before the VST3 exists
        would leave the freshly copied plugin unbridged until a manual
        ``yabridgectl sync``.
        """
        if not self.brew.yabridge_enabled:
            self._detail("disabled")
            return
        self._would("yabridge", "sync registered plugin dirs")
        if self.dry_run:
            self._detail("would sync")
            return
        result = run_command(["yabridgectl", "sync"], env=self.build_env())
        if result.returncode != 0:
            raise WineHelperError(
                f"yabridgectl sync failed: {result.stdout.strip() or result.stderr.strip()}"
            )
        self._detail("synced")

    def step_source(self, progress: "StepProgress | None" = None) -> None:
        """Find (or download) the installer file declared in [source].

        Searches ``look_in`` directories for a file matching the glob
        pattern. If found, sets ``$SYNTROPIA_SOURCE`` in the install
        environment. If not found but ``url`` is set, downloads it to
        ``/tmp/`` with a determinate progress bar.
        """
        if not self.brew.source_filename:
            self.log("source", "no [source] section in manifest, install commands use their own paths")
            self._detail("not needed")
            return

        look_in = self.brew.source_look_in or DEFAULT_SOURCE_LOOK_IN
        pattern = self.brew.source_filename

        self._would("source", f"looking for {pattern} in {', '.join(look_in)}")
        if self.dry_run:
            self._detail(f"would search {pattern}")
            return

        # Search for the file.
        matches: list[Path] = []
        for raw_dir in look_in:
            d = Path(raw_dir).expanduser()
            if not d.is_dir():
                continue
            for hit in sorted(d.glob(pattern)):
                if hit.is_file():
                    matches.append(hit)

        if matches:
            # Pick the largest match (most likely the complete download).
            found = max(matches, key=lambda p: p.stat().st_size)
            self.log("source", f"found: {found}")
            self._source_path = found
            self._detail(f"{found.name}")
            return

        # Not found — can we download?
        if self.brew.source_url:
            dest = Path("/tmp") / Path(self.brew.source_url).name
            self.log("source", f"not found locally, downloading from {self.brew.source_url}")
            self._download_with_progress(self.brew.source_url, dest)
            self.log("source", f"downloaded to {dest}")
            self._source_path = dest
            self._detail("downloaded")
            return

        # Neither found nor downloadable.
        raise WineHelperError(
            f"cannot find {pattern} in {', '.join(look_in)}. "
            f"Download the installer and place it in {look_in[0]}, "
            f"then re-run."
        )

    def _download_with_progress(self, url: str, dest: Path) -> None:
        """Download *url* to *dest* with a determinate progress bar."""
        from .progress import ProgressBar

        # Get content-length first.
        import urllib.request
        try:
            req = urllib.request.Request(url, method="HEAD")
            with urllib.request.urlopen(req, timeout=30) as resp:
                total = int(resp.headers.get("Content-Length", 0))
        except Exception:
            total = 0

        if total:
            bar = ProgressBar(total, desc="Downloading")
            bar.__enter__()
            try:
                with urllib.request.urlopen(url, timeout=900) as resp:
                    with dest.open("wb") as f:
                        while True:
                            chunk = resp.read(8192)
                            if not chunk:
                                break
                            f.write(chunk)
                            bar.update(len(chunk))
                bar.done()
            finally:
                bar.__exit__(None, None, None)
        else:
            # Fallback to curl if we can't get content-length.
            result = run_command(
                ["curl", "-L", "--max-time", "900", "-o", str(dest), url]
            )
            if result.returncode != 0:
                raise WineHelperError(
                    f"download failed: {result.stdout.strip() or result.stderr.strip()}"
                )

    def step_vendor_data(self) -> None:
        """Wire declared vendor data (Arturia-class) from a source prefix.

        Some vendors (Arturia, Native Instruments, …) split an install across
        a data directory (``C:\\ProgramData\\<Vendor>``) and an
        ``installdir`` registry key. Bitwig works without extra wiring because
        yabridge runs the plugin inside its *home* prefix; a wine-hosted DAW
        like Ableton runs the plugin in *its own* prefix, so the data dirs
        must be symlinked + keys added — exactly what ``plugins link --data``
        does. Best-effort: if the vendor isn't installed in the source prefix
        yet (fresh box), warn and continue — the app itself is already
        installed, and the user can link later with
        ``syntropia plugins link --data <Vendor>``.
        """
        vendors = self.brew.vendor_names or []
        if not vendors:
            self.log("vendor", "no vendor data declared in manifest")
            self._detail("none declared")
            return
        source = expand_path(self.brew.vendor_source or "~/.wine", self.home)
        total_dirs = 0
        total_reg = 0
        for vendor in vendors:
            try:
                result = link_vendor_data(
                    vendor,
                    source,
                    target_prefixes=[self.prefix],
                    home=self.home,
                    dry_run=self.dry_run,
                )
            except VendorError as exc:
                # Benign when the vendor's plugins aren't in the source
                # prefix (e.g. no Arturia installed yet) — don't fail the
                # DAW install over it.
                self.log("vendor", f"'{vendor}': skipped — {exc}")
                continue
            total_dirs += len(result.data_dirs)
            total_reg += len(result.registry_keys)
            verb = "would link" if self.dry_run else "linked"
            self.log(
                "vendor",
                f"'{vendor}': {verb} {len(result.data_dirs)} data dir(s), "
                f"{len(result.registry_keys)} registry value(s)",
            )
        if total_dirs or total_reg:
            self._detail(f"{total_dirs} dirs, {total_reg} reg")
        else:
            self._detail("none found")

    def step_install(self) -> None:
        self._would(
            "install",
            f"run {len(self.brew.install_commands)} command(s) from manifest",
        )
        if self.dry_run:
            for command in self.brew.install_commands:
                self.log("install", command)
            self._detail(f"{len(self.brew.install_commands)} commands (dry-run)")
            return

        # Start elapsed-time timer that updates the spinner label.
        self._elapsed_running = True
        timer = threading.Thread(target=self._elapsed, daemon=True)
        timer.start()

        try:
            env = self.build_env()
            for command in self.brew.install_commands:
                result = run_command(["bash", "-lc", command], env=env)
                if result.returncode != 0:
                    raise WineHelperError(
                        f"install command failed ({result.returncode}): {command}\n"
                        f"{result.stdout.strip() or result.stderr.strip()}"
                    )
            self._detail(f"{len(self.brew.install_commands)} commands")
        finally:
            self._elapsed_running = False
            timer.join(timeout=1)

    # -- runner -----------------------------------------------------------

    def run_all(self, progress: "StepProgress | None" = None) -> None:
        """Run every install step in order.

        When *progress* is given, each step reports through the animated
        step tracker instead of plain ``log()`` calls.
        """
        steps = [
            (idx, label, getattr(self, _STEP_METHODS[label]))
            for idx, (label, _desc) in enumerate(STEP_LABELS)
        ]

        if progress is not None:
            self._quiet = True
            self._progress = progress

        for idx, label, method in steps:
            if progress is not None:
                progress.step(idx)
            method()
            if progress is not None:
                # Each method sets a detail via _progress_detail
                progress.done(idx, getattr(self, "_progress_detail", ""))
                self._progress_detail = ""

        if self.dry_run:
            print(
                f"\nDry-run complete: install plan for '{self.brew.name} {self.brew.version}' "
                f"into {self.prefix}"
            )
            print("Nothing was changed. Re-run with --yes to actually install.")
        else:
            print(f"\n✨ '{self.brew.name} {self.brew.version}' installed into {self.prefix}")
