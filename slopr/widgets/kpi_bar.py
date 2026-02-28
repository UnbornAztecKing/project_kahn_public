"""KPI bar — bottom-docked horizontal strip of key performance indicators."""

from __future__ import annotations

from textual.events import Click
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static

from slopr.models import EventType, GameEvent
from slopr.store import EventStore

# ── Threshold helpers ──────────────────────────────────────────────────────


def _territory_class(value: float) -> str:
    if abs(value) >= 3.0:
        return "kpi-critical"
    if abs(value) >= 1.5:
        return "kpi-warning"
    return "kpi-normal"


def _power_class(value: float) -> str:
    if value <= 0.3:
        return "kpi-critical"
    if value <= 0.6:
        return "kpi-warning"
    return "kpi-normal"


def _trend_arrow(current: float, previous: float | None) -> str:
    if previous is None:
        return ""
    diff = current - previous
    if abs(diff) < 0.001:
        return " \u2500"  # ─
    return " \u25b2" if diff > 0 else " \u25bc"  # ▲ / ▼


# ── KPIIndicator ───────────────────────────────────────────────────────────


class KPIIndicator(Widget):
    """Single KPI cell: label, value, and optional trend arrow."""

    def __init__(self, label: str, value: str = "—", css_class: str = "") -> None:
        super().__init__()
        self._label = label
        self._value = value
        if css_class:
            self.add_class(css_class)

    def compose(self):  # type: ignore[override]
        yield Static(self._label, classes="kpi-label")
        yield Static(self._value, classes="kpi-value")

    def update_value(self, value: str, css_class: str = "") -> None:
        self._value = value
        # Update the value static
        try:
            val_widget = self.query_one(".kpi-value", Static)
            val_widget.update(value)
        except Exception:
            pass
        # Update threshold class
        for cls in ("kpi-normal", "kpi-warning", "kpi-critical"):
            self.remove_class(cls)
        if css_class:
            self.add_class(css_class)


# ── KPIBar ─────────────────────────────────────────────────────────────────


class KPIBarClicked(Message):
    """Posted when the user clicks the KPI bar."""

    pass


class KPIBar(Widget):
    """Bottom bar showing key metrics for the current turn."""

    def __init__(self, store: EventStore) -> None:
        super().__init__()
        self._store = store
        self._prev_kpi: dict | None = None
        self._indicators: dict[str, KPIIndicator] = {}
        self._current_turn: int | None = None

    def compose(self):  # type: ignore[override]
        names = [
            ("territory", "Territory"),
            ("a_conv",    "A Conv"),
            ("b_conv",    "B Conv"),
            ("a_nuc",     "A Nuc"),
            ("b_nuc",     "B Nuc"),
            ("a_action",  "A Act"),
            ("b_action",  "B Act"),
            ("gap_a",     "A Gap"),
            ("gap_b",     "B Gap"),
        ]
        for key, label in names:
            ind = KPIIndicator(label)
            self._indicators[key] = ind
            yield ind

    def on_click(self, event: Click) -> None:
        """Open the KPI history panel."""
        self.post_message(KPIBarClicked())

    def _update_kpis(self, turn: int) -> None:
        """Find the KPI_UPDATE event for *turn* and refresh indicators."""
        self._current_turn = turn
        events = self._store.get_events(turn=turn, event_type=EventType.KPI_UPDATE, limit=1)
        if not events:
            return

        kpi = events[0].structured_data
        prev = self._prev_kpi

        # Territory
        tb = kpi.get("territory_balance", 0)
        arrow = _trend_arrow(tb, prev.get("territory_balance") if prev else None)
        self._indicators["territory"].update_value(f"{tb:+.3f}{arrow}", _territory_class(tb))

        # Military power
        for side, prefix in [("a", "A"), ("b", "B")]:
            conv = kpi.get(f"{side}_conventional_power", 0)
            nuc = kpi.get(f"{side}_nuclear_power", 0)
            prev_conv = prev.get(f"{side}_conventional_power") if prev else None
            prev_nuc = prev.get(f"{side}_nuclear_power") if prev else None

            self._indicators[f"{side}_conv"].update_value(
                f"{conv:.1%}{_trend_arrow(conv, prev_conv)}", _power_class(conv)
            )
            self._indicators[f"{side}_nuc"].update_value(
                f"{nuc:.1%}{_trend_arrow(nuc, prev_nuc)}" if nuc else "—",
                _power_class(nuc) if nuc else "",
            )

        # Action values
        a_act = kpi.get("a_action_value", 0)
        b_act = kpi.get("b_action_value", 0)
        self._indicators["a_action"].update_value(str(a_act))
        self._indicators["b_action"].update_value(str(b_act))

        # Signal-action gaps
        gap_a = kpi.get("signal_action_gap_a", 0)
        gap_b = kpi.get("signal_action_gap_b", 0)
        self._indicators["gap_a"].update_value(
            f"{gap_a:+d}" if isinstance(gap_a, int) else str(gap_a)
        )
        self._indicators["gap_b"].update_value(
            f"{gap_b:+d}" if isinstance(gap_b, int) else str(gap_b)
        )

        self._prev_kpi = kpi
