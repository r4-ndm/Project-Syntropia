"""syntropia transform — turn a running CachyOS system into Syntropia OS.

Safety contract (see agent-rules/transform-safety.md):

* ``--check`` (dry-run) never modifies anything — it only reports what would change.
* Real runs require explicit ``--yes`` confirmation and root privileges.
* Every step is idempotent — safe to run twice.
* The runner stops at the first error.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from syntropia.process import run_command, scan_processes

from .branding import Branding, BrandingPaths

AUDIO_PACKAGES = [
    "wine-staging",
    "winetricks",
    "yabridge",
    "yabridgectl",
    "pipewire",
    "pipewire-pulse",
    "wireplumber",
]

# Relative to the target user's home directory.
SYNTROPIA_DIRS_REL = [
    ".config/syntropia/brews",
    ".local/share/syntropia/prefixes",
    "VST3",  # the single user-facing drop folder for Windows VST3s (yabridge-bridged)
]

PIPEWIRE_QUANTUM = 128

# Packaged branding asset dir — single source of truth, reused by update.py
# and the transform CLI so the path can't drift between modules.
BRANDING_DIR = "/usr/share/syntropia/branding"

OS_RELEASE_CONTENT = (
    'NAME="Syntropia"\n'
    'PRETTY_NAME="CachyOS Syntropia"\n'
    # Syntropia is a CachyOS re-skin (Mint→Ubuntu model).  Keep ID=cachyos
    # so CachyOS-specific tooling (cachyos-kernel-manager, cachyos-hello,
    # cachyos-settings) keeps recognising the base system.  VARIANT_ID is
    # the freedesktop-standard way for a derivative to declare itself —
    # exactly how Fedora Silverblue uses ID=fedora + VARIANT_ID=silverblue.
    # When we become a proper fork with our own repos, ID may change.
    "ID=cachyos\n"
    'ID_LIKE="arch"\n'
    'VARIANT="Syntropia"\n'
    "VARIANT_ID=syntropia\n"
    "BUILD_ID=rolling\n"
    'ANSI_COLOR="38;2;255;0;0"\n'
    'HOME_URL="https://github.com/r4-ndm/Project-Syntropia"\n'
    "LOGO=syntropia\n"
)

# Keep in sync with Branding/syntropia/logo.txt (the packaged source of
# truth) — apply_logo() prefers the branding-dir copy; this is the fallback
# for systems without one.
LOGO_TEXT = """\
   *4*                                          *4*
    ****4444                             444****4
     *********4444                44444*****44*4
       4444444*********4     4********4444444**
        **4444444444444**4 4*44444444444444*4
         *4444444444444*4   4*444444444444*4
          **44444444444      444444444444*4
           **4444444**4       4**4444444**
            **44444*4  *******  4*444444
              4*44*4    **4**    4*44*4
               ***4      4*4      4**4
                *4        4        44
                  4*4444*444444**4*4
                   4*444444444444*4
                    4*4444444*4***
                     4*44444444*4
                      4*444444*4
                       4*4444*4
                        4*44*4
                         4**4
                          44
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

FASTFETCH_CONF_TEMPLATE = """{{
  // Syntropia branding (managed by syntropia transform)
  "logo": {{
    "source": "/usr/share/syntropia/logo.txt"{colors}
  }},
  "modules": [
    "title",
    "separator",
    "os",
    "kernel",
    "uptime",
    "packages",
    "shell",
    "display",
    "de",
    "wm",
    "terminal",
    "cpu",
    "gpu",
    "memory",
    "disk",
    "separator",
    "colors"
  ]
}}
"""

SDDM_AUTOLOGIN_MARKER = "# syntropia-autologin (managed by syntropia transform)"
SDDM_AUTOLOGIN_CONF = """\
# syntropia-autologin (managed by syntropia transform)
# Skips the SDDM password prompt — LUKS already unlocked the disk.
[Autologin]
User={user}
Session=plasma.desktop
"""


def build_fastfetch_conf(color_map: dict[str, str] | None = None) -> str:
    """Build the fastfetch config, merging a logo.color map if provided.

    ``color_map`` maps fastfetch placeholder numbers ("1".."9") to hex
    colors — the output of tools/png_to_ascii.py --color-map. Fastfetch
    resolves $N placeholders in the logo file through this map.
    """
    if not color_map:
        return FASTFETCH_CONF_TEMPLATE.format(colors="")
    entries = ",\n".join(
        f'    "{k}": "{v}"' for k, v in sorted(color_map.items())
    )
    colors_block = ",\n    \"color\": {\n" + entries + "\n    }"
    return FASTFETCH_CONF_TEMPLATE.format(colors=colors_block)



class TransformError(Exception):
    """A transform step failed or the transform was refused."""


@dataclass
class TransformPaths:
    """Every filesystem path the transform touches (injectable for tests)."""

    home: Path
    os_release: Path = Path("/etc/os-release")
    logo_dir: Path = Path("/usr/share/syntropia")
    usr_local_bin: Path = Path("/usr/local/bin")
    branding_dir: Path = Path(BRANDING_DIR)

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
    def sddm_conf_dir(self) -> Path:
        return Path("/etc/sddm.conf.d")

    @property
    def syntropia_config_dir(self) -> Path:
        return self.home / ".config" / "syntropia"

    @classmethod
    def for_user(cls) -> "TransformPaths":
        """Paths for the real user even when transform runs under sudo/pkexec."""
        home = cls._resolve_real_home()
        return cls(home=home)

    @staticmethod
    def _resolve_real_home() -> Path:
        """Resolve the real user's home even when running as root via sudo/pkexec."""
        real_user = TransformPaths._resolve_real_user()
        if real_user:
            return Path("/home") / real_user
        return Path(os.environ.get("HOME", "/root"))

    @staticmethod
    def _resolve_real_user() -> str | None:
        """Resolve the real login user even when elevated via sudo/pkexec/polkit."""
        # sudo sets SUDO_USER
        sudo_user = os.environ.get("SUDO_USER")
        if sudo_user and sudo_user != "root":
            return sudo_user
        # pkexec often sets PKEXEC_UID
        pkexec_uid = os.environ.get("PKEXEC_UID")
        if pkexec_uid:
            try:
                import pwd
                return pwd.getpwuid(int(pkexec_uid)).pw_name
            except (ValueError, KeyError):
                pass
        # os.getlogin() works under both sudo and pkexec
        try:
            login = os.getlogin()
            if login and login != "root":
                return login
        except OSError:
            pass
        return None


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

    @staticmethod
    def _wineservers_running(proc_root: Path = Path("/proc")) -> list[str]:
        """Names of any live wineserver processes (any prefix).

        Transform is system-wide (it (re)installs the wine stack and
        restarts pipewire), so a running wine session — a DAW open with
        its prefix's wineserver up — would be disrupted mid-flight.
        """
        servers: list[str] = []
        for _pid, _environ, cmdline in scan_processes(proc_root):
            argv = cmdline.split("\0")
            if argv and "wineserver" in argv[0]:
                servers.append(argv[0])
        return servers

    def ensure_wine_idle(self) -> None:
        """Refuse to transform while a wine session is running.

        Reinstalling wine-staging / restarting pipewire under a live DAW
        would corrupt the running session. Dry-run only warns — it changes
        nothing, so it cannot disrupt anything.
        """
        servers = self._wineservers_running()
        if not servers:
            return
        names = ", ".join(sorted(set(servers)))
        if not self.dry_run:
            raise TransformError(
                "a Wine session is running ("
                f"{names}) — close your DAW / audio apps and wait for the "
                "prefixes to shut down, then re-run transform."
            )
        self.log("wine", f"⚠ wine session running ({names}) — transform would refuse")

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
        if path.exists() and "VARIANT_ID=syntropia" in path.read_text(encoding="utf-8"):
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
        # Prefer a logo.txt dropped in the branding asset-dir (e.g. the
        # output of tools/png_to_ascii.py); fall back to the built-in art.
        custom = self.paths.branding_dir / "logo.txt"
        if custom.is_file():
            text = custom.read_text(encoding="utf-8")
            source = str(custom)
        else:
            text = LOGO_TEXT
            source = "built-in"
        self._would("logo", f"write {self.paths.logo_path} (from {source})")
        if self.dry_run:
            return
        self.paths.logo_dir.mkdir(parents=True, exist_ok=True)
        self.paths.logo_path.write_text(text, encoding="utf-8")

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
        # Merge a color map dropped in the asset-dir (from png_to_ascii --color).
        color_map: dict[str, str] | None = None
        color_file = self.paths.branding_dir / "fastfetch-color.json"
        if color_file.is_file():
            try:
                color_map = json.loads(color_file.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise TransformError(f"invalid color map {color_file}: {exc}") from exc
        conf = build_fastfetch_conf(color_map)
        note = f" ({len(color_map)} colors)" if color_map else ""
        self._would("fastfetch", f"write {target}{note}")
        if self.dry_run:
            return
        self.paths.fastfetch_dir.mkdir(parents=True, exist_ok=True)
        target.write_text(conf, encoding="utf-8")

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

    def apply_autologin(self) -> None:
        """Enable SDDM auto-login for the real user (skips the login screen).

        Only applies when running under sudo (the transform's normal mode).
        Auto-login is safe when LUKS full-disk encryption is in use — the
        disk has already been unlocked before SDDM runs.
        """
        owner = self._target_user()
        if owner is None:
            self.log("autologin", "not running under sudo, skipping")
            return
        target = self.paths.sddm_conf_dir / "syntropia-autologin.conf"
        if target.exists() and SDDM_AUTOLOGIN_MARKER in target.read_text(encoding="utf-8"):
            self.log("autologin", f"{target} already configured for {owner}, skipping")
            return
        self._would("autologin", f"enable auto-login for {owner} ({target})")
        if self.dry_run:
            return
        self.paths.sddm_conf_dir.mkdir(parents=True, exist_ok=True)
        target.write_text(SDDM_AUTOLOGIN_CONF.format(user=owner), encoding="utf-8")

    def apply_branding(self) -> None:
        if not self.paths.branding_dir.is_dir():
            self.log(
                "branding",
                f"no assets in {self.paths.branding_dir} — use --branding-dir (skipped)",
            )
            return
        branding = Branding(
            BrandingPaths(home=self.paths.home, assets_dir=self.paths.branding_dir),
            dry_run=self.dry_run,
        )
        branding.apply_all()
        self.planned += branding.planned

    # -- runner -----------------------------------------------------------

    def _target_user(self) -> str | None:
        """The real user when running under sudo/pkexec, else None."""
        return TransformPaths._resolve_real_user()

    def _fix_user_ownership(self) -> None:
        """Return home-dir files to the real user after a root transform.

        mkdir/write under sudo creates root-owned files in the user's home
        (wine refuses to use a prefix it doesn't own). Re-own the trees the
        transform manages.
        """
        owner = self._target_user()
        if owner is None:
            return
        managed = {
            self.paths.bashrc,
            self.paths.zshrc,
            self.paths.pipewire_conf_dir,
            self.paths.fastfetch_dir,
            self.paths.syntropia_config_dir,
            self.paths.home / ".local" / "share" / "syntropia",
            self.paths.home / ".vst3",  # yabridge stubs land under ~/.vst3/yabridge
            self.paths.home / "VST3",  # the user-facing drop folder
            self.paths.home / ".local" / "share" / "backgrounds",
        }
        for path in managed:
            if path.exists():
                run_command(["chown", "-R", owner, str(path)])

    def run_all(self) -> None:
        self.ensure_wine_idle()
        self.apply_packages()
        self.apply_os_release()
        self.apply_logo()
        self.apply_shell_prompt()
        self.apply_directories()
        self.apply_pipewire()
        self.apply_fastfetch()
        self.deploy_cli()
        self.apply_autologin()
        self.apply_branding()
        if not self.dry_run:
            self._fix_user_ownership()
        if self.dry_run:
            print(f"\nDry-run complete: {self.planned} action(s) would be taken.")
            print("Remember the safety rule: snapshot first, then run with --yes.")


def run_transform(
    *,
    check: bool,
    yes: bool,
    snapshot_desc: str | None = None,
    branding_dir: str | None = None,
) -> None:
    """Entry point used by the CLI. See module docstring for the safety contract."""
    paths = TransformPaths.for_user()
    if branding_dir:
        paths.branding_dir = Path(branding_dir).expanduser()
    transform = Transform(paths, dry_run=check)

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
