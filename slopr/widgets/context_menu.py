"""Floating context menu for right-click skill invocation.

Mounted to the screen layer when the user right-clicks an EventCard.
Supports keyboard navigation (Up/Down/j/k, Enter, Escape) and
dismiss-on-click-outside.

Usage (from app.py or ContentPane)::

    from slopr.widgets.context_menu import ContextMenuScreen, AnalysisRequested
    from slopr.skill_store import Skill

    def _show_context_menu(self, event: GameEvent, offset: Offset) -> None:
        skills = self._skill_store.applicable_skills(event)

        def _on_result(skill_id: str | None) -> None:
            if skill_id is not None:
                self.post_message(AnalysisRequested(skill_id, event))

        self.app.push_screen(ContextMenuScreen(skills, offset), _on_result)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.events import Click
from textual.geometry import Offset
from textual.message import Message
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Static

if TYPE_CHECKING:
    from slopr.models import GameEvent
    from slopr.skill_store import Skill


# ── Message ──────────────────────────────────────────────────────────────────


class AnalysisRequested(Message):
    """Posted when the user selects a skill from the context menu."""

    def __init__(self, skill_id: str, event: "GameEvent") -> None:
        super().__init__()
        self.skill_id = skill_id
        self.event = event

    # Backward-compat property for callers that used command_id
    @property
    def command_id(self) -> str:
        return self.skill_id


# ── Internal widgets ─────────────────────────────────────────────────────────


class _MenuItem(Static):
    """One row in the context menu."""

    can_focus = True

    def __init__(self, skill_id: str, label: str) -> None:
        super().__init__(label, classes="context-item")
        self.skill_id = skill_id

    def on_click(self, _: Click) -> None:
        self.post_message(_ItemSelected(self.skill_id))

    def on_focus(self) -> None:
        self.add_class("--hi")

    def on_blur(self) -> None:
        self.remove_class("--hi")


class _ItemSelected(Message):
    """Internal: a menu item was clicked/activated."""

    def __init__(self, skill_id: str) -> None:
        super().__init__()
        self.skill_id = skill_id


class _ContextMenuWidget(Widget):
    """The visible popup box listing skills."""

    BINDINGS = [
        Binding("up",     "move_up",   "Up",    show=False),
        Binding("k",      "move_up",   "Up",    show=False),
        Binding("down",   "move_down", "Down",  show=False),
        Binding("j",      "move_down", "Down",  show=False),
        Binding("enter",  "activate",  "Select",show=False),
    ]

    DEFAULT_CSS = """
    _ContextMenuWidget {
        width: 36;
        height: auto;
        background: $surface;
        border: solid $primary;
        padding: 0 1;
    }
    .context-item {
        height: 1;
        padding: 0 1;
        color: $text;
    }
    .context-item.--hi {
        background: $surface-lighten-2;
        color: $accent;
        text-style: bold;
    }
    """

    def __init__(self, skills: "list[Skill]") -> None:
        super().__init__()
        self._skills = skills

    def compose(self) -> ComposeResult:
        for skill in self._skills:
            label = f"{skill.glyph}  {skill.label}" if skill.glyph else skill.label
            yield _MenuItem(skill.id, label)

    def on_mount(self) -> None:
        items = self.query(_MenuItem)
        if items:
            items.first().focus()

    def _focused_index(self) -> int:
        items = list(self.query(_MenuItem))
        for i, item in enumerate(items):
            if item.has_focus:
                return i
        return 0

    def action_move_up(self) -> None:
        items = list(self.query(_MenuItem))
        if not items:
            return
        idx = max(0, self._focused_index() - 1)
        items[idx].focus()

    def action_move_down(self) -> None:
        items = list(self.query(_MenuItem))
        if not items:
            return
        idx = min(len(items) - 1, self._focused_index() + 1)
        items[idx].focus()

    def action_activate(self) -> None:
        items = list(self.query(_MenuItem))
        if not items:
            return
        item = items[self._focused_index()]
        self.post_message(_ItemSelected(item.skill_id))


# ── ContextMenuScreen ────────────────────────────────────────────────────────


class ContextMenuScreen(ModalScreen[str | None]):
    """Transparent full-screen modal hosting :class:`_ContextMenuWidget`.

    Dismissed with the selected ``skill_id``, or ``None`` on cancel.
    """

    BINDINGS = [Binding("escape", "dismiss_menu", "Cancel")]

    DEFAULT_CSS = """
    ContextMenuScreen {
        background: transparent;
    }
    ContextMenuScreen _ContextMenuWidget {
        position: absolute;
    }
    """

    def __init__(
        self,
        skills: "list[Skill]",
        offset: Offset,
    ) -> None:
        super().__init__()
        self._skills = skills
        self._offset = offset

    def compose(self) -> ComposeResult:
        yield _ContextMenuWidget(self._skills)

    def on_mount(self) -> None:
        menu = self.query_one(_ContextMenuWidget)
        screen_w, screen_h = self.app.size
        menu_w = menu.styles.width.value if menu.styles.width else 36  # type: ignore[union-attr]
        menu_h = len(self._skills) + 2
        x = max(0, min(self._offset.x, screen_w - menu_w))
        y = max(0, min(self._offset.y, screen_h - menu_h))
        menu.styles.offset = (x, y)

    def on_click(self, event: Click) -> None:
        """Dismiss if the click lands outside the menu widget."""
        menu = self.query_one(_ContextMenuWidget)
        region = menu.region
        if not region.contains(event.screen_x, event.screen_y):
            self.dismiss(None)
            event.stop()

    def on__item_selected(self, message: _ItemSelected) -> None:
        self.dismiss(message.skill_id)

    def action_dismiss_menu(self) -> None:
        self.dismiss(None)
