"""Modal for reviewing AI analysis results and optionally saving as an annotation.

The modal accepts a coroutine (the result of ``analysis.run_command()``)
and shows a spinner while the API call is in flight.  When complete the
result is displayed.  The user can then save it as an ANNOTATION event or
dismiss without saving.

Usage (from app.py)::

    async def _run_analysis(self, command_id: str, event: GameEvent) -> None:
        commands = {c.id: c for c in analysis.COMMANDS}
        command = commands[command_id]
        coro = analysis.run_command(command_id, event, context_events,
                                    model=self._analysis_model)

        def _on_result(text: str | None) -> None:
            if text is not None:
                self._save_annotation(event, command, text)

        self.push_screen(AnalysisModal(command.label, coro), _on_result)
"""

from __future__ import annotations

from typing import Coroutine, Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, LoadingIndicator, Static


class AnalysisModal(ModalScreen[str | None]):
    """Modal that runs an AI analysis coroutine and shows the result.

    Dismissed with the result text if the user saves, or ``None`` to discard.
    """

    BINDINGS = [Binding("escape", "dismiss_modal", "Dismiss")]

    DEFAULT_CSS = """
    AnalysisModal {
        align: center middle;
    }
    #analysis-container {
        width: 72;
        height: auto;
        max-height: 40;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    #analysis-title {
        text-style: bold;
        color: $text-muted;
        height: 1;
        margin-bottom: 1;
    }
    #analysis-body {
        height: auto;
        max-height: 30;
        background: $background;
        padding: 1;
        border: solid $surface-lighten-2;
        scrollbar-size: 1 1;
        overflow-y: auto;
    }
    #analysis-body LoadingIndicator {
        height: 3;
    }
    #analysis-body Static {
        color: $text;
    }
    #analysis-btn-row {
        height: 3;
        align: right middle;
        margin-top: 1;
    }
    #btn-save-annotation {
        margin-right: 1;
    }
    """

    def __init__(
        self,
        command_label: str,
        coro: Coroutine[Any, Any, str],
    ) -> None:
        super().__init__()
        self._command_label = command_label
        self._coro = coro
        self._result: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical(id="analysis-container"):
            yield Static(f"Analysis: {self._command_label}", id="analysis-title")
            with Vertical(id="analysis-body"):
                yield LoadingIndicator()
            with Horizontal(id="analysis-btn-row"):
                yield Button(
                    "Save as annotation",
                    id="btn-save-annotation",
                    variant="primary",
                    disabled=True,
                )
                yield Button("Dismiss", id="btn-dismiss")

    def on_mount(self) -> None:
        self.app.call_later(self._start_analysis)

    async def _start_analysis(self) -> None:
        """Launch the API coroutine and update UI when done."""
        try:
            result = await self._coro
        except Exception as exc:
            result = f"[Error] {exc}"

        self._result = result
        body = self.query_one("#analysis-body", Vertical)
        body.remove_children()
        body.mount(Static(result))

        save_btn = self.query_one("#btn-save-annotation", Button)
        save_btn.disabled = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-dismiss":
            self.dismiss(None)
        elif event.button.id == "btn-save-annotation":
            self.dismiss(self._result)

    def action_dismiss_modal(self) -> None:
        self.dismiss(None)
