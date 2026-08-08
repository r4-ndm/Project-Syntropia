"""Terminal progress: npm-style spinner + step tracker + progress bar.

Uses ANSI escape sequences for in-place line updates. Falls back to
plain ``print()`` output when stderr is not a TTY (piped, redirected,
or running under test).

Usage inside an installer::

    from .progress import StepProgress

    steps = [
        ("Toolchain",     "Checking wine, winetricks, …"),
        ("Prefix",        "Provisioning Wine prefix"),
        ("Overrides",     "Applying DLL overrides"),
        ("Winetricks",    "Installing winetricks packages"),
        ("Source",        "Finding installer file"),
        ("Install",       "Running install commands"),
        ("Sync",          "Syncing yabridge plugins"),
    ]

    with StepProgress("😈 Installing Abelton Live 12 (12.1.10)", steps) as p:
        p.step(0)
        # … do toolchain check …
        p.done(0, "wine, winetricks, yabridge all present")

        p.step(1)
        # … provision prefix …
        p.done(1, "prefix provisioned")

        # … etc …
"""

from __future__ import annotations

import sys
import threading
import time

SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class StepProgress:
    """Draws a step list with an animated spinner on the current step.

    Uses ANSI escape codes to update lines in-place.  When *stderr* is
    not a TTY (pipe, redirect, test harness) the spinner is suppressed
    and steps are printed as plain lines — safe for pytest output.
    """

    def __init__(
        self,
        title: str,
        steps: list[tuple[str, str]],
    ) -> None:
        self.title = title
        self.steps = steps  # [(name, description), …]
        self._n = len(steps)
        self._current: int = -1
        self._results: dict[int, tuple[str, str]] = {}  # idx → (status, detail)
        self._spinner_idx = 0
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._tty = sys.stderr.isatty()

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def step(self, index: int) -> None:
        """Move the spinner to *index* (0-based)."""
        if index >= self._n:
            return
        with self._lock:
            self._current = index

    def done(self, index: int, detail: str = "") -> None:
        """Mark step *index* as completed, optionally with a short detail."""
        if index >= self._n:
            return
        with self._lock:
            self._results[index] = ("done", detail)
            self._current = index + 1
        if self._tty:
            self._render_one(index)
        else:
            label, _desc = self.steps[index]
            msg = f"  ✅ {label}"
            if detail:
                msg += f"  {detail}"
            sys.stderr.write(msg + "\n")

    def error(self, index: int, detail: str = "") -> None:
        """Mark step *index* as failed."""
        if index >= self._n:
            return
        with self._lock:
            self._results[index] = ("error", detail)
        self._render_one(index)

    # ------------------------------------------------------------------
    # context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "StepProgress":
        if self._tty:
            sys.stderr.write("\033[?25l")  # hide cursor
        if self.title:
            sys.stderr.write(f"\033[1m{self.title}\033[0m\n\n")
        if self._tty:
            # Print the initial (empty) step list and remember its position.
            sys.stderr.write("\033[s")  # save cursor
            for _ in self.steps:
                sys.stderr.write("  ⬜ \n")
            sys.stderr.write(f"\033[{self._n}A")  # jump back to first step line
        else:
            for name, desc in self.steps:
                sys.stderr.write(f"  ⬜ {name}: {desc}\n")

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
                for i in range(self._n):
                    if i not in self._results:
                        self._results[i] = ("done", "")
                self._current = self._n
            self._render_all()
            sys.stderr.write("\033[?25h\n")  # show cursor + final newline
        sys.stderr.flush()

    # ------------------------------------------------------------------
    # internal rendering (all under self._lock for thread safety)
    # ------------------------------------------------------------------

    def _spin(self) -> None:
        while self._running:
            with self._lock:
                self._spinner_idx += 1
                self._render_current_locked()
            time.sleep(0.08)

    def _render_one(self, index: int) -> None:
        if not self._tty:
            return
        with self._lock:
            self._emit_line(index)
            cur = self._current
            if 0 <= cur < self._n and cur != index:
                self._emit_line(cur)
            sys.stderr.flush()

    def _render_current_locked(self) -> None:
        """Render the spinner line (caller must hold lock)."""
        cur = self._current
        if 0 <= cur < self._n:
            self._emit_line(cur, locked=True)
            sys.stderr.flush()

    def _render_all(self) -> None:
        if not self._tty:
            return
        with self._lock:
            for i in range(self._n):
                self._emit_line(i)
            sys.stderr.flush()

    def _emit_line(self, index: int, *, locked: bool = False) -> None:
        """Write one step line at its absolute position, then restore cursor.

        When *locked* is True the caller already holds ``self._lock``.
        """
        sys.stderr.write("\033[s")  # save cursor
        row = self._row_for(index)
        sys.stderr.write(f"\033[{row};1H\033[K")  # move + clear
        label, _desc = self.steps[index]

        if index in self._results:
            status, detail = self._results[index]
            icon = "✅" if status == "done" else "❌"
            line = f"  {icon} {label}"
            if detail:
                line += f"  \033[2m{detail}\033[0m"
        elif index == self._current:
            frame = SPINNER_FRAMES[self._spinner_idx % len(SPINNER_FRAMES)]
            line = f"  {frame} {label}"
        else:
            line = f"  ⬜ {label}"

        sys.stderr.write(line)
        sys.stderr.write("\033[u")  # restore cursor

    def _row_for(self, index: int) -> int:
        """Absolute terminal row for step <index> (1-based)."""
        title_rows = 2 if self.title else 0
        return title_rows + index + 1


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
            # Non-TTY: print a line every 10 %.
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
