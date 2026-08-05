"""syntropia transform — turn a running CachyOS system into Syntropia OS.

Safety contract (see agent-rules/transform-safety.md):

* ``--check`` (dry-run) never modifies anything — it only reports what would change.
* Real runs require explicit ``--yes`` confirmation and root privileges.
* Every step is idempotent — safe to run twice.
* The runner stops at the first error.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

AUDIO_PACKAGES = [
    "wine-staging",
    "winetricks",
    "yabridge",
    "pipewire",
    "pipewire-pulse",
    "wireplumber",
]

# Relative to the target user's home directory.
SYNTROPIA_DIRS_REL = [
    ".config/syntropia/brews",
    ".local/share/syntropia/prefixes",
    ".vst3/Syntropia",
]

PIPEWIRE_QUANTUM = 128

OS_RELEASE_CONTENT = (
    'NAME="Syntropia"\n'
    'PRETTY_NAME="Syntropia OS"\n'
    "ID=syntropia\n"
    "ID_LIKE=arch\n"
    "BUILD_ID=rolling\n"
    'ANSI_COLOR="38;2;255;0;0"\n'
    'HOME_URL="https://github.com/r4-ndm/Project-Syntropia"\n'
    "LOGO=syntropia\n"
)

LOGO_TEXT = """\
 __      __ _                  _              _
 \\ \\    / /(_)                | |            (_)
  \\ \\  / /  _  _ __  _ __ ___ | |_  _ __  __ _  _  ___
   \\ \\/ /  | || '_ \\| '__/ _ \\| __|| '__|/ _` || |/ _ \\
    \\  /   | || | | | | | (_) | |_ | |  | (_| || |  __/
     \\/    |_||_| |_|_|  \\___/ \\__||_|   \\__,_||_|\\___|

              the living computer
"""

SHELL_PROMPT_MARKER = "# syntropia-prompt (managed by syntropia transform)"
BASH_PROMPT_LINE = "export PS1='😈 \\u@\\h \\W $ '"
ZSH_PROMPT_LINE = "export PROMPT='😈 %n@%m %~ $ '"

PIPEWIRE_CONF = f"""# Syntropia low-latency tuning (managed by syntropia transform)
context.properties = {{
    default.clock.quantum = {PIPEWIRE_QUANTUM}
    default.clock.min-quantum = {PIPEWIRE_QUANTUM // 2}
    default.clock.max-quantum = {PIPEWIRE_QUANTUM * 2}
}}
"""

FASTFETCH_CONF = """{
  // Syntropia branding (managed by syntropia transform)
  "logo": { "source": "/usr/share/syntropia/logo.txt" }
}
"""


class TransformError(Exception):
    """A transform step failed or the transform was refused."""


@dataclass
class TransformPaths:
    """Every filesystem path the transform touches (injectable for tests)."""

    home: Path
    os_release: Path = Path("/etc/os-release")
    logo_dir: Path = Path("/usr/share/syntropia")
    usr_local_bin: Path = Path("/usr/local/bin")

    @property
    def logo_path(self) -> Path:
        return self.logo_dir / "logo.txt"

    @property
    def bashrc(self) -> Path:
        return self.home / ".bashrc"

    @property
    def zshrc(self) -> Path:
        return self.home / ".zshrc"

    @property
    def pipewire_conf_dir(self) -> Path:
        return self.home / ".config" / "pipewire" / "pipewire.conf.d"

    @property
    def fastfetch_dir(self) -> Path:
        return self.home / ".config" / "fastfetch"

    @property
    def syntropia_config_dir(self) -> Path:
        return self.home / ".config" / "syntropia"

    @classmethod
    def for_user(cls) -> "TransformPaths":
        """Paths for the real user even when transform runs under sudo."""
        sudo_user = os.environ.get("SUDO_USER")
        home = Path(os.environ.get("HOME", "/root"))
        if sudo_user and sudo_user != "root":
            home = Path("/home") / sudo_user
        return cls(home=home)


def run_command(cmd: list[str]) -> subprocess.CompletedProcess:
    """Run a command and capture output. Wrapped for test mocking."""
    return subprocess.run(cmd, capture_output=True, text=True)


class Transform:
    def __init__(self, paths: TransformPaths, *, dry_run: bool) -> None:
        self.paths = paths
        self.dry_run = dry_run
        self.planned = 0

    # -- helpers ----------------------------------------------------------

    def log(self, action: str, message: str) -> None:
        prefix = "[CHECK]" if self.dry_run else "[APPLY]"
        print(f"{prefix} {action}: {message}")

    def _would(self, action: str, message: str) -> None:
        self.planned += 1
        self.log(action, message)

    # -- guards -----------------------------------------------------------

    def ensure_root(self) -> None:
        if os.geteuid() != 0:
            raise TransformError("transform must be run as root: sudo syntropia transform")

    # -- steps ------------------------------------------------------------

    def missing_packages(self) -> list[str]:
        missing = []
        for pkg in AUDIO_PACKAGES:
            result = run_command(["pacman", "-Q", pkg])
            if result.returncode != 0:
                missing.append(pkg)
        return missing

    def apply_packages(self) -> None:
        missing = self.missing_packages()
        if not missing:
            self.log("packages", "all audio packages already installed")
            return
        self._would("packages", f"installing: {', '.join(missing)}")
        if self.dry_run:
            return
        result = run_command(["pacman", "-S", "--noconfirm", "--needed", *missing])
        if result.returncode != 0:
            raise TransformError("audio package install failed")

    def apply_os_release(self) -> None:
        path = self.paths.os_release
        if path.exists() and "ID=syntropia" in path.read_text(encoding="utf-8"):
            self.log("os-release", "already branded, skipping")
            return
        self._would("os-release", f"write {path} (original backed up)")
        if self.dry_run:
            return
        backup = path.with_name(path.name + ".syntropia.bak")
        if path.exists() and not backup.exists():
            shutil.copy2(path, backup)
        path.write_text(OS_RELEASE_CONTENT, encoding="utf-8")

    def apply_logo(self) -> None:
        self._would("logo", f"write {self.paths.logo_path}")
        if self.dry_run:
            return
        self.paths.logo_dir.mkdir(parents=True, exist_ok=True)
        self.paths.logo_path.write_text(LOGO_TEXT, encoding="utf-8")

    def apply_shell_prompt(self) -> None:
        for rc, line in ((self.paths.bashrc, BASH_PROMPT_LINE), (self.paths.zshrc, ZSH_PROMPT_LINE)):
            if rc.exists() and SHELL_PROMPT_MARKER in rc.read_text(encoding="utf-8"):
                self.log("prompt", f"{rc.name} already branded, skipping")
                continue
            self._would("prompt", f"append prompt to {rc}")
            if self.dry_run:
                continue
            rc.parent.mkdir(parents=True, exist_ok=True)
            with rc.open("a", encoding="utf-8") as fh:
                fh.write(f"\n{SHELL_PROMPT_MARKER}\n{line}\n")

    def apply_directories(self) -> None:
        for rel in SYNTROPIA_DIRS_REL:
            path = self.paths.home / rel
            self._would("dirs", f"create {path}")
            if not self.dry_run:
                path.mkdir(parents=True, exist_ok=True)

    def apply_pipewire(self) -> None:
        target = self.paths.pipewire_conf_dir / "99-syntropia.conf"
        self._would("pipewire", f"write {target} (quantum {PIPEWIRE_QUANTUM})")
        if self.dry_run:
            return
        self.paths.pipewire_conf_dir.mkdir(parents=True, exist_ok=True)
        target.write_text(PIPEWIRE_CONF, encoding="utf-8")

    def apply_fastfetch(self) -> None:
        target = self.paths.fastfetch_dir / "config.jsonc"
        self._would("fastfetch", f"write {target}")
        if self.dry_run:
            return
        self.paths.fastfetch_dir.mkdir(parents=True, exist_ok=True)
        target.write_text(FASTFETCH_CONF, encoding="utf-8")

    def deploy_cli(self) -> None:
        found = shutil.which("syntropia")
        target = self.paths.usr_local_bin / "syntropia"
        if not found:
            self.log("cli", "syntropia not on PATH — install the package first (skipped)")
            return
        self._would("cli", f"link {found} -> {target}")
        if self.dry_run:
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() or target.is_symlink():
            target.unlink()
        os.symlink(found, target)

    # -- runner -----------------------------------------------------------

    def run_all(self) -> None:
        self.apply_packages()
        self.apply_os_release()
        self.apply_logo()
        self.apply_shell_prompt()
        self.apply_directories()
        self.apply_pipewire()
        self.apply_fastfetch()
        self.deploy_cli()
        if self.dry_run:
            print(f"\nDry-run complete: {self.planned} action(s) would be taken.")
            print("Remember the safety rule: snapshot first, then run with --yes.")


def run_transform(*, check: bool, yes: bool, snapshot_desc: str | None = None) -> None:
    """Entry point used by the CLI. See module docstring for the safety contract."""
    transform = Transform(TransformPaths.for_user(), dry_run=check)

    if not check:
        if not yes:
            raise TransformError(
                "transform modifies the system — pass --yes to confirm "
                "(read agent-rules/transform-safety.md first)"
            )
        transform.ensure_root()
        if snapshot_desc:
            transform.log("snapshot", f"creating snapper snapshot 'pre-transform-{snapshot_desc}'")
            result = run_command(["snapper", "-c", "root", "create", "-d", f"pre-transform-{snapshot_desc}"])
            if result.returncode != 0:
                raise TransformError(f"snapper snapshot failed: {result.stdout.strip() or result.stderr.strip()}")

    transform.run_all()
