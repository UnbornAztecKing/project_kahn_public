"""Search modal — full-screen search with paginated results."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList, Static
from textual.widgets.option_list import Option

from slopr.models import GameEvent
from slopr.store import EventStore


class SearchResultSelected(Message):
    """Posted when the user selects a search result."""

    def __init__(self, turn: int) -> None:
        super().__init__()
        self.turn = turn


class SearchModal(ModalScreen[int | None]):
    """Full-screen modal for searching events."""

    BINDINGS = [
        Binding("escape", "dismiss_modal", "Close"),
    ]

    DEFAULT_CSS = """
    SearchModal {
        align: center middle;
    }
    #search-container {
        width: 80%;
        max-width: 100;
        height: 80%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    #search-input {
        dock: top;
        margin-bottom: 1;
    }
    #search-results {
        height: 1fr;
    }
    #search-status {
        dock: bottom;
        height: 1;
        color: $text-muted;
    }
    """

    def __init__(self, store: EventStore) -> None:
        super().__init__()
        self._store = store
        self._results: list[GameEvent] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="search-container"):
            yield Input(placeholder="Search events...", id="search-input")
            yield OptionList(id="search-results")
            yield Static("Type to search", id="search-status")

    def on_mount(self) -> None:
        self.query_one("#search-input", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        query = event.value.strip()
        results_list = self.query_one("#search-results", OptionList)
        results_list.clear_options()
        self._results.clear()

        if len(query) < 2:
            self.query_one("#search-status", Static).update("Type at least 2 characters")
            return

        self._results = self._store.search(query, limit=50)
        status = self.query_one("#search-status", Static)

        if not self._results:
            status.update("No results")
            return

        for evt in self._results:
            label = f"T{evt.turn_number} | {evt.title}"
            if evt.body:
                label += f" — {evt.body[:60]}"
            results_list.add_option(Option(label))

        status.update(f"{len(self._results)} result(s)")

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        idx = event.option_index
        if 0 <= idx < len(self._results):
            turn = self._results[idx].turn_number
            self.dismiss(turn)

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)
