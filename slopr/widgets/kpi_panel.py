"""KPI panel — modal screen showing turn-by-turn KPI history table."""

from __future__ import annotations

from rich.text import Text

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Static

from slopr.models import EventType
from slopr.store import EventStore

# Column colour palette — mirrors wargame.tcss side-a / side-b
_C_TURN = "#aaaaaa"   # muted grey for turn index
_C_NEUT = "#daa520"   # gold for neutral metrics (territory)
_C_A    = "#5b9cf5"   # blue  — State A
_C_B    = "#f55b5b"   # coral — State B


def _t(value: str, color: str) -> Text:
    return Text(value, style=color)


class KPIPanel(ModalScreen[int | None]):
    """Full-screen modal showing KPI values across all turns."""

    BINDINGS = [
        Binding("escape", "dismiss_panel", "Close"),
    ]

    DEFAULT_CSS = """
    KPIPanel {
        align: center middle;
    }
    #kpi-panel-container {
        width: 90%;
        max-width: 120;
        height: 80%;
        background: $surface;
        border: thick $primary;
        padding: 1 2;
    }
    #kpi-panel-title {
        dock: top;
        height: 1;
        text-style: bold;
        color: $text;
        text-align: center;
        margin-bottom: 1;
    }
    #kpi-table {
        height: 1fr;
    }
    #kpi-panel-hint {
        dock: bottom;
        height: 1;
        color: $text-disabled;
        text-align: center;
    }
    """

    def __init__(self, store: EventStore, current_turn: int | None = None) -> None:
        super().__init__()
        self._store = store
        self._current_turn = current_turn

    def compose(self) -> ComposeResult:
        with Vertical(id="kpi-panel-container"):
            yield Static("KPI History", id="kpi-panel-title")
            yield DataTable(id="kpi-table", zebra_stripes=True)
            yield Static("Press Escape to close  |  Enter to jump to turn", id="kpi-panel-hint")

    def on_mount(self) -> None:
        table = self.query_one("#kpi-table", DataTable)
        table.cursor_type = "row"

        table.add_columns(
            _t("Turn",      _C_TURN),
            _t("Territory", _C_NEUT),
            _t("A Conv",    _C_A),
            _t("B Conv",    _C_B),
            _t("A Nuc",     _C_A),
            _t("B Nuc",     _C_B),
            _t("A Act",     _C_A),
            _t("B Act",     _C_B),
            _t("A Gap",     _C_A),
            _t("B Gap",     _C_B),
        )

        turns = self._store.get_turn_numbers()
        target_row = 0
        for i, t in enumerate(turns):
            events = self._store.get_events(turn=t, event_type=EventType.KPI_UPDATE, limit=1)
            if not events:
                continue
            kpi = events[0].structured_data
            tb = kpi.get("territory_balance", 0)
            a_conv = kpi.get("a_conventional_power", 0)
            a_nuc = kpi.get("a_nuclear_power", 0)
            b_conv = kpi.get("b_conventional_power", 0)
            b_nuc = kpi.get("b_nuclear_power", 0)
            a_act = kpi.get("a_action_value", "")
            b_act = kpi.get("b_action_value", "")
            gap_a = kpi.get("signal_action_gap_a", "")
            gap_b = kpi.get("signal_action_gap_b", "")

            table.add_row(
                _t(str(t),                                                         _C_TURN),
                _t(f"{tb:+.3f}",                                                   _C_NEUT),
                _t(f"{a_conv:.1%}" if isinstance(a_conv, float) else str(a_conv),  _C_A),
                _t(f"{b_conv:.1%}" if isinstance(b_conv, float) else str(b_conv),  _C_B),
                _t(f"{a_nuc:.1%}"  if isinstance(a_nuc,  float) else str(a_nuc),   _C_A),
                _t(f"{b_nuc:.1%}"  if isinstance(b_nuc,  float) else str(b_nuc),   _C_B),
                _t(str(a_act),                                                      _C_A),
                _t(str(b_act),                                                      _C_B),
                _t(f"{gap_a:+d}" if isinstance(gap_a, int) else str(gap_a),        _C_A),
                _t(f"{gap_b:+d}" if isinstance(gap_b, int) else str(gap_b),        _C_B),
                key=str(t),
            )
            if t == self._current_turn:
                target_row = i

        if target_row > 0:
            table.move_cursor(row=target_row)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        key = event.row_key
        if key and key.value is not None:
            try:
                turn = int(key.value)
                self.dismiss(turn)
            except ValueError:
                pass

    def action_dismiss_panel(self) -> None:
        self.dismiss(None)
