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
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .brew import Brew

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

    def toolchain_missing(self) -> list[str]:
        return [tool for tool in TOOLCHAIN if shutil.which(tool) is None]

    def build_env(self) -> dict[str, str]:
        env = dict(os.environ)
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
        return env

    def log(self, action: str, message: str) -> None:
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
            if not self.dry_run:
                raise WineHelperError(
                    "missing tools: "
                    + ", ".join(missing)
                    + " — run 'sudo syntropia transform' to install the audio stack first"
                )
            return
        self.log("toolchain", "wine, winetricks, yabridge, yabridgectl all present")

    def step_prefix(self) -> None:
        if self.prefix_is_provisioned():
            self.log("prefix", f"{self.prefix} already provisioned, skipping")
            return
        self._would("prefix", f"provision Wine prefix at {self.prefix} (wineboot -u)")
        if self.dry_run:
            return
        self.prefix.parent.mkdir(parents=True, exist_ok=True)
        result = run_command(["wineboot", "-u"], env=self.build_env())
        if result.returncode != 0:
            raise WineHelperError(
                f"wineboot failed: {result.stdout.strip() or result.stderr.strip()}"
            )

    def step_overrides(self) -> None:
        if not self.brew.wine_overrides:
            self.log("overrides", "no DLL overrides declared in manifest")
            return
        self._would(
            "overrides",
            f"persist {len(self.brew.wine_overrides)} DLL override(s) into prefix registry",
        )
        if self.dry_run:
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

    def step_winetricks(self) -> None:
        if not self.brew.winetricks_packages:
            self.log("winetricks", "no winetricks packages declared in manifest")
            return
        self._would(
            "winetricks", "install: " + ", ".join(self.brew.winetricks_packages)
        )
        if self.dry_run:
            return
        result = run_command(
            ["winetricks", "-q", *self.brew.winetricks_packages], env=self.build_env()
        )
        if result.returncode != 0:
            raise WineHelperError(
                f"winetricks failed: {result.stdout.strip() or result.stderr.strip()}"
            )

    def step_yabridge(self) -> None:
        if not self.brew.yabridge_enabled:
            self.log("yabridge", "disabled in manifest")
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

    def step_yabridge_sync(self) -> None:
        """Bridge everything currently in the registered plugin dirs.

        Runs after the install commands — bridging before the VST3 exists
        would leave the freshly copied plugin unbridged until a manual
        ``yabridgectl sync``.
        """
        if not self.brew.yabridge_enabled:
            return
        self._would("yabridge", "sync registered plugin dirs")
        if self.dry_run:
            return
        result = run_command(["yabridgectl", "sync"], env=self.build_env())
        if result.returncode != 0:
            raise WineHelperError(
                f"yabridgectl sync failed: {result.stdout.strip() or result.stderr.strip()}"
            )

    def step_install(self) -> None:
        self._would(
            "install",
            f"run {len(self.brew.install_commands)} command(s) from manifest",
        )
        if self.dry_run:
            for command in self.brew.install_commands:
                self.log("install", command)
            return
        env = self.build_env()
        for command in self.brew.install_commands:
            result = run_command(["bash", "-lc", command], env=env)
            if result.returncode != 0:
                raise WineHelperError(
                    f"install command failed ({result.returncode}): {command}\n"
                    f"{result.stdout.strip() or result.stderr.strip()}"
                )

    # -- runner -----------------------------------------------------------

    def run_all(self) -> None:
        self.step_toolchain()
        self.step_prefix()
        self.step_overrides()
        self.step_winetricks()
        self.step_yabridge()
        self.step_install()
        self.step_yabridge_sync()
        if self.dry_run:
            print(
                f"\nDry-run complete: install plan for '{self.brew.name} {self.brew.version}' "
                f"into {self.prefix}"
            )
            print("Nothing was changed. Re-run with --yes to actually install.")
        else:
            print(f"\n✅ '{self.brew.name} {self.brew.version}' installed into {self.prefix}")
