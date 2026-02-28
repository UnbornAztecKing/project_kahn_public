"""Provider configuration pane.

Displays the two fixed model providers (Anthropic, Ollama) in a DataTable and
lets the user edit per-provider settings (model, max_tokens, temperature,
thinking) via an inline edit panel.  Changes are persisted through
:class:`~slopr.provider_config.ProviderConfigStore`.

Layout::

    ┌─ ProviderConfigPane ──────────────────────────────────────────────┐
    │ DataTable (height: 6)                                              │
    │  cols: ● | Provider | Endpoint | Model | Tokens | Temp | Thinking  │
    ├───────────────────────────────────────────────────────────────────│
    │ VerticalScroll (1fr) — edit panel for selected row               │
    │  ── Anthropic ───────────────────                                 │
    │  Endpoint: https://api.anthropic.com/v1                           │
    │  Model:     [claude-sonnet-4-6______________]                     │
    │  Max Tokens [1024]   Temperature [1.0]                           │
    │  Thinking   [None ▼]   (hidden for Ollama)                       │
    │  [Set as Active Provider]                                         │
    ├───────────────────────────────────────────────────────────────────│
    │ Button row (height: 3): [Save]  [Reset to Default]                │
    └───────────────────────────────────────────────────────────────────┘

Posts :class:`ProviderConfigChanged` when config is saved or the active
provider changes, so :class:`~slopr.app.WargameApp` can update its
``_analysis_model`` reference.
"""

from __future__ import annotations

from typing import Any

from rich.text import Text

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Button, DataTable, Input, Select, Static

from slopr.provider_config import PROVIDERS, THINKING_OPTIONS, ProviderConfigStore


# ── Colours ───────────────────────────────────────────────────────────────────

_C_ACTIVE   = "#4caf50"
_C_INACTIVE = "#546e7a"
_C_LABEL    = "#aaaaaa"
_C_MODEL    = "#7986cb"
_C_ENDPOINT = "#546e7a"
_C_HEADER   = "#546e7a"


# ── Message ───────────────────────────────────────────────────────────────────


class ProviderConfigChanged(Message):
    """Posted when the active provider is changed or settings are saved."""

    def __init__(self, store: ProviderConfigStore) -> None:
        super().__init__()
        self.store = store


# ── ProviderConfigPane ────────────────────────────────────────────────────────


class ProviderConfigPane(Widget):
    """Content-area pane for configuring model provider settings."""

    DEFAULT_CSS = """
    ProviderConfigPane {
        layout: vertical;
        height: 1fr;
    }
    ProviderConfigPane DataTable {
        height: 6;
        border-bottom: solid $surface-lighten-2;
    }
    ProviderConfigPane #provider-edit-scroll {
        height: 1fr;
        border-bottom: solid $surface-lighten-2;
        padding: 0 1;
    }
    ProviderConfigPane #provider-edit-empty {
        color: $text-disabled;
        margin: 1 1;
    }
    ProviderConfigPane #provider-btn-row {
        height: 3;
        align: left middle;
        padding: 0 1;
    }
    ProviderConfigPane #provider-btn-row Button {
        margin: 0 1 0 0;
    }
    ProviderConfigPane .cfg-section-header {
        color: $text-muted;
        text-style: bold;
        height: 1;
        background: $surface;
        margin: 1 0 0 0;
    }
    ProviderConfigPane .cfg-label {
        color: $text-muted;
        height: 1;
        margin-top: 1;
    }
    ProviderConfigPane .cfg-endpoint-label {
        color: $text-disabled;
        height: 1;
    }
    ProviderConfigPane .cfg-pair {
        layout: horizontal;
        height: 5;
        margin-bottom: 1;
    }
    ProviderConfigPane .cfg-half {
        width: 1fr;
        height: 5;
        margin-right: 2;
    }
    ProviderConfigPane #btn-set-active {
        margin-top: 1;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._store: ProviderConfigStore | None = None
        self._selected_provider: str | None = None

    def set_store(self, store: ProviderConfigStore) -> None:
        """Wire in a :class:`ProviderConfigStore`; must be called before first use."""
        self._store = store
        try:
            self._populate_table()
        except Exception:
            pass  # widget not yet mounted

    def compose(self) -> ComposeResult:
        # ── Provider table ────────────────────────────────────────────────
        tbl: DataTable[str] = DataTable(id="provider-table", cursor_type="row")
        tbl.add_column("●",        key="active",   width=2)
        tbl.add_column("Provider", key="label",    width=12)
        tbl.add_column("Endpoint", key="endpoint", width=32)
        tbl.add_column("Model",    key="model",    width=26)
        tbl.add_column("Tokens",   key="tokens",   width=7)
        tbl.add_column("Temp",     key="temp",     width=5)
        tbl.add_column("Thinking", key="thinking", width=10)
        yield tbl

        # ── Edit panel (shown when a row is selected) ─────────────────────
        with VerticalScroll(id="provider-edit-scroll"):
            yield Static("", id="provider-name-label", classes="cfg-section-header")
            yield Static("", id="provider-endpoint-label", classes="cfg-endpoint-label")

            yield Static("Model", classes="cfg-label")
            yield Input("", placeholder="e.g. claude-sonnet-4-6", id="cfg-model")

            with Horizontal(classes="cfg-pair"):
                with Vertical(classes="cfg-half"):
                    yield Static("Max Tokens", classes="cfg-label")
                    yield Input("", placeholder="1024", id="cfg-max-tokens")
                with Vertical(classes="cfg-half"):
                    yield Static("Temperature  (0.0 – 2.0)", classes="cfg-label")
                    yield Input("", placeholder="1.0", id="cfg-temperature")

            yield Static("Thinking", classes="cfg-label", id="cfg-thinking-label")
            yield Select(
                THINKING_OPTIONS,
                id="cfg-thinking",
                value="none",
            )

            yield Button(
                "Set as Active Provider",
                id="btn-set-active",
                variant="primary",
            )

        yield Static("Select a provider row to configure.", id="provider-edit-empty")

        # ── Button row ────────────────────────────────────────────────────
        with Horizontal(id="provider-btn-row"):
            yield Button("Save", id="btn-cfg-save", variant="success", disabled=True)
            yield Button("Reset to Default", id="btn-cfg-reset", variant="default", disabled=True)

    def on_mount(self) -> None:
        self._populate_table()
        self.query_one("#provider-edit-scroll", VerticalScroll).display = False

    # ── Public API ────────────────────────────────────────────────────────

    def refresh_providers(self) -> None:
        """Re-populate the DataTable from the current store state."""
        self._populate_table()
        if self._selected_provider is not None:
            self._show_edit(self._selected_provider)

    # ── Internal ──────────────────────────────────────────────────────────

    def _populate_table(self) -> None:
        tbl = self.query_one("#provider-table", DataTable)
        tbl.clear()
        if self._store is None:
            return
        for p in PROVIDERS:
            cfg = self._store.get(p["id"])
            is_active = self._store.active_provider == p["id"]
            tbl.add_row(
                Text("●", style=_C_ACTIVE) if is_active else Text("○", style=_C_INACTIVE),
                p["label"],
                Text(p["endpoint"], style=_C_ENDPOINT),
                Text(cfg.model, style=_C_MODEL),
                Text(str(cfg.max_tokens), style=_C_LABEL),
                Text(str(cfg.temperature), style=_C_LABEL),
                Text(cfg.thinking if p["id"] == "anthropic" else "—", style=_C_LABEL),
                key=p["id"],
            )

    def _show_edit(self, provider_id: str) -> None:
        if self._store is None:
            return
        p_info = next((p for p in PROVIDERS if p["id"] == provider_id), None)
        if p_info is None:
            return
        cfg = self._store.get(provider_id)

        scroll = self.query_one("#provider-edit-scroll", VerticalScroll)
        empty  = self.query_one("#provider-edit-empty", Static)
        scroll.display = True
        empty.display  = False

        # Static metadata
        self.query_one("#provider-name-label", Static).update(
            f"[bold {_C_HEADER}]── {p_info['label']} {'─' * 48}[/]"
        )
        self.query_one("#provider-endpoint-label", Static).update(
            f"Endpoint: {p_info['endpoint']}"
        )

        # Editable fields
        self.query_one("#cfg-model", Input).value        = cfg.model
        self.query_one("#cfg-max-tokens", Input).value   = str(cfg.max_tokens)
        self.query_one("#cfg-temperature", Input).value  = str(cfg.temperature)

        # Thinking — only meaningful for Anthropic
        thinking_label  = self.query_one("#cfg-thinking-label", Static)
        thinking_select = self.query_one("#cfg-thinking", Select)
        if provider_id == "anthropic":
            thinking_label.display  = True
            thinking_select.display = True
            thinking_select.value   = cfg.thinking
        else:
            thinking_label.display  = False
            thinking_select.display = False

        # Active-state button
        is_active = self._store.active_provider == provider_id
        btn = self.query_one("#btn-set-active", Button)
        btn.label    = "✓  Active Provider" if is_active else "Set as Active Provider"
        btn.disabled = is_active

        # Enable action buttons
        self.query_one("#btn-cfg-save",  Button).disabled = False
        self.query_one("#btn-cfg-reset", Button).disabled = False

    # ── Event handlers ────────────────────────────────────────────────────

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id != "provider-table":
            return
        if event.row_key is None:
            return
        provider_id = str(event.row_key.value)
        self._selected_provider = provider_id
        self._show_edit(provider_id)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cfg-save":
            self._save_current()
        elif event.button.id == "btn-cfg-reset":
            self._reset_current()
        elif event.button.id == "btn-set-active":
            self._set_active()

    def _save_current(self) -> None:
        if self._store is None or self._selected_provider is None:
            return

        model       = self.query_one("#cfg-model", Input).value.strip()
        max_tok_str = self.query_one("#cfg-max-tokens", Input).value.strip()
        temp_str    = self.query_one("#cfg-temperature", Input).value.strip()

        try:
            max_tokens = int(max_tok_str)
            if max_tokens < 1:
                raise ValueError
        except ValueError:
            self.notify("Max Tokens must be a positive integer.", severity="error", timeout=5)
            return

        try:
            temperature = float(temp_str)
            if not (0.0 <= temperature <= 2.0):
                raise ValueError
        except ValueError:
            self.notify("Temperature must be a number between 0.0 and 2.0.", severity="error", timeout=5)
            return

        thinking_sel = self.query_one("#cfg-thinking", Select)
        thinking = (
            str(thinking_sel.value)
            if thinking_sel.value is not Select.BLANK
            else "none"
        )

        self._store.update(
            self._selected_provider,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            thinking=thinking,
        )
        self._populate_table()
        self.post_message(ProviderConfigChanged(self._store))
        self.notify("Provider config saved.", timeout=2)

    def _reset_current(self) -> None:
        if self._store is None or self._selected_provider is None:
            return
        self._store.reset(self._selected_provider)
        self._show_edit(self._selected_provider)
        self._populate_table()
        self.post_message(ProviderConfigChanged(self._store))
        self.notify("Provider config reset to defaults.", timeout=2)

    def _set_active(self) -> None:
        if self._store is None or self._selected_provider is None:
            return
        self._store.active_provider = self._selected_provider
        self._populate_table()
        self._show_edit(self._selected_provider)
        self.post_message(ProviderConfigChanged(self._store))
        p_label = next(
            (p["label"] for p in PROVIDERS if p["id"] == self._selected_provider),
            self._selected_provider,
        )
        self.notify(f"Active provider: {p_label}", timeout=2)
