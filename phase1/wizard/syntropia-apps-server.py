#!/usr/bin/env python3
"""😈 Syntropia Apps Dialog server — renders the app grid in a browser tab.

A tiny local-only HTTP server (127.0.0.1, ephemeral port) that:

  * reads the pipe-delimited apps.list catalog,
  * injects the catalog as a Win98-style 4-column checkbox grid into
    syntropia-apps-dialog.html (same look as the PySide6 dialog),
  * opens the page in the default browser,
  * waits for the user to press OK or Cancel,
  * prints the checked package tags, one per line, to stdout — the same
    contract as `kdialog --checklist --separate-output` — so the wizard
    parses it identically. Exit 0 = OK, 1 = cancelled.

Dependencies: python3 (stdlib only — http.server, json, webbrowser) and any
installed browser. No packages to install — that's the whole point vs. the
PySide6 dialog, which needs the ~200 MB pyside6 package.

Usage: syntropia-apps-server.py <apps.list>
"""

import json
import shutil
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

GRID_COLUMNS = 4

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "syntropia-apps-dialog.html"


def paru_present() -> bool:
    """Whether the paru AUR helper is installed (the wizard needs it to
    install the checked apps). The dialog page bootstraps it if missing."""
    return shutil.which("paru") is not None


def load_catalog(path: str) -> list[tuple[str, str, str]]:
    """Parse apps.list -> [(category, name, package), ...] in file order."""
    entries: list[tuple[str, str, str]] = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split("|")
        if len(parts) < 3:
            continue
        cat, name, pkg = parts[0].strip(), parts[1].strip(), parts[2].strip()
        if pkg:
            entries.append((cat, name, pkg))
    return entries


def build_grid(entries: list[tuple[str, str, str]]) -> str:
    """Render one 4-column checkbox grid per category (placeholder-padded so
    the columns align across categories — mirrors the Qt dialog)."""
    categories: list[str] = []
    for cat, _name, _pkg in entries:
        if cat not in categories:
            categories.append(cat)

    parts: list[str] = []
    for cat in categories:
        cells = []
        col = 0
        for c, name, pkg in entries:
            if c != cat:
                continue
            cells.append(
                f'<label class="cell"><input type="checkbox" value="{pkg}">'
                f"{name}</label>"
            )
            col += 1
            if col == GRID_COLUMNS:
                col = 0
        # pad leftover cells so every category fills a full row of columns
        while col < GRID_COLUMNS:
            cells.append('<div class="cell placeholder"></div>')
            col += 1
        parts.append(
            f'<div class="cat-group"><div class="cat-title">{cat}</div>'
            f'<div class="cat-grid">{"".join(cells)}</div></div>'
        )
    return "\n".join(parts)


def render_page(entries, paru_ok: bool) -> bytes:
    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("<!--CATALOG-->", build_grid(entries))
    html = html.replace("<!--PARU-->", "yes" if paru_ok else "no")
    return html.encode("utf-8")


def has_3d_gpu() -> bool:
    """Detect whether the system has a working 3D GPU.

    Tries multiple methods:
    1. Check /sys/class/drm/card*/capabilities for 'number of cap sets' > 0
       (works on virtio-vga with virgl)
    2. Run glxinfo and check for 'direct rendering: Yes'
       (works on real hardware and VMs with virtio-gpu-gl)
    3. Check for presence of Mesa/OpenGL libraries

    Returns False if none succeed — Chromium's GPU compositing fails without
    3D, so we fall back to Firefox.
    """
    import glob as _glob
    import shutil

    # Method 1: DRM capabilities (virtio-vga with virgl)
    for caps_file in _glob.glob("/sys/class/drm/card*/capabilities"):
        try:
            text = Path(caps_file).read_text(encoding="utf-8", errors="ignore")
            for line in text.splitlines():
                if line.startswith("number of cap sets:"):
                    count = int(line.split(":")[1].strip())
                    if count > 0:
                        return True
        except Exception:
            continue

    # Method 2: glxinfo (real hardware or virtio-gpu-gl)
    if shutil.which("glxinfo"):
        try:
            result = subprocess.run(
                ["glxinfo"],
                capture_output=True, text=True, timeout=5
            )
            if "direct rendering: Yes" in result.stdout:
                return True
        except Exception:
            pass

    # Method 3: Check for Mesa/OpenGL libraries
    lib_paths = ["/usr/lib64/libGL.so.1", "/usr/lib/libGL.so.1",
                 "/usr/lib64/libEGL.so.1", "/usr/lib/libEGL.so.1"]
    if any(Path(p).exists() for p in lib_paths):
        # GL libraries exist — assume 3D is available
        # (this catches cases where glxinfo isn't installed but GL works)
        return True

    # No 3D detected
    return False


def open_browser(url: str) -> bool:
    """Open the dialog as a NATIVE-LOOKING window, not a browser tab.

    Chromium-family browsers (brave, chromium, chrome, edge, vivaldi,
    opera) support --app=URL: a frameless window with no tabs/URL bar,
    titled by the page — i.e. it looks like a standalone app dialog. That
    is the whole point of this dialog, so we use it whenever available and
    only fall back to a plain browser window otherwise.

    If the system lacks a 3D GPU (e.g. a QEMU/KVM VM with plain virtio-vga),
    Chromium's GPU compositing fails and shows a blank page. In that case,
    we skip Chromium entirely and fall back to Firefox, which uses its own
    software renderer and works reliably.
    """
    gpu_ok = has_3d_gpu()
    app_flags = [f"--app={url}", "--window-size=920,800",
                 "--no-first-run", "--no-default-browser-check"]
    if gpu_ok:
        # 3D GPU present — try Chromium-family browsers for the native app look
        for name in ("brave", "chromium", "google-chrome-stable", "google-chrome",
                     "microsoft-edge", "vivaldi", "opera", "thorium"):
            path = shutil.which(name)
            if not path:
                continue
            try:
                subprocess.Popen([path] + app_flags,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except OSError:
                continue
    # No 3D GPU or no Chromium-family browser — fall back to Firefox/Epiphany
    try:
        return webbrowser.open(url)
    except Exception:
        return False


class Handler(BaseHTTPRequestHandler):
    server_version = "syntropia/1.0"

    def log_message(self, fmt, *args):  # keep it quiet on stdout
        pass

    def _send(self, code: int, body: bytes, ctype: str = "text/plain") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, render_page(self.server.entries, self.server.paru_ok),
                       "text/html; charset=utf-8")
        else:
            self._send(404, b"not found")

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            payload = {}

        if self.path == "/done":
            self.server.packages = [str(p) for p in payload.get("packages", [])]
            self.server.done = True
            self._send(200, b"OK - you can close this tab.")
        elif self.path == "/cancel":
            self.server.cancelled = True
            self.server.done = True
            self._send(200, b"Cancelled - you can close this tab.")
        elif self.path == "/paru/install":
            # The page offers to bootstrap paru when it's missing. pkexec
            # shows the standard polkit password prompt; the response flushes
            # to the page as soon as pkexec returns.
            self._send_paru_install()
        else:
            self._send(404, b"not found")

        # Once the page has answered, stop accepting connections so the
        # server process exits and the wizard continues. Give the response a
        # moment to flush before tearing down.
        if self.server.done:
            threading.Timer(0.5, self.server.shutdown).start()

    def _send_paru_install(self) -> None:
        try:
            proc = subprocess.run(
                ["pkexec", "pacman", "-S", "--noconfirm", "paru"],
                capture_output=True, text=True, timeout=600)
        except Exception as exc:  # timeout, missing pkexec, etc.
            self._send(500, json.dumps({"ok": False, "output": str(exc)}).encode(),
                       "application/json")
            return
        ok = proc.returncode == 0 and paru_present()
        self.server.paru_ok = paru_present()
        body = json.dumps({
            "ok": ok,
            "output": (proc.stdout + proc.stderr)[-2000:],
        }).encode()
        self._send(200 if ok else 500, body, "application/json")


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: syntropia-apps-server.py <apps.list>", file=sys.stderr)
        return 2
    entries = load_catalog(sys.argv[1])
    if not entries:
        print("empty catalog", file=sys.stderr)
        return 2
    if not TEMPLATE.exists():
        print(f"template not found: {TEMPLATE}", file=sys.stderr)
        return 2

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.entries = entries
    server.packages = []
    server.cancelled = False
    server.done = False
    server.paru_ok = paru_present()

    port = server.server_address[1]
    url = f"http://127.0.0.1:{port}/"
    # Open as a native-looking app window (chromium --app=URL), falling
    # back to a plain browser window. If that fails, print the URL so the
    # wizard can surface it.
    if not open_browser(url):
        print(f"open {url} in your browser", file=sys.stderr)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 1

    if server.cancelled:
        return 1
    for pkg in server.packages:
        print(pkg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
