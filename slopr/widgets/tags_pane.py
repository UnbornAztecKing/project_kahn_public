"""Tags pane — searchable, filterable view of all tag events.

Layout::

    ┌─ TagsPane ────────────────────────────────────────────────────────────────┐
    │ Filter bar (height: 3): [Phase ▾] [Search ___________________________]    │
    ├───────────────────────────────────────────────────────────────────────────│
    │ DataTable (1fr)                                                            │
    │  cols: # | Turn | Phase | Event | Task | Model | In | Out                │
    │  cursor_type="row"; Space = toggle select; Ctrl+A = select all            │
    ├───────────────────────────────────────────────────────────────────────────│
    │ Detail panel (VerticalScroll, 2fr — minimum ~2/3 of available height)     │
    │  metadata + parent event title + tag body                                 │
    ├───────────────────────────────────────────────────────────────────────────│
    │ Button row (height: 3): [Copy]  [Clear Selection]  [N selected]           │
    └───────────────────────────────────────────────────────────────────────────┘

Keyboard shortcuts (within this pane):
  Space     — toggle-select the highlighted row
  Ctrl+A    — select all visible rows
  c         — copy body of selected / highlighted tag to clipboard
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


# ── TagsPane ──────────────────────────────────────────────────────────────────


class TagsPane(Widget):
    """Content-area pane for viewing and managing all tags in the active store."""

    BINDINGS = [
        Binding("space",  "toggle_select",  "Toggle Select", show=False),
        Binding("ctrl+a", "select_all",     "Select All",    show=False),
        Binding("c",      "copy_selected",  "Copy",          show=False),
    ]

    DEFAULT_CSS = """
    TagsPane {
        height: 1fr;
        width: 3fr;
        layout: vertical;
    }
    #tag-filter-bar {
        height: 3;
        layout: horizontal;
        align: left middle;
        border-bottom: solid $surface-lighten-2;
        padding: 0 1;
    }
    #tag-phase-select {
        width: 18;
        margin-right: 1;
    }
    #tag-search-input {
        width: 1fr;
        margin-right: 1;
    }
    #tag-clear-btn {
        width: 8;
        min-width: 8;
        height: 1;
    }
    #tag-table {
        height: 1fr;
    }
    #tag-detail-scroll {
        height: 2fr;
        border-top: solid $surface-lighten-2;
        padding: 0 1;
    }
    #tag-detail-content {
        color: $text;
    }
    #tag-btn-row {
        height: 3;
        align: left middle;
        border-top: solid $surface-lighten-2;
        padding: 0 1;
    }
    #tag-btn-row Button {
        margin-right: 1;
        height: 1;
    }
    #tag-sel-count {
        color: $text-muted;
        margin-left: 1;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._store: EventStore | None = None
        # All tag events loaded from store
        self._all_tags: list[GameEvent] = []
        # Visible rows after filtering: list of (display_num, tag)
        self._visible: list[tuple[int, GameEvent]] = []
        # Set of selected tag IDs
        self._selected_ids: set[str] = set()
        # Mapping tag.id → display_num
        self._tag_num: dict[str, int] = {}
        self._highlighted_id: str | None = None

    # ── Public API ────────────────────────────────────────────────────────

    def set_store(self, store: EventStore) -> None:
        """Attach or replace the EventStore; does not reload automatically."""
        self._store = store

    def refresh_tags(self) -> None:
        """Reload tags from the store and re-apply filters."""
        self._load_tags()
        self._rebuild_phase_select()
        self._apply_filters()

    # ── Compose ───────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        with Horizontal(id="tag-filter-bar"):
            yield Select(
                [("(all phases)", "")],
                value="",
                id="tag-phase-select",
                allow_blank=False,
            )
            yield Input(placeholder="search body…", id="tag-search-input")
            yield Button("Clear", id="tag-clear-btn", variant="default")

        tbl: DataTable[str] = DataTable(id="tag-table", cursor_type="row")
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

        with VerticalScroll(id="tag-detail-scroll"):
            yield Static("Select a tag to view details.", id="tag-detail-content")

        with Horizontal(id="tag-btn-row"):
            yield Button("Copy",            id="tag-btn-copy",      variant="default")
            yield Button("Clear Selection", id="tag-btn-clear-sel", variant="default")
            yield Static("", id="tag-sel-count")

    # ── Internal: data loading ────────────────────────────────────────────

    def _load_tags(self) -> None:
        """Fetch all TAG and legacy ANNOTATION events from the store."""
        if self._store is None:
            self._all_tags = []
            return
        # Fetch both new TAG and legacy ANNOTATION events
        tags = self._store.get_events(event_type=EventType.TAG, limit=5000)
        legacy = self._store.get_events(event_type=EventType.ANNOTATION, limit=5000)
        # Merge, sort by sequence number
        combined = sorted(tags + legacy, key=lambda e: e.sequence_number)
        self._all_tags = combined
        # Assign stable display numbers
        self._tag_num = {tag.id: i + 1 for i, tag in enumerate(self._all_tags)}

    def _rebuild_phase_select(self) -> None:
        """Repopulate the phase Select widget with unique phases from loaded tags."""
        phases = sorted({a.phase for a in self._all_tags if a.phase})
        options: list[tuple[str, str]] = [("(all phases)", "")]
        options += [(p, p) for p in phases]
        sel = self.query_one("#tag-phase-select", Select)
        try:
            sel.set_options(options)
        except Exception:
            pass

    def _apply_filters(self) -> None:
        """Filter _all_tags by current filter bar values and rebuild the table."""
        try:
            phase_val = str(self.query_one("#tag-phase-select", Select).value or "")
        except Exception:
            phase_val = ""
        try:
            search = self.query_one("#tag-search-input", Input).value.strip().lower()
        except Exception:
            search = ""

        filtered = self._all_tags
        if phase_val:
            filtered = [a for a in filtered if a.phase == phase_val]
        if search:
            filtered = [a for a in filtered if search in (a.body or "").lower()]

        self._visible = [(self._tag_num.get(a.id, 0), a) for a in filtered]
        self._rebuild_table()

    def _rebuild_table(self) -> None:
        """Clear and repopulate the DataTable from _visible."""
        tbl = self.query_one("#tag-table", DataTable)
        tbl.clear()

        for num, tag in self._visible:
            sd = tag.structured_data or {}
            task_label = sd.get("task_label", "")[:20]
            model      = sd.get("model", "")[:16]
            in_tok     = str(sd.get("input_tokens", "—") or "—")
            out_tok    = str(sd.get("output_tokens", "—") or "—")

            # Find parent event title
            parent_title = ""
            parent_id = tag.parent_id or sd.get("parent_event_id", "")
            if parent_id and self._store is not None:
                p = self._store.get_event(parent_id)
                if p is not None:
                    parent_title = (p.title or "")[:30]

            is_sel = tag.id in self._selected_ids
            num_cell = _t("✓" if is_sel else str(num), _C_SEL if is_sel else _C_NUM)

            tbl.add_row(
                num_cell,
                _t(str(tag.turn_number), _C_TURN),
                _t(tag.phase or "—",   _C_PHASE),
                _t(parent_title,        _C_EVENT),
                _t(task_label,          _C_TASK),
                _t(model,               _C_MODEL),
                _t(in_tok,              _C_TOK),
                _t(out_tok,             _C_TOK),
                key=tag.id,
            )

        self._update_sel_count()

    # ── Internal: detail panel ────────────────────────────────────────────

    def _show_detail(self, tag: GameEvent) -> None:
        """Populate the detail panel for *tag*."""
        self._highlighted_id = tag.id
        sd = tag.structured_data or {}
        task_label = sd.get("task_label", "")
        model      = sd.get("model", "")
        in_tok     = sd.get("input_tokens", "—") or "—"
        out_tok    = sd.get("output_tokens", "—") or "—"
        elapsed    = sd.get("elapsed_s", "")

        meta_parts = []
        if tag.turn_number is not None:
            meta_parts.append(f"[dim]Turn:[/] {tag.turn_number}")
        if tag.phase:
            meta_parts.append(f"[dim]Phase:[/] {tag.phase}")
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

        parent_title = ""
        parent_id = tag.parent_id or sd.get("parent_event_id", "")
        if parent_id and self._store is not None:
            p = self._store.get_event(parent_id)
            if p is not None:
                parent_title = p.title or ""

        body = tag.body or "(no body)"

        sep = "─" * 50
        sections = [meta_line]
        if model_line:
            sections.append(model_line)
        if parent_title:
            sections.append(
                f"\n[bold {_C_HEADER}]─ Parent Event {sep[:36]}[/]\n{parent_title}"
            )
        sections.append(
            f"\n[bold {_C_HEADER}]─ Tag {sep[:44]}[/]\n{body}"
        )

        text = "\n".join(sections)
        self.query_one("#tag-detail-content", Static).update(text)

    # ── Internal: selection ───────────────────────────────────────────────

    def _toggle_select(self, tag_id: str) -> None:
        if tag_id in self._selected_ids:
            self._selected_ids.discard(tag_id)
        else:
            self._selected_ids.add(tag_id)
        tbl = self.query_one("#tag-table", DataTable)
        num = next(
            (n for n, a in self._visible if a.id == tag_id), None
        )
        if num is not None:
            is_sel = tag_id in self._selected_ids
            cell_val = _t("✓" if is_sel else str(num), _C_SEL if is_sel else _C_NUM)
            try:
                tbl.update_cell(tag_id, "#", cell_val, update_width=False)
            except Exception:
                pass
        self._update_sel_count()

    def _update_sel_count(self) -> None:
        n = len(self._selected_ids)
        text = f"{n} selected" if n else ""
        try:
            self.query_one("#tag-sel-count", Static).update(text)
        except Exception:
            pass

    def _get_highlighted_tag(self) -> GameEvent | None:
        """Return the tag for the currently highlighted row, if any."""
        if not self._visible:
            return None
        tbl = self.query_one("#tag-table", DataTable)
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
        tag = self._get_highlighted_tag()
        if tag is not None:
            self._toggle_select(tag.id)

    def action_select_all(self) -> None:
        for _, tag in self._visible:
            self._selected_ids.add(tag.id)
        self._rebuild_table()

    def action_copy_selected(self) -> None:
        if self._selected_ids:
            bodies = [
                tag.body or ""
                for _, tag in self._visible
                if tag.id in self._selected_ids
            ]
            self._copy_text("\n\n---\n\n".join(bodies))
        else:
            tag = self._get_highlighted_tag()
            if tag:
                self._copy_text(tag.body or "")

    # ── Event handlers ────────────────────────────────────────────────────

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id != "tag-table":
            return
        if event.row_key is None:
            return
        tag_id = str(event.row_key.value)
        tag = next((a for _, a in self._visible if a.id == tag_id), None)
        if tag is not None:
            self._show_detail(tag)

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "tag-phase-select":
            self._apply_filters()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "tag-search-input":
            self._apply_filters()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "tag-btn-copy":
            self.action_copy_selected()
        elif event.button.id == "tag-btn-clear-sel":
            self._selected_ids.clear()
            self._rebuild_table()
        elif event.button.id == "tag-clear-btn":
            self._clear_filters()

    def _clear_filters(self) -> None:
        try:
            self.query_one("#tag-search-input", Input).value = ""
            sel = self.query_one("#tag-phase-select", Select)
            sel.value = ""
        except Exception:
            pass
        self._apply_filters()


# Backward-compat alias
AnnotationsPane = TagsPane
