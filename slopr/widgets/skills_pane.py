"""Skills pane — view and edit skill definitions.

Layout::

    ┌─ SkillsPane ──────────────────────────────────────────────────────────────┐
    │ DataTable (1fr)                                                            │
    │  cols: # | Label | Phases | Type (built-in / custom)                      │
    ├───────────────────────────────────────────────────────────────────────────│
    │ Edit panel (height: auto; shown when row selected)                        │
    │  [Label: ___________]  [Phases: ____________]  (blank phases = all)       │
    │  Prompt Template: [TextArea, height: 12]                                  │
    ├───────────────────────────────────────────────────────────────────────────│
    │ Button row (height: 3): [New] [Save] [Reset to Default] [Delete]          │
    └───────────────────────────────────────────────────────────────────────────┘

Keyboard shortcuts (within this pane):
  Enter    — select / activate highlighted row
  Escape   — clear edit panel selection
"""

from __future__ import annotations

from typing import Any

from rich.text import Text

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.widget import Widget
from textual.widgets import Button, DataTable, Input, Label, Static, TextArea

from slopr.skill_store import Skill, SkillStore

# ── Colors ────────────────────────────────────────────────────────────────────

_C_NUM    = "#aaaaaa"
_C_LABEL  = "#90a4ae"
_C_PHASES = "#7986cb"
_C_TYPE   = "#4caf50"


def _t(value: str, color: str) -> Text:
    return Text(value, style=color)


# ── SkillsPane ────────────────────────────────────────────────────────────────


class SkillsPane(Widget):
    """Content-area pane for viewing and editing skill definitions."""

    BINDINGS = [
        Binding("escape", "clear_selection", "Clear", show=False),
    ]

    DEFAULT_CSS = """
    SkillsPane {
        height: 1fr;
        width: 3fr;
        layout: vertical;
    }
    #skill-table {
        height: 1fr;
    }
    #skill-edit-panel {
        height: auto;
        border-top: solid $surface-lighten-2;
        padding: 1 1 0 1;
    }
    #skill-field-row {
        height: auto;
        layout: horizontal;
        margin-bottom: 1;
    }
    #skill-label-input {
        width: 1fr;
        margin-right: 1;
    }
    #skill-phases-input {
        width: 24;
    }
    #skill-prompt-label {
        height: 1;
        color: $text-muted;
        margin-bottom: 0;
    }
    #skill-prompt-area {
        height: 12;
        border: solid $surface-lighten-2;
    }
    #skill-btn-row {
        height: 3;
        align: left middle;
        border-top: solid $surface-lighten-2;
        padding: 0 1;
    }
    #skill-btn-row Button {
        margin-right: 1;
        height: 1;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._store: SkillStore | None = None
        self._selected_id: str | None = None  # skill.id of currently selected row
        self._is_new: bool = False             # True when composing a new skill

    # ── Public API ────────────────────────────────────────────────────────

    def set_store(self, store: SkillStore) -> None:
        """Attach or replace the SkillStore."""
        self._store = store

    def refresh_skills(self) -> None:
        """Reload skills from the store and repopulate the table."""
        self._rebuild_table()

    # ── Compose ───────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        tbl: DataTable[str] = DataTable(id="skill-table", cursor_type="row")
        tbl.add_columns(
            _t("#",         _C_NUM),
            _t("Label",     _C_LABEL),
            _t("Phases",    _C_PHASES),
            _t("Type",      _C_TYPE),
        )
        yield tbl

        with VerticalScroll(id="skill-edit-panel"):
            with Horizontal(id="skill-field-row"):
                yield Input(placeholder="Label", id="skill-label-input")
                yield Input(
                    placeholder="Phases (comma-sep, blank=all)",
                    id="skill-phases-input",
                )
            yield Label("Prompt Template  ({event_block} and {context_block} are substituted at runtime)",
                        id="skill-prompt-label")
            yield TextArea(id="skill-prompt-area")

        with Horizontal(id="skill-btn-row"):
            yield Button("New",              id="btn-skill-new",    variant="default")
            yield Button("Save",             id="btn-skill-save",   variant="primary")
            yield Button("Reset to Default", id="btn-skill-reset",  variant="default")
            yield Button("Delete",           id="btn-skill-delete", variant="error")

    def on_mount(self) -> None:
        self._rebuild_table()
        self._update_button_states()

    # ── Internal ──────────────────────────────────────────────────────────

    def _rebuild_table(self) -> None:
        tbl = self.query_one("#skill-table", DataTable)
        tbl.clear()
        if self._store is None:
            return
        for i, skill in enumerate(self._store.list_all(), start=1):
            phases_str = ", ".join(skill.applicable_phases) or "(all)"
            type_str   = "built-in" if skill.builtin else "custom"
            tbl.add_row(
                _t(str(i),       _C_NUM),
                _t(skill.label,  _C_LABEL),
                _t(phases_str,   _C_PHASES),
                _t(type_str,     _C_TYPE),
                key=skill.id,
            )

    def _populate_edit_panel(self, skill: Skill) -> None:
        """Fill the edit form with *skill*'s values."""
        self.query_one("#skill-label-input", Input).value = skill.label
        self.query_one("#skill-phases-input", Input).value = ", ".join(skill.applicable_phases)
        area = self.query_one("#skill-prompt-area", TextArea)
        area.load_text(skill.prompt_template)

    def _clear_edit_panel(self) -> None:
        self.query_one("#skill-label-input", Input).value = ""
        self.query_one("#skill-phases-input", Input).value = ""
        area = self.query_one("#skill-prompt-area", TextArea)
        area.load_text("")

    def _read_edit_panel(self) -> tuple[str, list[str], str]:
        """Return (label, phases, prompt_template) from the edit form."""
        label = self.query_one("#skill-label-input", Input).value.strip()
        phases_raw = self.query_one("#skill-phases-input", Input).value.strip()
        phases = [p.strip() for p in phases_raw.split(",") if p.strip()] if phases_raw else []
        prompt = self.query_one("#skill-prompt-area", TextArea).text
        return label, phases, prompt

    def _update_button_states(self) -> None:
        """Enable/disable buttons based on current selection."""
        skill = self._get_selected_skill()
        is_new = self._is_new

        reset_btn  = self.query_one("#btn-skill-reset",  Button)
        delete_btn = self.query_one("#btn-skill-delete", Button)

        if is_new or skill is None:
            reset_btn.disabled  = True
            delete_btn.disabled = True
        else:
            reset_btn.disabled  = not skill.builtin
            delete_btn.disabled = skill.builtin

    def _get_selected_skill(self) -> Skill | None:
        if self._store is None or self._selected_id is None:
            return None
        return self._store.get(self._selected_id)

    # ── Event handlers ────────────────────────────────────────────────────

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id != "skill-table":
            return
        if event.row_key is None:
            return
        skill_id = str(event.row_key.value)
        if self._store is None:
            return
        skill = self._store.get(skill_id)
        if skill is None:
            return
        self._selected_id = skill_id
        self._is_new = False
        self._populate_edit_panel(skill)
        self._update_button_states()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id

        if btn_id == "btn-skill-new":
            self._selected_id = None
            self._is_new = True
            self._clear_edit_panel()
            self._update_button_states()
            self.query_one("#skill-label-input", Input).focus()

        elif btn_id == "btn-skill-save":
            self._action_save()

        elif btn_id == "btn-skill-reset":
            self._action_reset()

        elif btn_id == "btn-skill-delete":
            self._action_delete()

    # ── Actions ───────────────────────────────────────────────────────────

    def action_clear_selection(self) -> None:
        self._selected_id = None
        self._is_new = False
        self._clear_edit_panel()
        self._update_button_states()

    def _action_save(self) -> None:
        if self._store is None:
            return
        label, phases, prompt = self._read_edit_panel()
        if not label:
            self.app.notify("Label is required.", severity="warning", timeout=3)
            return
        if not prompt:
            self.app.notify("Prompt template is required.", severity="warning", timeout=3)
            return

        if self._is_new:
            new_skill = Skill(
                id="",   # will be assigned by add()
                label=label,
                applicable_phases=phases,
                prompt_template=prompt,
                builtin=False,
            )
            stored = self._store.add(new_skill)
            self._selected_id = stored.id
            self._is_new = False
            self.app.notify(f"Skill '{label}' created.", timeout=2)
        else:
            if self._selected_id is None:
                return
            try:
                self._store.update(
                    self._selected_id,
                    label=label,
                    applicable_phases=phases,
                    prompt_template=prompt,
                )
                self.app.notify(f"Skill '{label}' saved.", timeout=2)
            except ValueError as exc:
                self.app.notify(str(exc), severity="error", timeout=4)
                return

        self._rebuild_table()
        self._update_button_states()

    def _action_reset(self) -> None:
        if self._store is None or self._selected_id is None:
            return
        try:
            self._store.reset_builtin(self._selected_id)
            skill = self._store.get(self._selected_id)
            if skill:
                self._populate_edit_panel(skill)
            self._rebuild_table()
            self.app.notify("Skill reset to default.", timeout=2)
        except ValueError as exc:
            self.app.notify(str(exc), severity="error", timeout=4)

    def _action_delete(self) -> None:
        if self._store is None or self._selected_id is None:
            return
        skill = self._store.get(self._selected_id)
        label = skill.label if skill else self._selected_id
        try:
            self._store.delete(self._selected_id)
            self._selected_id = None
            self._is_new = False
            self._clear_edit_panel()
            self._rebuild_table()
            self._update_button_states()
            self.app.notify(f"Skill '{label}' deleted.", timeout=2)
        except ValueError as exc:
            self.app.notify(str(exc), severity="error", timeout=4)
