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


def render_page(entries) -> bytes:
    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("<!--CATALOG-->", build_grid(entries))
    return html.encode("utf-8")


def open_browser(url: str) -> bool:
    """Open the dialog as a NATIVE-LOOKING window, not a browser tab.

    Chromium-family browsers (brave, chromium, chrome, edge, vivaldi,
    opera) support --app=URL: a frameless window with no tabs/URL bar,
    titled by the page — i.e. it looks like a standalone app dialog. That
    is the whole point of this dialog, so we use it whenever available and
    only fall back to a plain browser window otherwise.
    """
    app_flags = [f"--app={url}", "--window-size=920,800",
                 "--no-first-run", "--no-default-browser-check"]
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
    # No chromium-family browser — plain window (firefox, epiphany, etc.)
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
            self._send(200, render_page(self.server.entries), "text/html; charset=utf-8")
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
        else:
            self._send(404, b"not found")

        # Once the page has answered, stop accepting connections so the
        # server process exits and the wizard continues. Give the response a
        # moment to flush before tearing down.
        if self.server.done:
            threading.Timer(0.5, self.server.shutdown).start()


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
