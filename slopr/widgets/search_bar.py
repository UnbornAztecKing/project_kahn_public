"""Quick search bar — bottom-docked incremental filter."""

from __future__ import annotations

from textual.message import Message
from textual.widgets import Input


class SearchSubmitted(Message):
    """Posted when the user presses Enter in the search bar."""

    def __init__(self, query: str) -> None:
        super().__init__()
        self.query = query


class SearchBar(Input):
    """Inline search input that posts ``SearchSubmitted`` on Enter."""

    def __init__(self) -> None:
        super().__init__(placeholder="Search events...", id="search-bar")
        self.display = False

    def toggle(self) -> None:
        self.display = not self.display
        if self.display:
            self.value = ""
            self.focus()
        else:
            self.screen.focus_next()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if self.value.strip():
            self.post_message(SearchSubmitted(self.value.strip()))
