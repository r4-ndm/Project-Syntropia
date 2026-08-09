#!/usr/bin/env python3
"""😈 Syntropia Apps Dialog — native Qt grid dialog for the apps wizard.

Renders one 4-column grid of checkboxes per category (from the pipe-delimited
apps.list), padded with empty placeholder cells so every category's columns
align. So far more apps fit on screen than a flat list. Prints the
checked package tags, one per line, to stdout — the same contract as
`kdialog --checklist --separate-output` — so the wizard parses it exactly the
same way. Exit 0 = OK, 1 = cancelled.

Usage: syntropia-apps-dialog.py <apps.list>
"""

import math
import struct
import sys
import tempfile
import wave
from pathlib import Path

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

GRID_COLUMNS = 4


def _write_click_wav(path: Path) -> None:
    """Synthesize a short Win98-style click (decaying 2 kHz blip)."""
    rate = 22050
    dur = 0.03
    n = int(rate * dur)
    frames = bytearray()
    for i in range(n):
        t = i / rate
        env = math.exp(-t * 180)
        sample = int(0.6 * env * math.sin(2 * math.pi * 2000 * t) * 32767)
        frames += struct.pack("<h", sample)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(bytes(frames))


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


class AppsDialog(QDialog):
    def __init__(self, entries: list[tuple[str, str, str]]) -> None:
        super().__init__()
        self.setWindowTitle("😈 Syntropia — Pick your apps")
        self.resize(760, 600)
        self.setMinimumSize(640, 480)

        root = QVBoxLayout(self)

        intro = QLabel(
            "Check the apps to install — everything installs together.\n"
            "Cancel skips this permanently."
        )
        root.addWidget(intro)

        bulk = QHBoxLayout()
        select_all = QPushButton("Select All")
        clear_all = QPushButton("Clear All")
        select_all.clicked.connect(self.select_all)
        clear_all.clicked.connect(self.clear_all)
        bulk.addWidget(select_all)
        bulk.addWidget(clear_all)
        bulk.addStretch(1)
        root.addLayout(bulk)

        # categories in first-appearance (file) order
        categories: list[str] = []
        for cat, _name, _pkg in entries:
            if cat not in categories:
                categories.append(cat)

        self._click = None  # lazily-created QSoundEffect
        self._bulk = False  # suppress click sounds during select/clear all

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        outer = QVBoxLayout(content)

        self._boxes: dict[str, QCheckBox] = {}
        for cat in categories:
            group = QGroupBox(cat)
            group.setObjectName("catGroup")
            grid = QGridLayout(group)
            row = col = 0
            for c, name, pkg in entries:
                if c != cat:
                    continue
                box = QCheckBox(name)  # default: unchecked
                box.toggled.connect(self._on_toggled)
                grid.addWidget(box, row, col)
                self._boxes[pkg] = box
                col += 1
                if col == GRID_COLUMNS:
                    col = 0
                    row += 1
            # pad the leftover cells with empty placeholders so every
            # category grid is a full row of GRID_COLUMNS — keeps the
            # columns aligned with the categories below
            while col < GRID_COLUMNS:
                grid.addWidget(QWidget(), row, col)
                col += 1
            for i in range(GRID_COLUMNS):
                grid.setColumnStretch(i, 1)
            grid.setHorizontalSpacing(8)
            grid.setVerticalSpacing(8)
            outer.addWidget(group)

        outer.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        # classic Windows 98 look: gray canvas, beveled 3D borders
        self.setStyleSheet("""
            QDialog {
                background: #c0c0c0;
            }
            QLabel {
                color: #000000;
            }
            QScrollArea {
                background: #c0c0c0;
                border: 2px solid;
                border-top-color: #808080;
                border-left-color: #808080;
                border-bottom-color: #ffffff;
                border-right-color: #ffffff;
            }
            QGroupBox#catGroup {
                background: #c0c0c0;
                border: 1px solid #808080;
                margin-top: 1.2em;
                padding-top: 2px;
            }
            QGroupBox#catGroup::title {
                subcontrol-origin: margin;
                left: 6px;
                padding: 0 3px;
                color: #000080;
                font-weight: bold;
            }
            QCheckBox {
                background: #c0c0c0;
                border: 2px solid;
                border-top-color: #ffffff;
                border-left-color: #ffffff;
                border-bottom-color: #808080;
                border-right-color: #808080;
                padding: 4px 8px;
                spacing: 8px;
                color: #000000;
            }
            QCheckBox:checked {
                background: #d4d0c8;
                border-top-color: #808080;
                border-left-color: #808080;
                border-bottom-color: #ffffff;
                border-right-color: #ffffff;
            }
            QPushButton {
                border: 2px solid;
                border-top-color: #ffffff;
                border-left-color: #ffffff;
                border-bottom-color: #404040;
                border-right-color: #404040;
                background: #c0c0c0;
                color: #000000;
                padding: 3px 14px;
                border-radius: 0;
            }
        """)

    def select_all(self) -> None:
        self._bulk = True
        for box in self._boxes.values():
            box.setChecked(True)
        self._bulk = False

    def clear_all(self) -> None:
        self._bulk = True
        for box in self._boxes.values():
            box.setChecked(False)
        self._bulk = False

    def _on_toggled(self, checked: bool) -> None:
        if checked and not self._bulk:
            self._play_click()

    def _play_click(self) -> None:
        if self._click is None:
            self._click = self._make_click()
        if self._click is not None:
            self._click.play()

    def _make_click(self):
        """Lazily build the click sound effect; None if audio unavailable."""
        try:
            from PySide6.QtCore import QUrl
            from PySide6.QtMultimedia import QSoundEffect
        except ImportError:
            return None
        wav = Path(tempfile.gettempdir()) / "syntropia-click.wav"
        if not wav.exists():
            try:
                _write_click_wav(wav)
            except OSError:
                return None
        eff = QSoundEffect()
        eff.setSource(QUrl.fromLocalFile(str(wav)))
        eff.setVolume(0.6)
        return eff

    def selection(self) -> list[str]:
        return [pkg for pkg, box in self._boxes.items() if box.isChecked()]


def apply_win98_theme(app: QApplication) -> None:
    """Classic Windows 98 look: gray canvas + beveled 3D borders."""
    app.setStyle("windows")
    gray = QColor(192, 192, 192)
    pal = QPalette()
    pal.setColor(QPalette.Window, gray)
    pal.setColor(QPalette.WindowText, QColor(0, 0, 0))
    pal.setColor(QPalette.Base, QColor(255, 255, 255))
    pal.setColor(QPalette.AlternateBase, gray)
    pal.setColor(QPalette.Text, QColor(0, 0, 0))
    pal.setColor(QPalette.Button, gray)
    pal.setColor(QPalette.ButtonText, QColor(0, 0, 0))
    pal.setColor(QPalette.BrightText, QColor(255, 0, 0))
    pal.setColor(QPalette.Highlight, QColor(0, 0, 128))
    pal.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    pal.setColor(QPalette.PlaceholderText, QColor(128, 128, 128))
    pal.setColor(QPalette.ToolTipBase, QColor(255, 255, 220))
    pal.setColor(QPalette.ToolTipText, QColor(0, 0, 0))
    app.setPalette(pal)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: syntropia-apps-dialog.py <apps.list>", file=sys.stderr)
        return 2
    entries = load_catalog(sys.argv[1])
    if not entries:
        print("empty catalog", file=sys.stderr)
        return 2

    app = QApplication(sys.argv)
    apply_win98_theme(app)
    dlg = AppsDialog(entries)
    if dlg.exec() == QDialog.Accepted:
        for pkg in dlg.selection():
            print(pkg)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
