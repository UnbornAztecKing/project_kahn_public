"""Tasks pane — running log of LLM analysis calls.

Each analysis command triggered via right-click shows up here as a row.
The detail panel below shows metadata, the full prompt, and the result
for the selected task.

Layout::

    ┌─ TasksPane ─────────────────────────────────────────────────────────────┐
    │ DataTable (1fr)                                                          │
    │  cols: # | Command | Event | Model | Status | Tokens                    │
    ├──────────────────────────────────────────────────────────────────────────│
    │ detail panel (VerticalScroll, 2fr)                                       │
    │  ─ Metadata ─  model, tokens, elapsed                                   │
    │  ─ Prompt ──  full prompt text (scrollable)                             │
    │  ─ Result ──  full result text (scrollable)                             │
    ├──────────────────────────────────────────────────────────────────────────│
    │ button row (height: 3): [Clear Done]                                     │
    └──────────────────────────────────────────────────────────────────────────┘

Tasks are persisted to ``{sim}.jsonl.tasks.jsonl`` via :class:`TaskStore`
so they survive TUI restarts.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Callable, Coroutine, Any

from rich.text import Text

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, DataTable, Static

from slopr.task_store import TaskEntry, TaskStore


# ── Colours ───────────────────────────────────────────────────────────────────

_C_RUNNING  = "#ffa726"
_C_DONE     = "#4caf50"
_C_ERROR    = "#ef5350"
_C_LABEL    = "#aaaaaa"
_C_MODEL    = "#7986cb"
_C_HEADER   = "#546e7a"


def _t(value: str, color: str) -> Text:
    return Text(value, style=color)


def _status_text(status: str) -> Text:
    colors = {
        "running": _C_RUNNING,
        "done":    _C_DONE,
        "error":   _C_ERROR,
    }
    return Text(status, style=colors.get(status, _C_LABEL))


# ── Messages ─────────────────────────────────────────────────────────────────


class TaskCompleted(Message):
    """Posted by TasksPane when an analysis task finishes (used to save annotation)."""

    def __init__(self, task: TaskEntry) -> None:
        super().__init__()
        self.task = task


# ── TasksPane ────────────────────────────────────────────────────────────────


class TasksPane(Widget):
    """Content-area pane showing in-flight and completed LLM analysis tasks."""

    DEFAULT_CSS = """
    TasksPane {
        layout: vertical;
        height: 1fr;
    }
    TasksPane DataTable {
        height: 1fr;
        border-bottom: solid $surface-lighten-2;
    }
    TasksPane #task-detail-scroll {
        height: 2fr;
        border-bottom: solid $surface-lighten-2;
        padding: 0 1;
    }
    TasksPane #task-detail-empty {
        color: $text-disabled;
        margin: 1 1;
    }
    TasksPane #task-btn-row {
        height: 3;
        align: left middle;
        padding: 0 1;
    }
    TasksPane #task-btn-row Button {
        margin: 0 1 0 0;
    }
    TasksPane .task-section-header {
        color: $text-muted;
        text-style: bold;
        height: 1;
        background: $surface;
        margin: 1 0 0 0;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._tasks: dict[str, TaskEntry] = {}
        self._display_nums: dict[str, int] = {}
        self._next_num: int = 1
        self._selected_id: str | None = None
        self._store: TaskStore | None = None
        self._start_times: dict[str, float] = {}

    def set_store(self, store: TaskStore) -> None:
        """Wire in a persistent TaskStore.  Must be called before first use."""
        self._store = store

    def compose(self) -> ComposeResult:
        tbl: DataTable[str] = DataTable(id="task-table", cursor_type="row")
        # Use explicit string keys so update_cell() can locate columns reliably.
        # Textual auto-generates UUID keys when no key is specified, making
        # label-based lookup in update_cell fail silently.
        tbl.add_column("#",       key="num")
        tbl.add_column("Command", key="cmd")
        tbl.add_column("Event",   key="evt")
        tbl.add_column("Model",   key="mdl")
        tbl.add_column("Status",  key="status")
        tbl.add_column("In",      key="in_tok")
        tbl.add_column("Out",     key="out_tok")
        yield tbl

        with VerticalScroll(id="task-detail-scroll"):
            yield Static("", id="task-detail-content")
        yield Static("No task selected.", id="task-detail-empty")

        with Horizontal(id="task-btn-row"):
            yield Button("Clear Done", id="btn-task-clear", variant="default")

    # ── Public API ────────────────────────────────────────────────────────

    def add_task(
        self,
        skill_label: str = "",
        event_title: str = "",
        model: str = "",
        coro: "Coroutine[Any, Any, tuple[str, str, dict]] | None" = None,
        on_done: "Callable[[TaskEntry], None] | None" = None,
        # Backward-compat alias — old callers may pass command_label= positionally
        command_label: str = "",
    ) -> str:
        """Register a task and launch it as a background coroutine.

        Returns the task_id (UUID string).
        ``on_done`` is called on the event loop thread when the task completes.
        """
        entry = TaskEntry.new(
            skill_label=skill_label or command_label,
            event_title=event_title,
            model=model,
        )
        display_num = self._next_num
        self._next_num += 1
        self._display_nums[entry.task_id] = display_num
        self._tasks[entry.task_id] = entry
        self._start_times[entry.task_id] = time.monotonic()

        if self._store is not None:
            self._store.add(entry)

        self._append_row(entry)
        if coro is not None:
            try:
                asyncio.get_running_loop().create_task(
                    self._run_task(entry.task_id, coro, on_done)
                )
            except RuntimeError:
                # Fallback if called outside a running loop (tests, etc.)
                asyncio.get_event_loop().create_task(
                    self._run_task(entry.task_id, coro, on_done)
                )
        return entry.task_id

    # ── Internal ──────────────────────────────────────────────────────────

    async def _run_task(
        self,
        task_id: str,
        coro: Coroutine[Any, Any, tuple[str, str, dict]],
        on_done: Callable[[TaskEntry], None] | None,
    ) -> None:
        entry = self._tasks[task_id]
        start = self._start_times.get(task_id, time.monotonic())
        try:
            prompt, result_text, meta = await coro
            elapsed = time.monotonic() - start
            entry.status = "done"
            entry.result = result_text
            entry.prompt = prompt
            entry.input_tokens = meta.get("input_tokens", 0)
            entry.output_tokens = meta.get("output_tokens", 0)
            entry.elapsed_s = round(elapsed, 2)
        except Exception as exc:
            elapsed = time.monotonic() - start
            entry.status = "error"
            entry.error = str(exc)
            entry.elapsed_s = round(elapsed, 2)
        finally:
            if self._store is not None:
                self._store.update(
                    task_id,
                    status=entry.status,
                    result=entry.result,
                    prompt=entry.prompt,
                    input_tokens=entry.input_tokens,
                    output_tokens=entry.output_tokens,
                    elapsed_s=entry.elapsed_s,
                    error=entry.error,
                )
            self._update_row(entry)
            if entry.status == "done":
                self.post_message(TaskCompleted(entry))
                if on_done is not None:
                    on_done(entry)

    def _append_row(self, entry: TaskEntry) -> None:
        tbl = self.query_one("#task-table", DataTable)
        num = self._display_nums.get(entry.task_id, "?")
        tbl.add_row(
            _t(str(num), _C_LABEL),
            entry.skill_label,
            entry.event_title[:30],
            _t(entry.model[:24], _C_MODEL),
            _status_text(entry.status),
            _t("—", _C_LABEL),
            _t("—", _C_LABEL),
            key=entry.task_id,
        )

    def _update_row(self, entry: TaskEntry) -> None:
        tbl = self.query_one("#task-table", DataTable)
        row_key = entry.task_id
        in_str  = str(entry.input_tokens)  if entry.input_tokens  else "—"
        out_str = str(entry.output_tokens) if entry.output_tokens else "—"
        try:
            tbl.update_cell(row_key, "status",  _status_text(entry.status), update_width=False)
            tbl.update_cell(row_key, "in_tok",  _t(in_str,  _C_LABEL), update_width=False)
            tbl.update_cell(row_key, "out_tok", _t(out_str, _C_LABEL), update_width=False)
        except Exception:
            pass
        if self._selected_id == entry.task_id:
            self._show_detail(entry)

    def _show_detail(self, entry: TaskEntry) -> None:
        self._selected_id = entry.task_id
        scroll = self.query_one("#task-detail-scroll", VerticalScroll)
        empty = self.query_one("#task-detail-empty", Static)
        content = self.query_one("#task-detail-content", Static)

        if entry.status == "running":
            text = "[bold yellow]Running…[/]"
        elif entry.status == "error":
            elapsed_str = f"  Elapsed: {entry.elapsed_s:.1f}s" if entry.elapsed_s else ""
            meta_line = f"[dim]Model:[/] [bold]{entry.model}[/]{elapsed_str}"
            text = (
                f"[bold {_C_HEADER}]─ Metadata {'─' * 40}[/]\n"
                f"{meta_line}\n\n"
                f"[bold {_C_HEADER}]─ Error {'─' * 43}[/]\n"
                f"[bold red]{entry.error}[/]"
            )
        else:
            # Build 3-section rich text
            elapsed_str = f"  Elapsed: {entry.elapsed_s:.1f}s" if entry.elapsed_s else ""
            in_str  = str(entry.input_tokens)  if entry.input_tokens  else "—"
            out_str = str(entry.output_tokens) if entry.output_tokens else "—"
            meta_line = (
                f"[dim]Model:[/] [bold]{entry.model}[/]{elapsed_str}\n"
                f"[dim]In:[/] {in_str}  [dim]Out:[/] {out_str}"
            )
            prompt_text = entry.prompt or "(no prompt recorded)"
            result_text = entry.result or "(no result)"
            text = (
                f"[bold {_C_HEADER}]─ Metadata {'─' * 40}[/]\n"
                f"{meta_line}\n\n"
                f"[bold {_C_HEADER}]─ Prompt {'─' * 42}[/]\n"
                f"{prompt_text}\n\n"
                f"[bold {_C_HEADER}]─ Result {'─' * 42}[/]\n"
                f"{result_text}"
            )

        content.update(text)
        scroll.display = True
        empty.display = False

    # ── Event handlers ────────────────────────────────────────────────────

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id != "task-table":
            return
        if event.row_key is None:
            return
        task_id = str(event.row_key.value)
        entry = self._tasks.get(task_id)
        if entry is not None:
            self._show_detail(entry)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-task-clear":
            self._clear_done()

    def _clear_done(self) -> None:
        tbl = self.query_one("#task-table", DataTable)
        done_ids = [
            tid for tid, e in self._tasks.items()
            if e.status != "running"
        ]
        for tid in done_ids:
            try:
                tbl.remove_row(tid)
            except Exception:
                pass
            del self._tasks[tid]
            self._display_nums.pop(tid, None)
            self._start_times.pop(tid, None)
        if self._selected_id in done_ids:
            self._selected_id = None
            scroll = self.query_one("#task-detail-scroll", VerticalScroll)
            empty = self.query_one("#task-detail-empty", Static)
            scroll.display = False
            empty.display = True
