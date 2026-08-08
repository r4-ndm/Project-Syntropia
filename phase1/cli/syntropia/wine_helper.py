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

import glob
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from .brew import Brew, DEFAULT_SOURCE_LOOK_IN

if TYPE_CHECKING:
    from .progress import StepProgress

DLL_OVERRIDES_REGKEY = r"HKCU\Software\Wine\DllOverrides"

# The install pipeline only invokes wine/winetricks/yabridgectl; yabridge-host
# is the yabridge package's artifact on CachyOS (whose build omits the standalone
# `yabridge` daemon binary — a packaging quirk, not required to install VST3s).
TOOLCHAIN = ("wine", "winetricks", "yabridgectl", "yabridge-host.exe")


class WineHelperError(Exception):
    """An install step failed or the install was refused."""


def run_command(cmd: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """Run a command and capture output. Wrapped for test mocking."""
    return subprocess.run(cmd, capture_output=True, text=True, env=env)


def expand_path(value: str, home: Path) -> Path:
    """Expand ``$VAR`` and ``~`` in a manifest path, anchoring to the given home.

    ``~`` resolves against the injected home (not the process HOME) so the
    install target stays testable and predictable.
    """
    value = os.path.expandvars(value)
    if value.startswith("~"):
        value = str(home) + value[1:] if value != "~" else str(home)
    path = Path(value)
    if not path.is_absolute():
        path = home / path
    return path


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
        """
        if self.brew.wine_version == "syntropia-wine":
            return "/opt/syntropia-wine/bin"
        return None

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

    def _detail(self, text: str) -> None:
        """Set the progress detail for the current step (used by run_all)."""
        self._progress_detail = text

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

    def step_source(self) -> None:
        """Find (or download) the installer file declared in [source].

        Searches ``look_in`` directories for a file matching the glob
        pattern. If found, sets ``$SYNTROPIA_SOURCE`` in the install
        environment. If not found but ``url`` is set, downloads it to
        ``/tmp/``.
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
            result = run_command(
                ["curl", "-L", "--max-time", "900", "-o", str(dest), self.brew.source_url]
            )
            if result.returncode != 0:
                raise WineHelperError(
                    f"download failed: {result.stdout.strip() or result.stderr.strip()}"
                )
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
        env = self.build_env()
        for command in self.brew.install_commands:
            result = run_command(["bash", "-lc", command], env=env)
            if result.returncode != 0:
                raise WineHelperError(
                    f"install command failed ({result.returncode}): {command}\n"
                    f"{result.stdout.strip() or result.stderr.strip()}"
                )
        self._detail(f"{len(self.brew.install_commands)} commands")

    # -- runner -----------------------------------------------------------

    def run_all(self, progress: "StepProgress | None" = None) -> None:
        """Run every install step in order.

        When *progress* is given, each step reports through the animated
        step tracker instead of plain ``log()`` calls.
        """
        steps: list[tuple[int, str, object]] = [
            (0, "Toolchain", self.step_toolchain),
            (1, "Prefix", self.step_prefix),
            (2, "Overrides", self.step_overrides),
            (3, "Winetricks", self.step_winetricks),
            (4, "Yabridge", self.step_yabridge),
            (5, "Source", self.step_source),
            (6, "Install", self.step_install),
            (7, "Sync", self.step_yabridge_sync),
        ]

        if progress is not None:
            self._quiet = True

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
