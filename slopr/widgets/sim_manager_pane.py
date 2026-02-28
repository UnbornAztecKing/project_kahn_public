"""Simulation manager pane — content-area replacement for monitoring sims.

Layout::

    ┌─ SimManagerPane ─────────────────────────────────────────────────────────┐
    │ DataTable (1fr)                                                           │
    │  cols: Label | Branch | Scenario | Models | Turns | Status | Turn | PID  │
    ├───────────────────────────────────────────────────────────────────────────│
    │ events tail VerticalScroll (height: 8)                                    │
    │  last 30 events from selected sim's JSONL (type + title)                  │
    ├───────────────────────────────────────────────────────────────────────────│
    │ process log VerticalScroll (height: 10)                                   │
    │  last 80 lines from {branch_jsonl}.log (raw stdout/stderr)                │
    ├───────────────────────────────────────────────────────────────────────────│
    │ button row (height: 3): [Cancel]  [Retry]  [Clear Done]                   │
    └───────────────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import json
import os
import signal
from pathlib import Path
from typing import TYPE_CHECKING

from rich.text import Text

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, DataTable, Static

from slopr.sim_queue import SimQueue, SimRequest, SimStatus

if TYPE_CHECKING:
    pass

# ── Colours ──────────────────────────────────────────────────────────────────

_C_LABEL  = "#aaaaaa"
_C_STATUS_RUNNING  = "#4caf50"
_C_STATUS_FAILED   = "#ef5350"
_C_STATUS_COMPLETE = "#90a4ae"
_C_STATUS_QUEUED   = "#ffa726"
_C_MODEL  = "#7986cb"

_STATUS_COLORS = {
    SimStatus.RUNNING:  _C_STATUS_RUNNING,
    SimStatus.COMPLETE: _C_STATUS_COMPLETE,
    SimStatus.FAILED:   _C_STATUS_FAILED,
    SimStatus.QUEUED:   _C_STATUS_QUEUED,
}


def _t(value: str, color: str) -> Text:
    return Text(value, style=color)


def _status_text(status: SimStatus) -> Text:
    color = _STATUS_COLORS.get(status, _C_LABEL)
    return Text(status.value, style=color)


# ── Messages ─────────────────────────────────────────────────────────────────


class SimCancelRequested(Message):
    """Posted when the user wants to cancel a running sim."""

    def __init__(self, request_id: str) -> None:
        super().__init__()
        self.request_id = request_id


class SimRetryRequested(Message):
    """Posted when the user wants to retry a failed sim."""

    def __init__(self, request_id: str) -> None:
        super().__init__()
        self.request_id = request_id


# ── SimManagerPane ────────────────────────────────────────────────────────────


class SimManagerPane(Widget):
    """DataTable of all tracked sim requests with live output from selected sim."""

    DEFAULT_CSS = """
    SimManagerPane {
        height: 1fr;
        width: 3fr;
        layout: vertical;
    }
    #sim-table {
        height: 1fr;
        background: $background;
    }
    #sim-live-log {
        height: 8;
        background: $surface;
        border-top: solid $surface-lighten-2;
        scrollbar-size: 1 1;
        padding: 0 1;
    }
    #sim-proc-log {
        height: 10;
        background: $surface;
        border-top: solid $surface-lighten-3;
        scrollbar-size: 1 1;
        padding: 0 1;
    }
    .sim-log-section-header {
        color: $text-disabled;
        text-style: bold italic;
        height: 1;
        padding: 0 0;
    }
    #sim-btn-row {
        height: 3;
        dock: bottom;
        align: center middle;
        background: $surface;
    }
    #btn-cancel {
        margin-right: 1;
    }
    #btn-retry {
        margin-right: 1;
    }
    .sim-log-line {
        color: $text-muted;
        height: 1;
    }
    .sim-proc-line {
        color: $text-disabled;
        height: 1;
    }
    .sim-log-empty {
        color: $text-disabled;
        text-style: italic;
    }
    """

    def __init__(
        self, id: str | None = None, classes: str | None = None
    ) -> None:
        super().__init__(id=id, classes=classes)
        self._queue: SimQueue | None = None
        self._selected_request_id: str | None = None
        self._branch_store = None  # set by app via set_branch_store()

    def compose(self) -> ComposeResult:
        yield DataTable(id="sim-table", zebra_stripes=True)
        yield VerticalScroll(
            Static("Events  (last 30)", classes="sim-log-section-header"),
            Static("No sim selected.", classes="sim-log-empty"),
            id="sim-live-log",
        )
        yield VerticalScroll(
            Static("Process log", classes="sim-log-section-header"),
            Static("No sim selected.", classes="sim-log-empty"),
            id="sim-proc-log",
        )
        with Horizontal(id="sim-btn-row"):
            yield Button("Cancel",     id="btn-cancel",     variant="warning",  disabled=True)
            yield Button("Retry",      id="btn-retry",      variant="primary",  disabled=True)
            yield Button("Clear Done", id="btn-clear-done", variant="default")

    def on_mount(self) -> None:
        table = self.query_one("#sim-table", DataTable)
        table.cursor_type = "row"
        table.add_columns(
            _t("Label",    _C_LABEL),
            _t("Branch",   _C_LABEL),
            _t("Scenario", _C_LABEL),
            _t("Models",   _C_MODEL),
            _t("Turns",    _C_LABEL),
            _t("Status",   _C_LABEL),
            _t("Cur Turn", _C_LABEL),
            _t("PID",      _C_LABEL),
        )

    # ── Public API ───────────────────────────────────────────────────────

    def set_queue(self, queue: SimQueue) -> None:
        """Attach a :class:`SimQueue` and render the initial table."""
        self._queue = queue
        self.refresh_sims()

    def set_branch_store(self, branch_store) -> None:
        """Provide the BranchStore so we can look up branch JSONL paths."""
        self._branch_store = branch_store

    def refresh_sims(self) -> None:
        """Re-render the DataTable from the current queue contents.

        Reloads from disk first so status changes made by the background
        sim process (or by another call to ``update()``) are visible.
        Preserves the currently selected request if it still exists.
        """
        if self._queue is None:
            return

        # Reload queue from disk to pick up status changes
        self._queue.reload()

        table = self.query_one("#sim-table", DataTable)
        prev_selected = self._selected_request_id
        table.clear()

        for req in self._queue.list_all():
            models = f"{req.model_a} / {req.model_b}"
            cur_turn = str(req.current_turn) if req.current_turn is not None else "—"
            pid_str  = str(req.pid) if req.pid is not None else "—"

            table.add_row(
                _t(req.branch_label[:24], _C_LABEL),
                _t(req.branch_id[:8] + "…", _C_LABEL),
                _t(req.scenario[:18],        _C_LABEL),
                _t(models[:28],              _C_MODEL),
                _t(str(req.turns),           _C_LABEL),
                _status_text(req.status),
                _t(cur_turn,                 _C_LABEL),
                _t(pid_str,                  _C_LABEL),
                key=req.id,
            )

        # Restore previous selection
        if prev_selected is not None:
            try:
                table.move_cursor(row=table.get_row_index(prev_selected))
                self._update_buttons()
                self._refresh_live_log()
                return
            except Exception:
                pass

        self._update_buttons()

    def select_first_running(self) -> None:
        """Move the cursor to the first RUNNING sim in the table, if any."""
        if self._queue is None:
            return
        for i, req in enumerate(self._queue.list_all()):
            if req.status == SimStatus.RUNNING:
                table = self.query_one("#sim-table", DataTable)
                try:
                    table.move_cursor(row=i)
                    self._selected_request_id = req.id
                    self._update_buttons()
                    self._refresh_live_log()
                except Exception:
                    pass
                return

    def select_request(self, request_id: str) -> None:
        """Move the cursor to the row matching *request_id*, if present."""
        if self._queue is None:
            return
        for i, req in enumerate(self._queue.list_all()):
            if req.id == request_id:
                table = self.query_one("#sim-table", DataTable)
                try:
                    table.move_cursor(row=i)
                    self._selected_request_id = req.id
                    self._update_buttons()
                    self._refresh_live_log()
                except Exception:
                    pass
                return

    # ── Event handlers ───────────────────────────────────────────────────

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        key = event.row_key
        if key and key.value is not None:
            self._selected_request_id = key.value
            self._update_buttons()
            self._refresh_live_log()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self._do_cancel()
        elif event.button.id == "btn-retry":
            self._do_retry()
        elif event.button.id == "btn-clear-done":
            self._do_clear_done()

    # ── Private helpers ──────────────────────────────────────────────────

    def _update_buttons(self) -> None:
        """Enable/disable action buttons based on selected request state."""
        cancel_btn = self.query_one("#btn-cancel", Button)
        retry_btn  = self.query_one("#btn-retry",  Button)

        if self._queue is None or self._selected_request_id is None:
            cancel_btn.disabled = True
            retry_btn.disabled  = True
            return

        req = self._queue.get(self._selected_request_id)
        if req is None:
            cancel_btn.disabled = True
            retry_btn.disabled  = True
            return

        cancel_btn.disabled = req.status != SimStatus.RUNNING
        retry_btn.disabled  = req.status != SimStatus.FAILED

    def _refresh_live_log(self) -> None:
        """Show the last 30 events from the selected sim's branch JSONL."""
        log_scroll = self.query_one("#sim-live-log", VerticalScroll)
        log_scroll.remove_children()
        log_scroll.mount(Static("Events  (last 30)", classes="sim-log-section-header"))

        if self._queue is None or self._selected_request_id is None:
            log_scroll.mount(Static("No sim selected.", classes="sim-log-empty"))
            self._refresh_proc_log(None)
            return

        req = self._queue.get(self._selected_request_id)
        if req is None:
            log_scroll.mount(Static("Sim not found.", classes="sim-log-empty"))
            self._refresh_proc_log(None)
            return

        # Locate the branch JSONL via BranchStore
        branch_jsonl: Path | None = None
        if self._branch_store is not None:
            try:
                branch_jsonl = self._branch_store.get_jsonl_path(req.branch_id)
            except (KeyError, Exception):
                pass

        if branch_jsonl is None or not branch_jsonl.exists():
            log_scroll.mount(
                Static("Branch JSONL not found.", classes="sim-log-empty")
            )
            self._refresh_proc_log(None)
            return

        self._show_tail(branch_jsonl, log_scroll, n=30)
        self._refresh_proc_log(req.branch_id)

    def _refresh_proc_log(self, branch_id: str | None) -> None:
        """Show the last 80 lines of the process log file for *branch_id*."""
        proc_scroll = self.query_one("#sim-proc-log", VerticalScroll)
        proc_scroll.remove_children()
        proc_scroll.mount(Static("Process log", classes="sim-log-section-header"))

        if branch_id is None or self._branch_store is None:
            proc_scroll.mount(Static("No sim selected.", classes="sim-log-empty"))
            return

        try:
            log_path = self._branch_store.get_log_path(branch_id)
        except (KeyError, Exception):
            proc_scroll.mount(Static("Cannot resolve log path.", classes="sim-log-empty"))
            return

        if not log_path.exists():
            proc_scroll.mount(Static("(no log file yet)", classes="sim-log-empty"))
            return

        try:
            text = log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            proc_scroll.mount(Static("Cannot read log file.", classes="sim-log-empty"))
            return

        lines = [l for l in text.splitlines() if l.strip()][-80:]
        if not lines:
            proc_scroll.mount(Static("(log is empty)", classes="sim-log-empty"))
            return

        widgets = [Static(line[:160], classes="sim-proc-line") for line in lines]
        proc_scroll.mount(*widgets)
        proc_scroll.scroll_end(animate=False)

    def _show_tail(
        self, branch_jsonl: Path, container: VerticalScroll, n: int = 30
    ) -> None:
        """Parse the last *n* lines of *branch_jsonl* and render as log lines."""
        try:
            text = branch_jsonl.read_text(encoding="utf-8", errors="replace")
        except OSError:
            container.mount(Static("Cannot read branch JSONL.", classes="sim-log-empty"))
            return

        lines = [l for l in text.splitlines() if l.strip()][-n:]
        if not lines:
            container.mount(Static("(no events yet)", classes="sim-log-empty"))
            return

        widgets = []
        for line in lines:
            try:
                obj = json.loads(line)
                event_type = obj.get("event_type", "?")
                title      = obj.get("title", "")
                turn       = obj.get("turn_number", "?")
                label = f"T{turn}  [{event_type}]  {title}"
            except Exception:
                label = line[:120]
            widgets.append(Static(label[:120], classes="sim-log-line"))

        container.mount(*widgets)
        # Scroll to bottom
        container.scroll_end(animate=False)

    def _do_cancel(self) -> None:
        if self._selected_request_id is None or self._queue is None:
            return
        req = self._queue.get(self._selected_request_id)
        if req is None or req.status != SimStatus.RUNNING:
            return
        if req.pid is not None:
            try:
                os.kill(req.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
        self.post_message(SimCancelRequested(self._selected_request_id))

    def _do_retry(self) -> None:
        if self._selected_request_id is None:
            return
        self.post_message(SimRetryRequested(self._selected_request_id))

    def _do_clear_done(self) -> None:
        if self._queue is None:
            return
        self._queue.clear_finished()
        self.refresh_sims()
