"""Branch pane — full content-area replacement for branch exploration.

Layout::

    ┌─ BranchPane ───────────────────────────────────────────────────────────┐
    │ BranchManager (2fr)       │  BranchDetail (3fr, VerticalScroll)        │
    │  tree + spawn/delete btns │   label, fork turn, annotation, edited     │
    │                           │   event diff (title / body before→after)   │
    │                           ├────────────────────────────────────────────│
    │                           │  KPI Compare DataTable (height: 8)         │
    │                           │   cols: Branch, T, Territory, A Conv, ...  │
    └───────────────────────────┴────────────────────────────────────────────┘

``app.query_one(BranchManager)`` continues to work — Textual's recursive query
traverses through BranchPane to find the nested widget.

:class:`BranchActivated`, :class:`BranchSimRequested`, and :class:`BranchDeleted`
bubble up through BranchPane to WargameApp unchanged.
"""

from __future__ import annotations

import difflib

from rich.text import Text

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.widget import Widget
from textual.widgets import DataTable, Static

from slopr.branches import BranchEntry, BranchStore
from slopr.models import EventType
from slopr.widgets.branch_manager import BranchActivated, BranchManager


# ── Column colours (match kpi_panel.py palette) ─────────────────────────────

_C_BRANCH = "#aaaaaa"
_C_NEUT   = "#daa520"
_C_A      = "#5b9cf5"
_C_B      = "#f55b5b"


def _t(value: str, color: str) -> Text:
    return Text(value, style=color)


class BranchPane(Widget):
    """Full-width content-area pane for branch exploration.

    Contains the existing :class:`~slopr.widgets.branch_manager.BranchManager`
    on the left plus a detail panel and KPI compare table on the right.
    """

    DEFAULT_CSS = """
    BranchPane {
        layout: horizontal;
        height: 1fr;
        width: 3fr;
    }
    BranchPane BranchManager {
        display: block;
        height: 1fr;
        width: 2fr;
        border-top: none;
        border-right: solid $surface-lighten-2;
    }
    #branch-right-col {
        width: 3fr;
        height: 1fr;
        layout: vertical;
    }
    #branch-detail {
        height: 1fr;
        background: $background;
        scrollbar-size: 1 1;
        padding: 0 1;
    }
    #branch-compare {
        height: 8;
        background: $surface;
        border-top: solid $surface-lighten-2;
    }
    .branch-detail-header {
        color: $text-muted;
        text-style: bold;
        height: 1;
    }
    .branch-detail-value {
        color: $text;
        margin: 0 0 0 1;
    }
    .branch-detail-section {
        color: $text-disabled;
        text-style: italic;
        height: 1;
        margin-top: 1;
    }
    .branch-detail-diff-old {
        color: $error;
        margin: 0 0 0 1;
    }
    .branch-detail-diff-new {
        color: $success;
        margin: 0 0 0 1;
    }
    """

    def __init__(
        self, id: str | None = None, classes: str | None = None
    ) -> None:
        super().__init__(id=id, classes=classes)
        self._store: BranchStore | None = None
        self._selected_branch_id: str | None = None

    def compose(self) -> ComposeResult:
        yield BranchManager(id="branch-manager")
        with Vertical(id="branch-right-col"):
            yield VerticalScroll(
                Static("Select a branch to view details.", id="branch-detail-content"),
                id="branch-detail",
            )
            yield DataTable(id="branch-compare", zebra_stripes=True)

    def on_mount(self) -> None:
        table = self.query_one("#branch-compare", DataTable)
        table.cursor_type = "row"
        table.add_columns(
            _t("Branch",    _C_BRANCH),
            _t("Fork T",    _C_NEUT),
            _t("Status",    _C_BRANCH),
            _t("Territory", _C_NEUT),
            _t("A Conv",    _C_A),
            _t("B Conv",    _C_B),
            _t("A Act",     _C_A),
            _t("B Act",     _C_B),
        )

    def set_store(self, branch_store: BranchStore) -> None:
        """Attach a :class:`BranchStore` and refresh."""
        self._store = branch_store
        bm = self.query_one(BranchManager)
        bm.set_store(branch_store)
        self._refresh_compare()

    def refresh_pane(self, branch_store: BranchStore | None = None) -> None:
        """Re-render tree and compare table from current (or given) store."""
        if branch_store is not None:
            self._store = branch_store
        if self._store is None:
            return
        bm = self.query_one(BranchManager)
        bm.refresh_branches(self._store)
        self._refresh_compare()

    def on_branch_activated(self, message: BranchActivated) -> None:
        """When a branch is selected in the tree, refresh the detail panel."""
        self._selected_branch_id = message.branch_id
        self._show_detail(message.branch_id)
        # Let the message bubble up to WargameApp unchanged.

    def _show_detail(self, branch_id: str | None) -> None:
        """Render branch metadata + edited-event diff in the detail scroll."""
        container = self.query_one("#branch-detail", VerticalScroll)
        container.remove_children()

        if self._store is None:
            container.mount(Static("No branch store loaded."))
            return

        if branch_id is None:
            # Root — show manifest summary
            manifest = self._store.manifest
            root_store = self._store.get_store(None)
            container.mount(
                Static("Root stream", classes="branch-detail-header"),
                Static(f"{manifest.root_file}  ·  {root_store.event_count()} events",
                       classes="branch-detail-value"),
                Static(f"{len(manifest.branches)} branch(es) total",
                       classes="branch-detail-value"),
            )
            return

        try:
            entry: BranchEntry = self._store.get_entry(branch_id)
        except KeyError:
            container.mount(Static("Branch not found."))
            return

        branch_store = self._store.get_store(branch_id)
        widgets: list[Widget] = [
            Static(entry.label, classes="branch-detail-header"),
            Static(
                f"Fork turn: {entry.fork_turn}  ·  seq: {entry.fork_sequence}",
                classes="branch-detail-value",
            ),
            Static(
                f"Status: {entry.sim_status.value}  ·  "
                f"{branch_store.event_count()} events",
                classes="branch-detail-value",
            ),
        ]

        if entry.annotation:
            widgets += [
                Static("Tag", classes="branch-detail-section"),
                Static(entry.annotation, classes="branch-detail-value"),
            ]

        if entry.edited_event:
            ed = entry.edited_event
            old_title = ed.get("original_title", "")
            old_body  = ed.get("original_body",  "")
            new_title = ed.get("title", "")
            new_body  = ed.get("body",  "")

            widgets.append(Static("Edited event", classes="branch-detail-section"))

            if old_title or new_title:
                widgets.append(Static("Title", classes="branch-detail-header"))
                if old_title and old_title != new_title:
                    widgets.append(Static(f"− {old_title}", classes="branch-detail-diff-old"))
                widgets.append(Static(f"+ {new_title}", classes="branch-detail-diff-new"))

            if old_body or new_body:
                widgets.append(Static("Body", classes="branch-detail-header"))
                if old_body and old_body != new_body:
                    diff_lines = list(difflib.unified_diff(
                        (old_body or "").splitlines(keepends=True),
                        (new_body or "").splitlines(keepends=True),
                        fromfile="original",
                        tofile="edited",
                        lineterm="",
                    ))
                    if diff_lines:
                        for line in diff_lines:
                            if line.startswith("+") and not line.startswith("+++"):
                                widgets.append(Static(line, classes="branch-detail-diff-new"))
                            elif line.startswith("-") and not line.startswith("---"):
                                widgets.append(Static(line, classes="branch-detail-diff-old"))
                            elif line.startswith("@@"):
                                widgets.append(Static(line, classes="branch-detail-section"))
                            # skip header lines (--- / +++)
                    else:
                        widgets.append(Static(new_body or "(empty)", classes="branch-detail-value"))
                else:
                    new_excerpt = new_body[:600] + ("…" if len(new_body) > 600 else "")
                    widgets.append(Static(new_excerpt or "(empty)", classes="branch-detail-value"))

        container.mount(*widgets)

    def _refresh_compare(self) -> None:
        """Rebuild the KPI compare DataTable from all branches in the store."""
        table = self.query_one("#branch-compare", DataTable)
        table.clear()

        if self._store is None:
            return

        # Root row
        root_store = self._store.get_store(None)
        self._add_compare_row(
            table,
            label=f"[root] {self._store.manifest.root_file}",
            fork_turn=0,
            status="root",
            branch_store=root_store,
        )

        # Branch rows
        for entry in self._store.manifest.branches:
            branch_store = self._store.get_store(entry.id)
            self._add_compare_row(
                table,
                label=entry.label,
                fork_turn=entry.fork_turn,
                status=entry.sim_status.value,
                branch_store=branch_store,
                row_key=entry.id,
            )

    def _add_compare_row(
        self,
        table: DataTable,
        label: str,
        fork_turn: int,
        status: str,
        branch_store,
        row_key: str | None = None,
    ) -> None:
        """Append one row to the compare DataTable using the last KPI event."""
        turns = branch_store.get_turn_numbers()
        kpi: dict = {}
        for t in reversed(turns):
            events = branch_store.get_events(
                turn=t, event_type=EventType.KPI_UPDATE, limit=1
            )
            if events:
                kpi = events[0].structured_data
                break

        tb     = kpi.get("territory_balance", 0)
        a_conv = kpi.get("a_conventional_power", "")
        b_conv = kpi.get("b_conventional_power", "")
        a_act  = kpi.get("a_action_value", "")
        b_act  = kpi.get("b_action_value", "")

        table.add_row(
            _t(label[:30],                                                       _C_BRANCH),
            _t(str(fork_turn),                                                   _C_NEUT),
            _t(status,                                                           _C_BRANCH),
            _t(f"{tb:+.3f}" if isinstance(tb, float) else str(tb),              _C_NEUT),
            _t(f"{a_conv:.1%}" if isinstance(a_conv, float) else str(a_conv),   _C_A),
            _t(f"{b_conv:.1%}" if isinstance(b_conv, float) else str(b_conv),   _C_B),
            _t(str(a_act),                                                       _C_A),
            _t(str(b_act),                                                       _C_B),
            key=row_key,
        )
