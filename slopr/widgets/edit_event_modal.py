"""Edit event modal — double-click an event card to edit and create a branch fork."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import NamedTuple

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static, TextArea

from slopr.models import EventSource, GameEvent


class EditResult(NamedTuple):
    """Returned by the modal on successful commit."""

    edited_event: GameEvent
    """A new GameEvent with source=HUMAN, parent_id=original.id."""
    branch_label: str
    """Required branch label for the fork."""
    branch_annotation: str
    """Optional free-text annotation."""
    peer_edited_event: GameEvent | None = None
    """If the fork came from an event group, the counterparty's edited event."""


class EditEventModal(ModalScreen[EditResult | None]):
    """Modal for editing an event and labeling the resulting branch fork.

    Double-clicking an EventCard posts :class:`EventCardDoubleClicked` which
    the app handles by pushing this screen.  On commit, the screen dismisses
    with an :class:`EditResult`; on cancel or Escape it dismisses with ``None``.

    When *peer_event* is supplied (e.g. the counterparty's decision in the same
    phase), the modal exposes a second editor so both A and B events can be
    adjusted before the branch is created.
    """

    BINDINGS = [Binding("escape", "dismiss_modal", "Cancel", show=True)]

    DEFAULT_CSS = """
    EditEventModal {
        align: center middle;
    }

    #edit-container {
        width: 80%;
        max-width: 110;
        height: 90%;
        background: $surface;
        border: thick $warning;
        padding: 1 2;
    }

    #edit-header {
        color: $text-muted;
        height: 2;
        margin-bottom: 1;
    }

    #editors-area {
        height: 1fr;
        margin-bottom: 1;
    }

    .section-label {
        color: $warning;
        text-style: bold;
        height: 1;
        margin-top: 1;
    }

    .field-label {
        color: $text-muted;
        height: 1;
    }

    .title-input {
        margin-bottom: 1;
    }

    .body-input {
        height: 7;
        margin-bottom: 1;
    }

    .struct-data-label {
        color: $text-muted;
        height: 1;
        margin-top: 1;
    }

    .struct-data-input {
        height: 8;
        margin-bottom: 1;
    }

    #branch-label-hint {
        color: $warning;
        height: 1;
        margin-top: 1;
    }

    #branch-label {
        border: solid $warning;
        margin-bottom: 1;
    }

    #branch-annotation-hint {
        color: $text-muted;
        height: 1;
    }

    #branch-annotation {
        height: 4;
        margin-bottom: 1;
    }

    #button-row {
        height: 3;
        align: right middle;
    }

    #btn-commit {
        margin-right: 1;
    }
    """

    def __init__(self, event: GameEvent, peer_event: GameEvent | None = None) -> None:
        super().__init__()
        self._original = event
        self._peer = peer_event

    def compose(self) -> ComposeResult:
        evt = self._original
        header = (
            f"Turn {evt.turn_number}  ·  {evt.phase or '—'}  ·  "
            f"[{evt.source.value}]  ·  {evt.event_type.value}"
        )
        with Vertical(id="edit-container"):
            yield Static(header, id="edit-header")
            with VerticalScroll(id="editors-area"):
                # ── Primary event editor ──────────────────────────────────
                if self._peer is not None:
                    primary_name = evt.source_detail or "State A"
                    yield Static(
                        f"── {primary_name} ───────────────────",
                        classes="section-label",
                        id="primary-section-label",
                    )
                yield Static("Title", classes="field-label")
                yield Input(value=evt.title, id="title-input", classes="title-input")
                yield Static("Body", classes="field-label")
                yield TextArea(evt.body, id="body-input", classes="body-input")
                yield Static(
                    "Structured Data (JSON — add/edit fields below)",
                    classes="struct-data-label",
                )
                yield TextArea(
                    json.dumps(evt.structured_data or {}, indent=2),
                    id="struct-data-input",
                    classes="struct-data-input",
                )

                # ── Peer event editor (if provided) ───────────────────────
                if self._peer is not None:
                    peer = self._peer
                    peer_name = peer.source_detail or "State B"
                    yield Static(
                        f"── {peer_name} ───────────────────",
                        classes="section-label",
                        id="peer-section-label",
                    )
                    yield Static("Title", classes="field-label")
                    yield Input(
                        value=peer.title,
                        id="peer-title-input",
                        classes="title-input",
                    )
                    yield Static("Body", classes="field-label")
                    yield TextArea(peer.body, id="peer-body-input", classes="body-input")
                    yield Static(
                        "Structured Data (JSON — add/edit fields below)",
                        classes="struct-data-label",
                    )
                    yield TextArea(
                        json.dumps(peer.structured_data or {}, indent=2),
                        id="peer-struct-data-input",
                        classes="struct-data-input",
                    )

            # ── Branch metadata ───────────────────────────────────────────
            yield Static("Branch label (required)", id="branch-label-hint")
            yield Input(placeholder="Describe this branch...", id="branch-label")
            yield Static("Annotation (optional)", id="branch-annotation-hint")
            yield TextArea("", id="branch-annotation")
            with Horizontal(id="button-row"):
                yield Button("Commit Edit", id="btn-commit", variant="warning", disabled=True)
                yield Button("Cancel", id="btn-cancel", variant="default")

    def on_mount(self) -> None:
        self.query_one("#branch-label", Input).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "branch-label":
            has_label = bool(event.value.strip())
            self.query_one("#btn-commit", Button).disabled = not has_label

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-commit":
            self._commit()

    def _commit(self) -> None:
        branch_label = self.query_one("#branch-label", Input).value.strip()
        if not branch_label:
            return

        new_title = self.query_one("#title-input", Input).value
        new_body = self.query_one("#body-input", TextArea).text
        annotation = self.query_one("#branch-annotation", TextArea).text

        # Parse the structured_data JSON text.
        sd_text = self.query_one("#struct-data-input", TextArea).text.strip()
        try:
            new_structured_data: dict | None = json.loads(sd_text) if sd_text else None
        except json.JSONDecodeError as exc:
            self.notify(f"Structured Data JSON error: {exc}", severity="error", timeout=6)
            return

        # Build the primary edited event.
        edited = GameEvent(
            id=str(uuid.uuid4()),
            parent_id=self._original.id,
            sequence_number=self._original.sequence_number,
            turn_number=self._original.turn_number,
            phase=self._original.phase,
            timestamp=datetime.now(timezone.utc),
            event_type=self._original.event_type,
            source=EventSource.HUMAN,
            source_detail="analyst",
            title=new_title,
            body=new_body,
            structured_data=new_structured_data,
        )

        # Build the peer edited event (if a peer was provided).
        peer_edited: GameEvent | None = None
        if self._peer is not None:
            peer_inputs = self.query("#peer-title-input")
            peer_bodies = self.query("#peer-body-input")
            if peer_inputs and peer_bodies:
                peer_title = peer_inputs.first(Input).value
                peer_body = peer_bodies.first(TextArea).text
                peer_sd_text = ""
                peer_sd_areas = self.query("#peer-struct-data-input")
                if peer_sd_areas:
                    peer_sd_text = peer_sd_areas.first(TextArea).text.strip()
                try:
                    peer_sd: dict | None = json.loads(peer_sd_text) if peer_sd_text else None
                except json.JSONDecodeError as exc:
                    self.notify(
                        f"Peer Structured Data JSON error: {exc}", severity="error", timeout=6
                    )
                    return
                peer_edited = GameEvent(
                    id=str(uuid.uuid4()),
                    parent_id=self._peer.id,
                    sequence_number=self._peer.sequence_number,
                    turn_number=self._peer.turn_number,
                    phase=self._peer.phase,
                    timestamp=datetime.now(timezone.utc),
                    event_type=self._peer.event_type,
                    source=EventSource.HUMAN,
                    source_detail="analyst",
                    title=peer_title,
                    body=peer_body,
                    structured_data=peer_sd,
                )

        self.dismiss(EditResult(edited, branch_label, annotation, peer_edited))

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)
