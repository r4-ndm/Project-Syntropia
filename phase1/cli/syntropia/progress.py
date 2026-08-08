"""Terminal progress: npm-style single-line spinner + checkmarks + progress bar.

Uses ``\r`` carriage-return for the spinner (works in every terminal).
Falls back to plain ``print()`` when stderr is not a TTY.

Usage inside an installer::

    from .progress import StepProgress

    steps = [
        ("Toolchain",     "Checking wine, winetricks"),
        ("Prefix",        "Provisioning Wine prefix"),
        ("Overrides",     "Applying DLL overrides"),
        ("Winetricks",    "Installing winetricks packages"),
        ("Yabridge",      "Registering plugin dirs"),
        ("Source",        "Finding installer file"),
        ("Install",       "Running install commands"),
        ("Sync",          "Syncing yabridge plugins"),
    ]

    with StepProgress("😈 Installing Ableton Live 12 (12.1.10)", steps) as p:
        p.step(0)
        # … do work …
        p.done(0, "wine, winetricks present")

        p.step(1)
        # … do work …
        p.done(1, "provisioned")

        # … etc …
"""

from __future__ import annotations

import sys
import threading
import time

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class StepProgress:
    """Single-line spinner with permanent ✅ lines as each step completes.

    When stderr is a TTY the spinner animates in-place via ``\r``.
    Otherwise each step prints a plain line — safe for pipes and pytest.
    """

    def __init__(
        self,
        title: str,
        steps: list[tuple[str, str]],
    ) -> None:
        self.title = title
        self.steps = steps  # [(name, description), …]
        self._n = len(steps)
        self._current_label: str = ""
        self._spinner_idx = 0
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._tty = sys.stderr.isatty()

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def step(self, index: int) -> None:
        """Update the spinner message to show this step."""
        if index >= self._n:
            return
        _name, desc = self.steps[index]
        with self._lock:
            self._current_label = desc
        if not self._tty:
            sys.stderr.write(f"  ⠋ {desc}\n")

    def done(self, index: int, detail: str = "") -> None:
        """Print a permanent checkmark for the completed step."""
        if index >= self._n:
            return
        label, _desc = self.steps[index]
        msg = f"  ✅ {label}"
        if detail:
            msg += f"  \033[2m{detail}\033[0m"
        if self._tty:
            sys.stderr.write(f"\r\033[K{msg}\n")
        else:
            sys.stderr.write(msg + "\n")
        sys.stderr.flush()

    def error(self, index: int, detail: str = "") -> None:
        """Print a ❌ for a failed step."""
        if index >= self._n:
            return
        label, _desc = self.steps[index]
        msg = f"  ❌ {label}"
        if detail:
            msg += f"  \033[2m{detail}\033[0m"
        if self._tty:
            sys.stderr.write(f"\r\033[K{msg}\n")
        else:
            sys.stderr.write(msg + "\n")
        sys.stderr.flush()

    # ------------------------------------------------------------------
    # context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "StepProgress":
        if self._tty:
            sys.stderr.write("\033[?25l")  # hide cursor
        if self.title:
            sys.stderr.write(f"\033[1m{self.title}\033[0m\n")

        self._running = True
        if self._tty:
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *args: object) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1)
        if self._tty:
            sys.stderr.write("\r\033[K")  # clear spinner line
            sys.stderr.write("\033[?25h\n")  # show cursor
        sys.stderr.flush()

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------

    def _spin(self) -> None:
        while self._running:
            with self._lock:
                self._spinner_idx += 1
                frame = SPINNER_FRAMES[self._spinner_idx % len(SPINNER_FRAMES)]
                label = self._current_label
            if label:
                sys.stderr.write(f"\r\033[K  {frame} {label}...")
                sys.stderr.flush()
            time.sleep(0.08)


# ------------------------------------------------------------------
# determinate progress bar (for downloads, large extractions, etc.)
# ------------------------------------------------------------------

BAR_WIDTH = 30
BAR_FILLED = "█"
BAR_EMPTY = "░"


class ProgressBar:
    """A single determinate progress bar for file-size operations.

        total = os.path.getsize("big.zip")
        with ProgressBar(total, desc="Extracting") as bar:
            for chunk in read_chunks():
                bar.update(len(chunk))

    When stderr is not a TTY, a simple percentage line is printed
    every 10% instead.
    """

    def __init__(
        self,
        total: int,
        desc: str = "",
        unit: str = "B",
    ) -> None:
        self.total = max(total, 1)
        self.desc = desc
        self.unit = unit
        self._current: int = 0
        self._tty = sys.stderr.isatty()
        self._last_tick_pct: int = -1

    def update(self, n: int) -> None:
        """Advance the bar by *n* units."""
        self._current = min(self._current + n, self.total)
        self._draw()

    def set(self, n: int) -> None:
        """Set the bar position to *n* units."""
        self._current = min(n, self.total)
        self._draw()

    def _draw(self) -> None:
        pct = int(100 * self._current / self.total)
        if self._tty:
            filled = int(BAR_WIDTH * self._current / self.total)
            bar = BAR_FILLED * filled + BAR_EMPTY * (BAR_WIDTH - filled)
            label = f"{self.desc}  " if self.desc else ""
            sys.stderr.write(
                f"\r\033[K{label}{bar}  {pct}%  "
                f"({_human_size(self._current)}/{_human_size(self.total)})"
            )
            sys.stderr.flush()
        else:
            tick = pct // 10 * 10
            if tick != self._last_tick_pct:
                self._last_tick_pct = tick
                label = f"{self.desc}: " if self.desc else ""
                sys.stderr.write(f"{label}{pct}% ({_human_size(self._current)}/{_human_size(self.total)})\n")

    def done(self) -> None:
        """Complete the bar at 100 % and move to the next line."""
        self._current = self.total
        self._draw()
        if self._tty:
            sys.stderr.write("\n")
        sys.stderr.flush()

    def __enter__(self) -> "ProgressBar":
        self._draw()
        if self._tty:
            sys.stderr.write("\033[?25l")
        return self

    def __exit__(self, *args: object) -> None:
        if self._tty:
            sys.stderr.write("\033[?25h")
        sys.stderr.flush()


def _human_size(n: int) -> str:
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.1f} GB"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f} MB"
    if n >= 1_000:
        return f"{n / 1_000:.1f} KB"
    return f"{n} B"
