"""Syntropia brew GUI — a Textual TUI over the brew inventory + engine.

Shows what's installed and where: Windows apps (Wine prefixes), Windows
VSTs (drop folder + bridge state), native Linux VSTs, and the installable
registry. Uninstall/install actions delegate to the existing CLI commands
(`syntropia uninstall` / `syntropia install`) via subprocess, so the GUI
never re-implements the engine's safety logic.

Run with:  syntropia brews-gui
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import DataTable, Footer, Header, Label, Static, TabbedContent, TabPane

from .inventory import (
    InstalledApp,
    Inventory,
    LinuxPlugin,
    RegistryBrew,
    WindowsPlugin,
    scan_all,
)

# ── Row builders: one consistent row shape per table ------------------------

def _app_rows(apps: list[InstalledApp]) -> list[tuple[str, ...]]:
    rows = []
    for app in apps:
        size = f"{app.size_bytes // (1024 * 1024)} MB" if app.size_bytes else "—"
        rows.append((app.name, size, app.location, "yes" if app.brew else "no"))
    return rows


def _win_rows(plugins: list[WindowsPlugin]) -> list[tuple[str, ...]]:
    return [
        (p.name, "✅ bridged" if p.bridged else "⬜ not bridged", p.location)
        for p in plugins
    ]


def _linux_rows(plugins: list[LinuxPlugin]) -> list[tuple[str, ...]]:
    return [(p.name, p.location) for p in plugins]


def _registry_rows(brews: list[RegistryBrew]) -> list[tuple[str, ...]]:
    return [(b.name, b.category, b.version, b.location) for b in brews]


# ── Tables ------------------------------------------------------------------

class InventoryTable(DataTable):
    """A DataTable that (re)loads rows from a list of tuples.

    ``enter`` is rebound to the app's open-location action: DataTable's own
    enter binding (select_cursor) would otherwise shadow the app binding and
    make Enter a no-op for our purposes.

    Sorting is disabled (``sort=False`` on every column) because header
    clicks drive the app's folder-mode; a sort would reorder rows under our
    positional row map and break open-location.
    """

    # Hidden from the footer (the app-level binding is shown instead); it
    # only exists to route Enter to the app's open action before DataTable's
    # own select-cursor binding can swallow it.
    BINDINGS = [Binding("enter", "open_location", "Open location", show=False)]

    def action_open_location(self) -> None:
        self.app.action_open_selected()

    def on_focus(self) -> None:
        # Focus lands after the initial batch of row-highlight events, so
        # re-sync the footer's open-location visibility now that THIS table
        # is the focused one (row 0 is selected by default).
        self.app._sync_open_visibility()

    def reload(self, columns: list[str], rows: list[tuple[str, ...]]) -> None:
        self.clear()
        for column in columns:
            self.add_column(column)
        for row in rows:
            self.add_row(*row)


class DetailPane(Static):
    """Footer detail for the selected row."""


# ── The app -----------------------------------------------------------------

class BrewsApp(App):
    """Textual TUI: inventory + management for Syntropia brews."""

    CSS = """
    #detail {
        height: auto;
        padding: 0 1;
        background: #150b28;
        color: #c9b8e8;
        border-top: solid #3a2a5a;
    }
    TabbedContent {
        height: 1fr;
    }
    DataTable {
        height: 1fr;
    }
    """

    TITLE = "😈 Syntropia Brews"
    SUB_TITLE = "Windows DAWs & VSTs — inventory and management"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("u", "uninstall_selected", "Uninstall"),
        # "Open location" is only meaningful when a row is selected; its
        # visibility is toggled by _sync_open_visibility() so the footer
        # doesn't advertise a dead key on an empty table.
        Binding("enter", "open_selected", "Open location", show=False),
    ]

    def __init__(self, inventory: Inventory | None = None) -> None:
        super().__init__()
        self._inventory = inventory or scan_all(with_sizes=True)
        self._tables: dict[str, InventoryTable] = {}
        self._row_map: dict[str, dict[str, object]] = {}

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent():
            with TabPane("Windows Apps", id="tab-apps"):
                yield InventoryTable(id="tbl-apps", cursor_type="row")
            with TabPane("Windows VSTs", id="tab-winvst"):
                yield InventoryTable(id="tbl-winvst", cursor_type="row")
            with TabPane("Linux VSTs", id="tab-linuxvst"):
                yield InventoryTable(id="tbl-linuxvst", cursor_type="row")
            with TabPane("Registry", id="tab-registry"):
                yield InventoryTable(id="tbl-registry", cursor_type="row")
        yield DetailPane("", id="detail")
        yield Footer()

    def on_mount(self) -> None:
        self._load_all()
        # Start with the first table focused so up/down arrows work
        # immediately instead of landing on the tab bar.
        if self._tables:
            first = next(iter(self._tables.values()))
            first.focus()
        self._sync_open_visibility()

    # -- Loading -------------------------------------------------------------

    def _load_all(self) -> None:
        inv = self._inventory
        tables = {
            "tbl-apps": ("App", "Size", "Location", "Manifest"),
            "tbl-winvst": ("Plugin", "Bridge", "Location"),
            "tbl-linuxvst": ("Plugin", "Location"),
            "tbl-registry": ("Name", "Category", "Version", "Location"),
        }
        self._row_map.clear()
        for table_id, columns in tables.items():
            table = self.query_one(f"#{table_id}", InventoryTable)
            table.reload(columns, [])
            self._tables[table_id] = table

        for i, row in enumerate(_app_rows(inv.installed_apps)):
            self._tables["tbl-apps"].add_row(*row)
            self._row_map[f"tbl-apps:{i}"] = {"app": inv.installed_apps[i]}
        # Folder rows: open the whole plugin directory, not just one plugin.
        # They sit at index 0; the real plugins start at index 1.
        win_folder = Path.home() / "VST3"
        self._tables["tbl-winvst"].add_row("📁 Windows VST3 folder", "", str(win_folder))
        self._row_map["tbl-winvst:0"] = {"folder": win_folder}
        for i, row in enumerate(_win_rows(inv.windows_plugins)):
            self._tables["tbl-winvst"].add_row(*row)
            self._row_map[f"tbl-winvst:{i + 1}"] = {"plugin": inv.windows_plugins[i]}

        linux_folder = Path.home() / ".vst3"
        self._tables["tbl-linuxvst"].add_row("📁 Linux VST3 folder", str(linux_folder))
        self._row_map["tbl-linuxvst:0"] = {"folder": linux_folder}
        for i, row in enumerate(_linux_rows(inv.linux_plugins)):
            self._tables["tbl-linuxvst"].add_row(*row)
            self._row_map[f"tbl-linuxvst:{i + 1}"] = {"plugin": inv.linux_plugins[i]}
        for i, row in enumerate(_registry_rows(inv.registry_brews)):
            self._tables["tbl-registry"].add_row(*row)
            self._row_map[f"tbl-registry:{i}"] = {"brew": inv.registry_brews[i]}

    # -- Selection detail ----------------------------------------------------

    def _current(self) -> tuple[str, int, dict[str, object]]:
        """Return (table_id, row_index, row_payload) for the focused table."""
        for table_id, table in self._tables.items():
            if table.has_focus or self.focused is table:
                idx = table.cursor_coordinate.row
                return table_id, idx, self._row_map.get(f"{table_id}:{idx}", {})
        return "", 0, {}

    def _update_detail(self) -> None:
        table_id, idx, payload = self._current()
        detail = self.query_one("#detail", DetailPane)
        if table_id == "tbl-apps":
            app: InstalledApp = payload.get("app")
            if app:
                brew_note = f"manifest: {app.brew.name}" if app.brew else "no manifest in registry"
                detail.update(f"▶ {app.name} — {brew_note}\n   {app.location}")
        elif table_id in ("tbl-winvst", "tbl-linuxvst"):
            folder = payload.get("folder")
            if folder:
                detail.update(f"▶ {folder}\n   [enter] to open this folder")
                return
            plugin = payload.get("plugin")
            if plugin:
                state = "bridged" if getattr(plugin, "bridged", False) else "not bridged"
                detail.update(f"▶ {plugin.name} — {state}\n   {plugin.location}")
        elif table_id == "tbl-registry":
            brew: RegistryBrew = payload.get("brew")
            if brew:
                detail.update(
                    f"▶ {brew.name} {brew.version} ({brew.category})\n   {brew.location}\n"
                    f"   [u] to install"
                )
        else:
            detail.update("")

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._update_detail()
        self._sync_open_visibility()

    # -- Open-location footer visibility -------------------------------------

    def _sync_open_visibility(self) -> None:
        """Show the footer's Open-location key only when a row is selected.

        Binding is a frozen dataclass, so the list is rebuilt with a new
        Binding rather than mutated; refresh_bindings() then re-renders the
        footer. The key itself stays functional either way — this only
        changes what the footer advertises.
        """
        import dataclasses

        _, _, payload = self._current()
        has_selection = bool(payload)
        new_bindings = []
        for binding in self.BINDINGS:
            if binding.action == "open_selected":
                binding = dataclasses.replace(binding, show=has_selection)
            new_bindings.append(binding)
        self.BINDINGS = new_bindings
        self.refresh_bindings()

    # -- Actions -------------------------------------------------------------

    def action_refresh(self) -> None:
        self._inventory = scan_all(with_sizes=True)
        self._load_all()
        self.notify("Inventory refreshed")

    def action_open_selected(self) -> None:
        """Open the selected item's location with the default file manager."""
        _, _, payload = self._current()
        target: Path | None = None
        for obj in payload.values():
            if isinstance(obj, Path):
                target = obj
                break
            target = getattr(obj, "path", None) or getattr(obj, "prefix_path", None)
            if target is not None:
                break
        if target is None or not Path(target).exists():
            self.notify("Nothing to open", severity="warning")
            return
        subprocess.Popen(["xdg-open", str(target)])
        self.notify(f"Opened {target}")
        self._sync_open_visibility()

    def action_uninstall_selected(self) -> None:
        """Uninstall the selected installed app (delegates to the CLI)."""
        _, _, payload = self._current()
        app: InstalledApp | None = payload.get("app")
        if app is None:
            self.notify("Select an installed app to uninstall", severity="warning")
            return
        self._confirm_uninstall(app)

    def _cli(self) -> list[str]:
        """Locate the syntropia CLI (falls back to the module invocation)."""
        found = shutil.which("syntropia")
        if found:
            return [found]
        return [sys.executable, "-m", "syntropia.cli"]

    def _confirm_uninstall(self, app: InstalledApp) -> None:
        """Two-step confirm: the engine's uninstall is destructive."""
        self.notify(f"Uninstalling {app.name}… (full prefix removal)", severity="warning")
        try:
            proc = subprocess.run(
                self._cli() + ["uninstall", app.name, "--yes"],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            self.notify("Uninstall timed out", severity="error")
            return
        if proc.returncode == 0:
            self.notify(f"✅ {app.name} uninstalled", severity="information")
        else:
            self.notify(
                f"Uninstall failed: {proc.stderr.strip()[-200:]}",
                severity="error",
            )
        self.action_refresh()


def run() -> None:
    """Entry point for the GUI command."""
    BrewsApp().run()


if __name__ == "__main__":
    run()
