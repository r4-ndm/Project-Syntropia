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

# Determinate step-progress bar (how far through the pipeline we are).
STEP_BAR_WIDTH = 20
STEP_BAR_FILLED = "█"
STEP_BAR_EMPTY = "░"


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
        self._current_index = 0
        self._spinner_idx = 0
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._tty = sys.stderr.isatty()
        self._drawn = False  # spinner + bar lines currently on screen

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def _pos(self, index: int) -> str:
        """Position label like ``[4/9 44%]`` for step *index* (0-based).

        The percentage counts steps *completed through* this one, so the
        bar reaches 100% exactly when the last step is running.
        """
        pct = int(100 * (index + 1) / self._n) if self._n else 0
        return f"[{index + 1}/{self._n} {pct}%]"

    def step(self, index: int) -> None:
        """Update the spinner message to show this step."""
        if index >= self._n:
            return
        _name, desc = self.steps[index]
        with self._lock:
            self._current_label = desc
            self._current_index = index
        if not self._tty:
            sys.stderr.write(f"  ⠋ {self._pos(index)} {desc}\n")

    def update_label(self, label: str) -> None:
        """Change the spinner text mid-step (e.g. elapsed time)."""
        with self._lock:
            self._current_label = label

    def done(self, index: int, detail: str = "") -> None:
        """Print a permanent checkmark for the completed step."""
        if index >= self._n:
            return
        label, _desc = self.steps[index]
        msg = f"  ✅ {label}  \033[2m{self._pos(index)}\033[0m"
        if detail:
            msg += f"  \033[2m{detail}\033[0m"
        if self._tty:
            with self._lock:
                if self._drawn:
                    self._clear_spinner()
                sys.stderr.write(msg + "\n")
        else:
            sys.stderr.write(msg + "\n")
        sys.stderr.flush()

    def error(self, index: int, detail: str = "") -> None:
        """Print a ❌ for a failed step."""
        if index >= self._n:
            return
        label, _desc = self.steps[index]
        msg = f"  ❌ {label}  \033[2m{self._pos(index)}\033[0m"
        if detail:
            msg += f"  \033[2m{detail}\033[0m"
        if self._tty:
            with self._lock:
                if self._drawn:
                    self._clear_spinner()
                sys.stderr.write(msg + "\n")
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
            with self._lock:
                if self._drawn:
                    self._clear_spinner()
                sys.stderr.write("\033[?25h")  # show cursor
        sys.stderr.flush()

    def _clear_spinner(self) -> None:
        """Erase the two live lines (spinner + bar) and leave the cursor
        on the row where the next permanent line will be written."""
        # Cursor sits at the end of the bar line (row R+1); the spinner is
        # one row up at R.  Clear R, move down, clear R+1, back up to R.
        sys.stderr.write("\033[1A\r\033[K\033[1B\r\033[K\033[1A")
        self._drawn = False

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
                    idx = self._current_index
                    pct = int(100 * (idx + 1) / self._n) if self._n else 0
                    filled = int(STEP_BAR_WIDTH * pct / 100)
                    bar = STEP_BAR_FILLED * filled + STEP_BAR_EMPTY * (STEP_BAR_WIDTH - filled)
                    if self._drawn:
                        sys.stderr.write("\033[1A")  # back to the spinner row
                    sys.stderr.write(f"\r\033[K  {frame} [{idx + 1}/{self._n}] {label}...")
                    sys.stderr.write(f"\n\r\033[K  {bar} {pct}%")
                    self._drawn = True
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
