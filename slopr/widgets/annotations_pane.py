"""Annotations pane — searchable, filterable view of all annotation events.

Layout::

    ┌─ AnnotationsPane ────────────────────────────────────────────────────────┐
    │ Filter bar (height: 3): [Phase ▾] [Turn ─] [Search ________________]    │
    ├──────────────────────────────────────────────────────────────────────────│
    │ DataTable (1fr)                                                           │
    │  cols: # | Turn | Phase | Event | Task | Model | In | Out               │
    │  cursor_type="row"; Space = toggle select; Ctrl+A = select all           │
    ├──────────────────────────────────────────────────────────────────────────│
    │ Detail panel (VerticalScroll, height: 12)                                │
    │  metadata + parent event title + annotation body                         │
    ├──────────────────────────────────────────────────────────────────────────│
    │ Button row (height: 3): [Copy]  [Clear Selection]  [N selected]          │
    └──────────────────────────────────────────────────────────────────────────┘

Keyboard shortcuts (within this pane):
  Space     — toggle-select the highlighted row
  Ctrl+A    — select all visible rows
  c         — copy body of selected / highlighted annotation to clipboard
"""

from __future__ import annotations

import subprocess
import sys
from typing import Any

from rich.text import Text

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widget import Widget
from textual.widgets import Button, DataTable, Input, Select, Static

from slopr.models import EventType, GameEvent
from slopr.store import EventStore

# ── Colors ────────────────────────────────────────────────────────────────────

_C_NUM    = "#aaaaaa"
_C_TURN   = "#daa520"
_C_PHASE  = "#7986cb"
_C_EVENT  = "#90a4ae"
_C_TASK   = "#4caf50"
_C_MODEL  = "#7986cb"
_C_TOK    = "#aaaaaa"
_C_HEADER = "#546e7a"
_C_SEL    = "#ffa726"


def _t(value: str, color: str) -> Text:
    return Text(value, style=color)


# ── Clipboard helper ──────────────────────────────────────────────────────────


def _copy_to_clipboard(text: str) -> bool:
    """Copy *text* to the system clipboard.  Returns True on success."""
    try:
        if sys.platform == "darwin":
            subprocess.run(["pbcopy"], input=text.encode(), check=True)
        elif sys.platform.startswith("linux"):
            # Try xclip first, then xsel
            try:
                subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=text.encode(),
                    check=True,
                )
            except FileNotFoundError:
                subprocess.run(
                    ["xsel", "--clipboard", "--input"],
                    input=text.encode(),
                    check=True,
                )
        elif sys.platform == "win32":
            subprocess.run(["clip"], input=text.encode("utf-16"), check=True)
        else:
            return False
        return True
    except Exception:
        return False


# ── AnnotationsPane ───────────────────────────────────────────────────────────


class AnnotationsPane(Widget):
    """Content-area pane for viewing and managing all annotations in the active store."""

    BINDINGS = [
        Binding("space",  "toggle_select",  "Toggle Select", show=False),
        Binding("ctrl+a", "select_all",     "Select All",    show=False),
        Binding("c",      "copy_selected",  "Copy",          show=False),
    ]

    DEFAULT_CSS = """
    AnnotationsPane {
        height: 1fr;
        width: 3fr;
        layout: vertical;
    }
    #ann-filter-bar {
        height: 3;
        layout: horizontal;
        align: left middle;
        border-bottom: solid $surface-lighten-2;
        padding: 0 1;
    }
    #ann-phase-select {
        width: 18;
        margin-right: 1;
    }
    #ann-turn-input {
        width: 9;
        margin-right: 1;
    }
    #ann-search-input {
        width: 1fr;
        margin-right: 1;
    }
    #ann-clear-btn {
        width: 8;
        min-width: 8;
        height: 1;
    }
    #ann-table {
        height: 1fr;
    }
    #ann-detail-scroll {
        height: 12;
        border-top: solid $surface-lighten-2;
        padding: 0 1;
    }
    #ann-detail-content {
        color: $text;
    }
    #ann-btn-row {
        height: 3;
        align: left middle;
        border-top: solid $surface-lighten-2;
        padding: 0 1;
    }
    #ann-btn-row Button {
        margin-right: 1;
        height: 1;
    }
    #ann-sel-count {
        color: $text-muted;
        margin-left: 1;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._store: EventStore | None = None
        # All annotation events loaded from store
        self._all_anns: list[GameEvent] = []
        # Visible rows after filtering: list of (display_num, annotation)
        self._visible: list[tuple[int, GameEvent]] = []
        # Set of selected annotation IDs
        self._selected_ids: set[str] = set()
        # Mapping ann.id → display_num
        self._ann_num: dict[str, int] = {}
        self._highlighted_id: str | None = None

    # ── Public API ────────────────────────────────────────────────────────

    def set_store(self, store: EventStore) -> None:
        """Attach or replace the EventStore; does not reload automatically."""
        self._store = store

    def refresh_annotations(self) -> None:
        """Reload annotations from the store and re-apply filters."""
        self._load_annotations()
        self._rebuild_phase_select()
        self._apply_filters()

    # ── Compose ───────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        with Horizontal(id="ann-filter-bar"):
            yield Select(
                [("(all phases)", "")],
                value="",
                id="ann-phase-select",
                allow_blank=False,
            )
            yield Input(placeholder="turn", id="ann-turn-input")
            yield Input(placeholder="search body…", id="ann-search-input")
            yield Button("Clear", id="ann-clear-btn", variant="default")

        tbl: DataTable[str] = DataTable(id="ann-table", cursor_type="row")
        tbl.add_columns(
            _t("#",     _C_NUM),
            _t("Turn",  _C_TURN),
            _t("Phase", _C_PHASE),
            _t("Event", _C_EVENT),
            _t("Task",  _C_TASK),
            _t("Model", _C_MODEL),
            _t("In",    _C_TOK),
            _t("Out",   _C_TOK),
        )
        yield tbl

        with VerticalScroll(id="ann-detail-scroll"):
            yield Static("Select an annotation to view details.", id="ann-detail-content")

        with Horizontal(id="ann-btn-row"):
            yield Button("Copy",            id="ann-btn-copy",  variant="default")
            yield Button("Clear Selection", id="ann-btn-clear-sel", variant="default")
            yield Static("", id="ann-sel-count")

    # ── Internal: data loading ────────────────────────────────────────────

    def _load_annotations(self) -> None:
        """Fetch all ANNOTATION events from the store."""
        if self._store is None:
            self._all_anns = []
            return
        self._all_anns = self._store.get_events(
            event_type=EventType.ANNOTATION, limit=5000
        )
        # Assign stable display numbers
        self._ann_num = {ann.id: i + 1 for i, ann in enumerate(self._all_anns)}

    def _rebuild_phase_select(self) -> None:
        """Repopulate the phase Select widget with unique phases from loaded annotations."""
        phases = sorted({a.phase for a in self._all_anns if a.phase})
        options: list[tuple[str, str]] = [("(all phases)", "")]
        options += [(p, p) for p in phases]
        sel = self.query_one("#ann-phase-select", Select)
        try:
            sel.set_options(options)
        except Exception:
            pass

    def _apply_filters(self) -> None:
        """Filter _all_anns by current filter bar values and rebuild the table."""
        # Read filter values
        try:
            phase_val = str(self.query_one("#ann-phase-select", Select).value or "")
        except Exception:
            phase_val = ""
        try:
            turn_raw = self.query_one("#ann-turn-input", Input).value.strip()
            turn_filter: int | None = int(turn_raw) if turn_raw else None
        except (ValueError, Exception):
            turn_filter = None
        try:
            search = self.query_one("#ann-search-input", Input).value.strip().lower()
        except Exception:
            search = ""

        filtered = self._all_anns
        if phase_val:
            filtered = [a for a in filtered if a.phase == phase_val]
        if turn_filter is not None:
            filtered = [a for a in filtered if a.turn_number == turn_filter]
        if search:
            filtered = [a for a in filtered if search in (a.body or "").lower()]

        self._visible = [(self._ann_num.get(a.id, 0), a) for a in filtered]
        self._rebuild_table()

    def _rebuild_table(self) -> None:
        """Clear and repopulate the DataTable from _visible."""
        tbl = self.query_one("#ann-table", DataTable)
        tbl.clear()

        for num, ann in self._visible:
            sd = ann.structured_data or {}
            task_label = sd.get("task_label", "")[:20]
            model      = sd.get("model", "")[:16]
            in_tok     = str(sd.get("input_tokens", "—") or "—")
            out_tok    = str(sd.get("output_tokens", "—") or "—")

            # Find parent event title
            parent_title = ""
            parent_id = ann.parent_id or sd.get("parent_event_id", "")
            if parent_id and self._store is not None:
                p = self._store.get_event(parent_id)
                if p is not None:
                    parent_title = (p.title or "")[:30]

            is_sel = ann.id in self._selected_ids
            num_cell = _t("✓" if is_sel else str(num), _C_SEL if is_sel else _C_NUM)

            tbl.add_row(
                num_cell,
                _t(str(ann.turn_number), _C_TURN),
                _t(ann.phase or "—",   _C_PHASE),
                _t(parent_title,        _C_EVENT),
                _t(task_label,          _C_TASK),
                _t(model,               _C_MODEL),
                _t(in_tok,              _C_TOK),
                _t(out_tok,             _C_TOK),
                key=ann.id,
            )

        self._update_sel_count()

    # ── Internal: detail panel ────────────────────────────────────────────

    def _show_detail(self, ann: GameEvent) -> None:
        """Populate the detail panel for *ann*."""
        self._highlighted_id = ann.id
        sd = ann.structured_data or {}
        task_label = sd.get("task_label", "")
        model      = sd.get("model", "")
        in_tok     = sd.get("input_tokens", "—") or "—"
        out_tok    = sd.get("output_tokens", "—") or "—"
        elapsed    = sd.get("elapsed_s", "")

        # Metadata line
        meta_parts = []
        if ann.turn_number is not None:
            meta_parts.append(f"[dim]Turn:[/] {ann.turn_number}")
        if ann.phase:
            meta_parts.append(f"[dim]Phase:[/] {ann.phase}")
        if task_label:
            meta_parts.append(f"[dim]Task:[/] {task_label}")
        meta_line = "   ".join(meta_parts)

        model_line = ""
        if model:
            el = f"  [dim]Elapsed:[/] {elapsed}s" if elapsed else ""
            model_line = (
                f"[dim]Model:[/] {model}{el}\n"
                f"[dim]In:[/] {in_tok}  [dim]Out:[/] {out_tok}"
            )

        # Parent event title
        parent_title = ""
        parent_id = ann.parent_id or sd.get("parent_event_id", "")
        if parent_id and self._store is not None:
            p = self._store.get_event(parent_id)
            if p is not None:
                parent_title = p.title or ""

        body = ann.body or "(no body)"

        sep = "─" * 50
        sections = [meta_line]
        if model_line:
            sections.append(model_line)
        if parent_title:
            sections.append(
                f"\n[bold {_C_HEADER}]─ Parent Event {sep[:36]}[/]\n{parent_title}"
            )
        sections.append(
            f"\n[bold {_C_HEADER}]─ Annotation {sep[:38]}[/]\n{body}"
        )

        text = "\n".join(sections)
        self.query_one("#ann-detail-content", Static).update(text)

    # ── Internal: selection ───────────────────────────────────────────────

    def _toggle_select(self, ann_id: str) -> None:
        if ann_id in self._selected_ids:
            self._selected_ids.discard(ann_id)
        else:
            self._selected_ids.add(ann_id)
        # Update the # cell for this row
        tbl = self.query_one("#ann-table", DataTable)
        num = next(
            (n for n, a in self._visible if a.id == ann_id), None
        )
        if num is not None:
            is_sel = ann_id in self._selected_ids
            cell_val = _t("✓" if is_sel else str(num), _C_SEL if is_sel else _C_NUM)
            try:
                tbl.update_cell(ann_id, "#", cell_val, update_width=False)
            except Exception:
                pass
        self._update_sel_count()

    def _update_sel_count(self) -> None:
        n = len(self._selected_ids)
        text = f"{n} selected" if n else ""
        try:
            self.query_one("#ann-sel-count", Static).update(text)
        except Exception:
            pass

    def _get_highlighted_ann(self) -> GameEvent | None:
        """Return the annotation for the currently highlighted row, if any."""
        if not self._visible:
            return None
        tbl = self.query_one("#ann-table", DataTable)
        if 0 <= tbl.cursor_row < len(self._visible):
            return self._visible[tbl.cursor_row][1]
        return None

    def _copy_text(self, text: str) -> None:
        ok = _copy_to_clipboard(text)
        if ok:
            self.app.notify("Copied to clipboard.", timeout=2)
        else:
            self.app.notify("Clipboard not available on this platform.", severity="warning", timeout=3)

    # ── Actions ───────────────────────────────────────────────────────────

    def action_toggle_select(self) -> None:
        ann = self._get_highlighted_ann()
        if ann is not None:
            self._toggle_select(ann.id)

    def action_select_all(self) -> None:
        for _, ann in self._visible:
            self._selected_ids.add(ann.id)
        self._rebuild_table()

    def action_copy_selected(self) -> None:
        if self._selected_ids:
            bodies = [
                ann.body or ""
                for _, ann in self._visible
                if ann.id in self._selected_ids
            ]
            self._copy_text("\n\n---\n\n".join(bodies))
        else:
            ann = self._get_highlighted_ann()
            if ann:
                self._copy_text(ann.body or "")

    # ── Event handlers ────────────────────────────────────────────────────

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id != "ann-table":
            return
        if event.row_key is None:
            return
        ann_id = str(event.row_key.value)
        ann = next((a for _, a in self._visible if a.id == ann_id), None)
        if ann is not None:
            self._show_detail(ann)

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "ann-phase-select":
            self._apply_filters()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id in ("ann-turn-input", "ann-search-input"):
            self._apply_filters()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "ann-btn-copy":
            self.action_copy_selected()
        elif event.button.id == "ann-btn-clear-sel":
            self._selected_ids.clear()
            self._rebuild_table()
        elif event.button.id == "ann-clear-btn":
            self._clear_filters()

    def _clear_filters(self) -> None:
        try:
            self.query_one("#ann-turn-input", Input).value = ""
            self.query_one("#ann-search-input", Input).value = ""
            sel = self.query_one("#ann-phase-select", Select)
            sel.value = ""
        except Exception:
            pass
        self._apply_filters()
