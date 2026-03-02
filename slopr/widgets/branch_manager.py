"""Branch manager panel — tree view of simulation branches with CRUD actions."""

from __future__ import annotations

from typing import NamedTuple

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Button, Input, Label, Static, TextArea, Tree
from textual.widgets.tree import TreeNode

from slopr.branches import BranchEntry, BranchStore


class BranchActivated(Message):
    """Posted when the user selects a branch to view in the content pane."""

    def __init__(self, branch_id: str | None) -> None:
        super().__init__()
        self.branch_id = branch_id
        """None = root stream."""


class BranchSimRequested(Message):
    """Posted when the user wants to spawn a sim for a branch."""

    def __init__(self, branch_id: str, sim_kwargs: dict) -> None:
        super().__init__()
        self.branch_id = branch_id
        self.sim_kwargs = sim_kwargs


class BranchDeleted(Message):
    """Posted when the user deletes a branch."""

    def __init__(self, branch_id: str) -> None:
        super().__init__()
        self.branch_id = branch_id


class BranchEdited(Message):
    """Posted when the user saves edits to a branch via :class:`EditBranchModal`."""

    def __init__(
        self,
        branch_id: str,
        label: str,
        annotation: str,
        reset_to_fork: bool,
        event_title: str = "",
        event_body: str = "",
    ) -> None:
        super().__init__()
        self.branch_id = branch_id
        self.label = label
        self.annotation = annotation
        self.reset_to_fork = reset_to_fork
        self.event_title = event_title
        self.event_body = event_body


class SpawnConfig(NamedTuple):
    model_a: str
    model_b: str
    turns: int


class SpawnSimModal(ModalScreen[SpawnConfig | None]):
    """Small form for configuring and launching a branch simulation.

    The scenario and all other game parameters are inherited from the parent
    branch's JSONL file — only the models and number of additional turns can
    be changed here.
    """

    BINDINGS = [Binding("escape", "dismiss_modal", "Cancel")]

    DEFAULT_CSS = """
    SpawnSimModal {
        align: center middle;
    }
    #spawn-container {
        width: 60;
        height: auto;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    #spawn-container Label {
        color: $text-muted;
        margin-top: 1;
    }
    #spawn-container Input {
        margin-bottom: 0;
    }
    #spawn-btn-row {
        height: 3;
        align: right middle;
        margin-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="spawn-container"):
            yield Static("Spawn Branch Simulation", classes="panel-title")
            yield Static(
                "Scenario and game parameters are inherited from the parent branch.",
                classes="fork-info",
            )
            yield Label("Model A")
            yield Input(value="claude-sonnet-4-6", id="model-a-input")
            yield Label("Model B")
            yield Input(value="gpt-5.2", id="model-b-input")
            yield Label("Additional turns")
            yield Input(value="15", id="turns-input")
            with Horizontal(id="spawn-btn-row"):
                yield Button("Spawn", id="btn-spawn-ok", variant="primary")
                yield Button("Cancel", id="btn-spawn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-spawn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-spawn-ok":
            model_a = self.query_one("#model-a-input", Input).value.strip()
            model_b = self.query_one("#model-b-input", Input).value.strip()
            try:
                turns = int(self.query_one("#turns-input", Input).value.strip())
            except ValueError:
                turns = 15
            self.dismiss(SpawnConfig(model_a, model_b, turns))

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)


class EditBranchResult(NamedTuple):
    label: str
    annotation: str
    reset_to_fork: bool
    event_title: str = ""
    event_body: str = ""


class EditBranchModal(ModalScreen["EditBranchResult | None"]):
    """Form for editing branch label/annotation and optionally resetting to fork."""

    BINDINGS = [Binding("escape", "dismiss_modal", "Cancel")]

    DEFAULT_CSS = """
    EditBranchModal {
        align: center middle;
    }
    #edit-branch-container {
        width: 64;
        height: auto;
        max-height: 46;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
        overflow-y: auto;
    }
    #edit-branch-container Label {
        color: $text-muted;
        margin-top: 1;
    }
    #edit-branch-container .fork-info {
        color: $text-disabled;
        text-style: italic;
        margin-top: 1;
        height: 1;
    }
    #edit-btn-row {
        height: 3;
        align: right middle;
        margin-top: 1;
    }
    #btn-edit-reset {
        margin-right: 1;
    }
    #branch-event-body {
        height: 8;
        margin-bottom: 1;
    }
    """

    def __init__(self, entry: BranchEntry) -> None:
        super().__init__()
        self._entry = entry

    def compose(self) -> ComposeResult:
        edited = self._entry.edited_event or {}
        with Vertical(id="edit-branch-container"):
            yield Static("Edit Branch", classes="panel-title")
            yield Label("Label")
            yield Input(value=self._entry.label, id="branch-label-input")
            yield Label("Annotation")
            yield Input(value=self._entry.annotation, id="branch-annotation-input")
            if self._entry.edited_event is not None:
                yield Label("Event Title")
                yield Input(
                    value=edited.get("title", ""),
                    id="branch-event-title-input",
                )
                yield Label("Event Body")
                yield TextArea(
                    text=edited.get("body", ""),
                    id="branch-event-body",
                )
            yield Static(
                f"Fork: T{self._entry.fork_turn}  ·  seq {self._entry.fork_sequence}",
                classes="fork-info",
            )
            with Horizontal(id="edit-btn-row"):
                yield Button("Reset to Fork", id="btn-edit-reset", variant="warning")
                yield Button("Save", id="btn-edit-save", variant="primary")
                yield Button("Cancel", id="btn-edit-cancel")

    def _collect(self, reset: bool) -> EditBranchResult:
        label = self.query_one("#branch-label-input", Input).value.strip()
        annotation = self.query_one("#branch-annotation-input", Input).value.strip()
        event_title = ""
        event_body = ""
        if self._entry.edited_event is not None:
            event_title = self.query_one("#branch-event-title-input", Input).value.strip()
            event_body = self.query_one("#branch-event-body", TextArea).text
        return EditBranchResult(
            label=label or self._entry.label,
            annotation=annotation,
            reset_to_fork=reset,
            event_title=event_title,
            event_body=event_body,
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-edit-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-edit-save":
            self.dismiss(self._collect(reset=False))
        elif event.button.id == "btn-edit-reset":
            self.dismiss(self._collect(reset=True))

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)

class _NodeData(NamedTuple):
    branch_id: str | None
    """None = root."""
    label: str


class BranchManager(Widget):
    """Collapsible left panel showing the branch tree for a simulation.

    Toggle visibility with ``Ctrl+B`` (wired in :class:`~slopr.app.WargameApp`).
    Initially hidden — no branches panel is shown until a :class:`BranchStore`
    is set via :meth:`set_store`.
    """

    DEFAULT_CSS = """
    BranchManager {
        height: 1fr;
        display: none;
        background: $surface;
        border-top: solid $surface-lighten-2;
        padding: 0 1;
        layout: vertical;
    }
    BranchManager.--visible {
        display: block;
    }
    BranchManager .panel-title {
        text-style: bold;
        color: $text-muted;
        height: 1;
        padding: 0 0 0 1;
        margin-bottom: 1;
    }
    BranchManager Tree {
        width: 1fr;
        height: 1fr;
        background: $surface;
    }
    BranchManager #branch-btn-row {
        height: 3;
        align: left middle;
        border-top: solid $surface-lighten-2;
        padding: 0 0;
    }
    BranchManager #branch-btn-row Button {
        margin: 0 1 0 0;
        min-width: 9;
        height: 1;
    }
    """

    def __init__(self, id: str | None = None, classes: str | None = None) -> None:
        super().__init__(id=id, classes=classes)
        self._store: BranchStore | None = None
        self._selected_branch_id: str | None = None
        self._is_root_selected: bool = True

    def compose(self) -> ComposeResult:
        yield Static("Branches", classes="panel-title")
        yield Tree[_NodeData]("(no file)", id="branch-tree")
        with Horizontal(id="branch-btn-row"):
            yield Button("Spawn",  id="btn-spawn",  variant="primary", disabled=True)
            yield Button("Edit",   id="btn-edit",   disabled=True)
            yield Button("Delete", id="btn-delete", variant="error",   disabled=True)

    def set_store(self, store: BranchStore) -> None:
        """Attach a :class:`BranchStore` and render the branch tree."""
        self._store = store
        self.refresh_branches()

    def refresh_branches(self, store: BranchStore | None = None) -> None:
        """Re-render the branch tree from the current (or given) store."""
        if store is not None:
            self._store = store
        if self._store is None:
            return

        tree = self.query_one("#branch-tree", Tree)
        tree.clear()

        root_store = self._store.get_store(None)
        turns = root_store.get_turn_numbers()
        last_turn = turns[-1] if turns else 0
        root_label = (
            f"[dim]T0–T{last_turn}[/dim]  {self._store.manifest.root_file}"
            f"  [{root_store.event_count()} ev]"
        )
        root_node = tree.root
        root_node.set_label(root_label)
        root_node.data = _NodeData(branch_id=None, label=root_label)
        root_node.expand()

        self._populate_branch_nodes(root_node, parent_branch_id=None)

    _STATUS_COLOR: dict[str, str] = {
        "pending":  "dim",
        "running":  "yellow",
        "complete": "green",
        "failed":   "red",
    }

    def _populate_branch_nodes(
        self, parent_node: TreeNode[_NodeData], parent_branch_id: str | None
    ) -> None:
        if self._store is None:
            return
        for entry in self._store.children_of(parent_branch_id):
            branch_store = self._store.get_store(entry.id)
            status_val = entry.sim_status.value
            sc = self._STATUS_COLOR.get(status_val, "dim")
            label = (
                f"[{sc}]T{entry.fork_turn}[/{sc}]  [bold]{entry.label}[/bold]\n"
                f"  [{sc}]{status_val}[/{sc}]  ·  {branch_store.event_count()} ev"
            )
            if entry.annotation:
                label += f"\n  [dim]{entry.annotation[:50]}[/dim]"
            node = parent_node.add(label, data=_NodeData(branch_id=entry.id, label=entry.label))
            self._populate_branch_nodes(node, entry.id)

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        if event.node.data is None:
            return
        data: _NodeData = event.node.data
        self._selected_branch_id = data.branch_id
        self._is_root_selected = data.branch_id is None

        self.query_one("#btn-spawn",  Button).disabled = False
        self.query_one("#btn-edit",   Button).disabled = self._is_root_selected
        self.query_one("#btn-delete", Button).disabled = self._is_root_selected

        self.post_message(BranchActivated(data.branch_id))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-spawn":
            self._open_spawn_modal()
        elif event.button.id == "btn-edit":
            self._open_edit_modal()
        elif event.button.id == "btn-delete":
            self._confirm_delete()

    def _open_spawn_modal(self) -> None:
        def _on_spawn(config: SpawnConfig | None) -> None:
            if config is None or self._selected_branch_id is None:
                return
            self.post_message(
                BranchSimRequested(
                    branch_id=self._selected_branch_id,
                    sim_kwargs={
                        "model_a": config.model_a,
                        "model_b": config.model_b,
                        "turns":   config.turns,
                    },
                )
            )

        self.app.push_screen(SpawnSimModal(), _on_spawn)

    def _open_edit_modal(self) -> None:
        if self._selected_branch_id is None or self._is_root_selected or self._store is None:
            return
        try:
            entry = self._store.get_entry(self._selected_branch_id)
        except KeyError:
            return

        def _on_edit(result: EditBranchResult | None) -> None:
            if result is None or self._selected_branch_id is None:
                return
            self.post_message(
                BranchEdited(
                    branch_id=self._selected_branch_id,
                    label=result.label,
                    annotation=result.annotation,
                    reset_to_fork=result.reset_to_fork,
                    event_title=result.event_title,
                    event_body=result.event_body,
                )
            )

        self.app.push_screen(EditBranchModal(entry), _on_edit)

    def _confirm_delete(self) -> None:
        if self._selected_branch_id is None or self._is_root_selected:
            return
        # For simplicity, post delete immediately — a future version could add
        # a confirmation modal.
        self.post_message(BranchDeleted(self._selected_branch_id))
