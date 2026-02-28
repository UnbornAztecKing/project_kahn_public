"""Content pane — vertical scroll of attributed ``EventCard`` widgets."""

from __future__ import annotations

import json
import re
from typing import Any, NamedTuple

from textual.containers import Horizontal, VerticalScroll
from textual.events import Click, Resize
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Collapsible, Static

from slopr.models import EventSource, EventType, GameEvent
from slopr.store import EventStore
from slopr.widgets.banner import KahnBanner

# ── Constants ──────────────────────────────────────────────────────────────

_BADGES: dict[EventSource, str] = {
    EventSource.SIMULATION: "",
    EventSource.LLM: "LLM",
    EventSource.HUMAN: "EDIT",
    EventSource.SYSTEM: "",
}

_TITLE_CLS: dict[EventType, str] = {
    EventType.PHASE_TRANSITION: "title-phase",
    EventType.LLM_DECISION: "title-phase",
    EventType.STATE_CHANGE: "title-state",
    EventType.KPI_UPDATE: "title-kpi",
    EventType.SITUATION_REPORT: "title-report",
    EventType.GAME_START: "title-game",
    EventType.GAME_END: "title-game",
    EventType.ANNOTATION: "title-phase",  # legacy
    EventType.TAG: "title-phase",
}

_RULE = "\u2500" * 40  # ─
_THIN_RULE = "\u2500" * 60  # ─  (divider between events within a group)
_LC = "#8899aa"  # label color — steel blue-gray

_PHASE_LABELS: dict[str, str] = {
    "reflection": "Reflection",
    "forecast": "Forecast",
    "signal": "Signal",
    "action": "Action",
    "scenario": "Scenario",
    "profiles": "State Profiles",
}

_PHASE_CSS: dict[str, str] = {
    "reflection": "group-reflection",
    "forecast": "group-forecast",
    "signal": "group-signal",
    "action": "group-action",
    "scenario": "group-scenario",
    "profiles": "group-profiles",
    "initialstate": "group-initialstate",
    "parameters": "group-parameters",
}

_SUMMARY_TYPES = {EventType.STATE_CHANGE, EventType.KPI_UPDATE, EventType.SITUATION_REPORT}

# ── Text-format config ────────────────────────────────────────────────────────

_double_newlines: bool = True
_wrap_indent: int = 0


def configure_text_format(double_newlines: bool = True, wrap_indent: int = 0) -> None:
    """Configure how prose text is displayed throughout the event cards."""
    global _double_newlines, _wrap_indent
    _double_newlines = double_newlines
    _wrap_indent = wrap_indent


def _fmt_text(text: str) -> str:
    """Apply text-format options to a prose string (body text, scenario fields)."""
    if not text:
        return text
    sep = "\n\n" if _double_newlines else "\n"
    if _wrap_indent > 0:
        sep += " " * _wrap_indent
    return re.sub(r'\n+', sep, text)


# Priority for ordering events within the end-state group:
# situation report first, then state change, then KPI update.
_SIM_ORDER: dict[EventType, int] = {
    EventType.SITUATION_REPORT: 0,
    EventType.STATE_CHANGE: 1,
    EventType.KPI_UPDATE: 2,
}

# Regex to parse the situation report body.
_SITREP_RE = re.compile(r"A:\s*(.+?),\s*B:\s*(.+?)\.\s*Territory:\s*(.+)")


# ── Event grouping ────────────────────────────────────────────────────────


class EventGroup(NamedTuple):
    """A labeled group of events to render inside a single bordered container."""

    label: str
    css_class: str
    events: list[GameEvent]


def _group_events(events: list[GameEvent]) -> list[EventGroup]:
    """Segment a flat event list into phase groups.

    PHASE_TRANSITION events are consumed as group delimiters — they become the
    group label and are *not* included in the event list.  Trailing system
    events (STATE_CHANGE, KPI_UPDATE, SITUATION_REPORT) with ``phase=""`` are
    collected into an "End State" group with SITUATION_REPORT ordered first.
    GAME_END events are placed in a separate "Game Over" group.
    """
    groups: list[EventGroup] = []
    current_label: str | None = None
    current_cls: str = ""
    current_events: list[GameEvent] = []

    def _flush() -> None:
        if current_events:
            groups.append(EventGroup(current_label or "Events", current_cls, list(current_events)))

    sim_events: list[GameEvent] = []
    game_end_events: list[GameEvent] = []

    for evt in events:
        # Phase transition → flush and start a new phase group
        if evt.event_type == EventType.PHASE_TRANSITION:
            _flush()
            phase = evt.phase
            current_label = _PHASE_LABELS.get(phase, phase.title() or "Phase")
            current_cls = _PHASE_CSS.get(phase, "group-phase")
            current_events = []
            continue

        # Game start → standalone group
        if evt.event_type == EventType.GAME_START:
            _flush()
            current_events = []
            current_label = None
            groups.append(EventGroup("Parameters", "group-parameters", [evt]))
            continue

        # Game end → defer until after end-state group
        if evt.event_type == EventType.GAME_END:
            game_end_events.append(evt)
            continue

        # Summary-type events (phase="") → collect for "End State" group
        if evt.event_type in _SUMMARY_TYPES and not evt.phase:
            if current_label != "End State":
                _flush()
                current_label = "End State"
                current_cls = "group-endstate"
                current_events = []
            sim_events.append(evt)
            continue

        # Everything else → current group
        current_events.append(evt)

    # Reorder end-state events: SITUATION_REPORT first, then STATE_CHANGE, then KPI_UPDATE
    if sim_events:
        sim_events.sort(key=lambda e: _SIM_ORDER.get(e.event_type, 99))
        if current_label == "End State":
            current_events = sim_events
        else:
            _flush()
            current_label = "End State"
            current_cls = "group-endstate"
            current_events = sim_events

    _flush()

    # Game Over group(s) always come last (after End State)
    for ge in game_end_events:
        groups.append(EventGroup("Game Over", "group-gameover", [ge]))

    return groups


# ── Helpers ────────────────────────────────────────────────────────────────


def _L(label: str, width: int = 13) -> str:
    """Wrap *label* in Rich markup with the field-label color, padded to *width*."""
    padded = f"{label:<{width}}"
    return f"[{_LC}]{padded}[/]"


def _badge_text(event: GameEvent) -> str:
    prefix = _BADGES.get(event.source, "")
    detail = f" {event.source_detail}" if event.source_detail else ""
    return f"{prefix}{detail}" if prefix else ""


def _side_cls(side: str) -> str:
    if side.upper() == "A":
        return "side-a"
    if side.upper() == "B":
        return "side-b"
    return ""


def _fmt_val(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:.4f}"
    if isinstance(v, (dict, list)):
        return json.dumps(v, indent=2)
    return str(v)


# ── EventCardClicked message ──────────────────────────────────────────────


class EventCardClicked(Message):
    """Posted when an EventCard is clicked. Bubbles up to the app."""

    def __init__(self, event_id: str, turn_number: int) -> None:
        super().__init__()
        self.event_id = event_id
        self.turn_number = turn_number


class EventCardDoubleClicked(Message):
    """Posted when an EventCard is double-clicked. Bubbles up to the app."""

    def __init__(self, event: GameEvent) -> None:
        super().__init__()
        self.event = event


class EventCardRightClicked(Message):
    """Posted when an EventCard is right-clicked. Bubbles up to the app."""

    def __init__(self, event: GameEvent, screen_x: int, screen_y: int) -> None:
        super().__init__()
        self.event = event
        self.screen_x = screen_x
        self.screen_y = screen_y


# ── TagCard ────────────────────────────────────────────────────────────────


class TagCard(Widget):
    """Renders a single tag event in a titled pipe-box border.

    Displayed immediately after the parent :class:`EventCard` in the content
    pane.  The title appears in the top border: ``┌ label ───┐``.

    Cards start collapsed (border + label only).  Click to expand the full
    body and metadata.  Pass ``split=True`` when embedding inside the split-view
    aligned grid to suppress the sequential-mode left indent.
    """

    DEFAULT_CSS = """
    TagCard {
        layout: vertical;
        height: auto;
        margin: 0 1 1 4;
        padding: 0 1;
        border: solid #daa520;
    }
    TagCard.tag-split {
        margin: 1 1 0 0;
        width: 1fr;
    }
    TagCard .tag-body {
        color: $text;
    }
    TagCard .tag-skill-id {
        color: #8c7a3a;
        height: 1;
    }
    TagCard .tag-meta {
        color: $text-disabled;
        height: 1;
        margin-top: 1;
    }
    """

    def __init__(
        self,
        annotation: "GameEvent",
        last: bool = False,
        split: bool = False,
    ) -> None:
        super().__init__()
        self._tag = annotation
        self._last = last
        self._collapsed = True
        if split:
            self.add_class("tag-split")

    def on_mount(self) -> None:
        # Strip wrapping brackets from the title if present (e.g. "[Analyze Action]")
        raw = self._tag.title or "tag"
        label = raw.strip("[]")
        # Prepend skill glyph if one is stored in structured_data
        glyph = (self._tag.structured_data or {}).get("skill_glyph", "")
        self.border_title = f"{glyph} {label}" if glyph else label
        self._apply_collapse()

    def _apply_collapse(self) -> None:
        """Show or hide body content based on self._collapsed."""
        visible = not self._collapsed
        for cls in (".tag-skill-id", ".tag-body", ".tag-meta"):
            try:
                self.query_one(cls, Static).display = visible
            except Exception:
                pass

    def on_click(self, event: Click) -> None:  # type: ignore[override]
        self._collapsed = not self._collapsed
        self._apply_collapse()
        event.stop()

    def compose(self):  # type: ignore[override]
        sd = self._tag.structured_data or {}
        task_label = sd.get("task_label", "")
        model      = sd.get("model", "")
        in_tok     = sd.get("input_tokens", 0)
        out_tok    = sd.get("output_tokens", 0)
        task_id    = str(sd.get("task_id", ""))[:8]

        if task_label:
            suffix = f"  [{task_id}]" if task_id else ""
            yield Static(f"[dim]{task_label}{suffix}[/]", classes="tag-skill-id")
        if self._tag.body:
            yield Static(self._tag.body, classes="tag-body")
        if model:
            meta = f"[dim]{model}  {in_tok}↑ {out_tok}↓[/]"
            yield Static(meta, classes="tag-meta")


# Backward-compat alias so old imports still work
AnnotationCard = TagCard


# ── EventCard ──────────────────────────────────────────────────────────────


class EventCard(Widget):
    """Renders a single event with type-colored titles and side-colored fields."""

    can_focus = True

    def __init__(
        self, event: GameEvent, annotations: "list[GameEvent] | None" = None
    ) -> None:
        super().__init__()
        self._event = event
        self._annotations: list[GameEvent] = annotations or []
        self.add_class(f"source-{event.source.value}")

    def on_click(self, event: Click) -> None:
        """Post clicked, double-clicked, or right-clicked message."""
        if event.button == 3:
            self.post_message(
                EventCardRightClicked(self._event, event.screen_x, event.screen_y)
            )
        elif event.chain == 2 and self._event.event_type == EventType.LLM_DECISION:
            self.post_message(EventCardDoubleClicked(self._event))
        else:
            self.post_message(
                EventCardClicked(
                    event_id=self._event.id,
                    turn_number=self._event.turn_number,
                )
            )

    def compose(self):  # type: ignore[override]
        evt = self._event

        # ── Title row ─────────────────────────────────────────────────
        title_cls = _TITLE_CLS.get(evt.event_type, "")
        badge = _badge_text(evt)
        if badge:
            yield Static(badge, classes="source-badge")
        yield Static(evt.title, classes=f"event-title {title_cls}")

        # ── Metadata ──────────────────────────────────────────────────
        meta_parts = [
            f"seq={evt.sequence_number}",
            f"type={evt.event_type.value}",
        ]
        if evt.phase:
            meta_parts.append(f"phase={evt.phase}")
        meta_parts.append(f"time={evt.timestamp.strftime('%H:%M:%S')}")
        if evt.parent_id:
            meta_parts.append(f"parent={evt.parent_id[:8]}")
        meta_parts.append(f"hash={evt.content_hash[:8]}")
        yield Static("  ".join(meta_parts), classes="event-meta")

        # ── Type-specific rendering ───────────────────────────────────
        rendered_keys: set[str] = set()
        if evt.event_type == EventType.LLM_DECISION:
            rendered_keys = yield from self._render_llm_decision(evt)
        elif evt.event_type == EventType.STATE_CHANGE:
            rendered_keys = yield from self._render_state_change(evt)
        elif evt.event_type == EventType.KPI_UPDATE:
            rendered_keys = yield from self._render_kpi_update(evt)
        elif evt.event_type == EventType.SITUATION_REPORT:
            rendered_keys = yield from self._render_situation_report(evt)
        elif evt.event_type == EventType.GAME_START:
            rendered_keys = yield from self._render_game_start(evt)
        elif evt.event_type == EventType.GAME_END:
            rendered_keys = yield from self._render_game_end(evt)

        # ── Body text (if not already consumed) ───────────────────────
        if evt.body and evt.event_type != EventType.SITUATION_REPORT:
            yield Static(_fmt_text(evt.body), classes="event-body")

        # ── Remaining structured_data ─────────────────────────────────
        remaining = {
            k: v
            for k, v in evt.structured_data.items()
            if k not in rendered_keys and v is not None and v != ""
        }
        if remaining:
            yield Static("data", classes="event-data-header")
            for k, v in remaining.items():
                formatted = _fmt_val(v)
                if "\n" in formatted:
                    yield Static(f"[{_LC}]{k}:[/]", classes="event-data-key")
                    for line in formatted.splitlines():
                        yield Static(line, classes="event-data-val")
                else:
                    yield Static(f"[{_LC}]{k}:[/] {formatted}", classes="event-data-kv")

        # Annotations are rendered as AnnotationCard widgets after this EventCard
        # by the parent container (_build_sequential_children / _SplitPair).

    # ── LLM Decision ──────────────────────────────────────────────────

    def _render_llm_decision(self, evt: GameEvent):
        sd = evt.structured_data
        phase = evt.phase
        side = sd.get("side", "")
        scls = _side_cls(side)
        rendered: set[str] = {"side", "phase"}

        if phase == "action":
            rung = sd.get("action_rung", "")
            val = sd.get("action_value", "")
            yield Static(f"{_L('Action:')}{rung} ({val})", classes=f"event-body {scls}")
            rendered |= {"action_rung", "action_value"}
            yield Static(f"{_L('accident:')}{sd.get('accident_occurred', '')}", classes="event-body event-accident")
            rendered.add("accident_occurred")
            cs = sd.get("consistency_statement", "")
            yield Static(f"{_L('Consistency:')}{cs}", classes=f"event-body {scls}")
            rendered.add("consistency_statement")

        elif phase == "forecast":
            pred = sd.get("predicted_opponent_action", "")
            conf = sd.get("predictive_confidence", "")
            risk = sd.get("miscalculation_risk", "")
            yield Static(
                f"{_L('Prediction:')}{pred}  (confidence: {conf})", classes=f"event-body {scls}"
            )
            rendered |= {"predicted_opponent_action", "predictive_confidence"}
            yield Static(f"{_L('Miscalc:')}{risk}", classes=f"event-body {scls}")
            rendered.add("miscalculation_risk")

        elif phase == "signal":
            sig = sd.get("immediate_signal", "")
            val = sd.get("immediate_signal_value", "")
            yield Static(f"{_L('Signal:')}{sig} ({val})", classes=f"event-body {scls}")
            rendered |= {"immediate_signal", "immediate_signal_value"}
            cond = sd.get("conditional_signal", "")
            yield Static(f"{_L('Conditional:')}{cond}", classes=f"event-body {scls}")
            rendered.add("conditional_signal")
            pub = sd.get("public_statement", "")
            yield Static(f"{_L('Public:')}{pub}", classes=f"event-body {scls}")
            rendered.add("public_statement")

        elif phase == "reflection":
            cred = sd.get("opponent_immediate_credibility", "")
            forecast_ability = sd.get("my_forecasting_ability", "")
            meta_cog = sd.get("my_meta_cognitive_ability", "")
            assessment = sd.get("situational_assessment", "")
            yield Static(f"{_L('Credibility:')}{cred}", classes=f"event-body {scls}")
            rendered.add("opponent_immediate_credibility")
            yield Static(f"{_L('Forecast:')}{forecast_ability}", classes=f"event-body {scls}")
            rendered.add("my_forecasting_ability")
            yield Static(f"{_L('Meta-cog:')}{meta_cog}", classes=f"event-body {scls}")
            rendered.add("my_meta_cognitive_ability")
            yield Static(f"{_L('Assessment:')}{assessment}", classes=f"event-body {scls}")
            rendered.add("situational_assessment")

        # ── LLM metadata footer (dark gray, always last) ──────────────
        meta = sd.get("llm_metadata")
        if isinstance(meta, dict):
            in_tok = meta.get("input_tokens", 0)
            out_tok = meta.get("output_tokens", 0)
            model_str = meta.get("model", "")
            temp = meta.get("temperature", "")
            max_tok = meta.get("max_tokens", "")
            yield Static(
                f"[{_LC}]llm:[/] {model_str}  [{_LC}]T=[/]{temp}  [{_LC}]max=[/]{max_tok}"
                f"  [{_LC}]in=[/]{in_tok}  [{_LC}]out=[/]{out_tok}",
                classes="event-meta",
            )
        rendered.add("llm_metadata")

        return rendered

    # ── State Change (tabular) ────────────────────────────────────────

    def _render_state_change(self, evt: GameEvent):
        sd = evt.structured_data
        rendered: set[str] = set()

        before = sd.get("territory_balance_before", "?")
        after = sd.get("territory_balance_after", "?")
        change = sd.get("territory_change", "?")
        if isinstance(change, (int, float)):
            yield Static(
                f"{_L('Territory')}{before} \u2192 {after}  ({change:+.4f})",
                classes="event-body",
            )
        else:
            yield Static(f"{_L('Territory')}{before} \u2192 {after}", classes="event-body")
        rendered |= {"territory_balance_before", "territory_balance_after", "territory_change"}

        if "a_action_effective" in sd:
            yield Static(f"{_L('A action')}{sd['a_action_effective']}", classes="event-body side-a")
            rendered.add("a_action_effective")
        if "b_action_effective" in sd:
            yield Static(f"{_L('B action')}{sd['b_action_effective']}", classes="event-body side-b")
            rendered.add("b_action_effective")

        for key, label, scls in [
            ("a_military_power", "A military", "side-a"),
            ("b_military_power", "B military", "side-b"),
        ]:
            mp = sd.get(key)
            if isinstance(mp, dict):
                conv = mp.get("conventional", "?")
                nuc = mp.get("nuclear", "?")
                if isinstance(conv, (int, float)):
                    yield Static(
                        f"{_L(label)}Conv: {conv:.1%}   Nuc: {nuc:.1%}",
                        classes=f"event-body {scls}",
                    )
                else:
                    yield Static(
                        f"{_L(label)}Conv: {conv}   Nuc: {nuc}",
                        classes=f"event-body {scls}",
                    )
                rendered.add(key)

        return rendered

    # ── KPI Update (tabular) ──────────────────────────────────────────

    def _render_kpi_update(self, evt: GameEvent):
        sd = evt.structured_data
        rendered: set[str] = set()

        if "territory_balance" in sd:
            tc = sd.get("territory_change", 0)
            yield Static(
                f"{_L('Territory')}{sd['territory_balance']:+.4f}  (change: {tc:+.4f})",
                classes="event-body",
            )
            rendered |= {"territory_balance", "territory_change"}

        for side, scls in [("a", "side-a"), ("b", "side-b")]:
            conv = sd.get(f"{side}_conventional_power")
            nuc = sd.get(f"{side}_nuclear_power")
            if conv is not None:
                yield Static(
                    f"{_L(f'{side.upper()} power')}Conv: {conv:.1%}   Nuc: {nuc:.1%}",
                    classes=f"event-body {scls}",
                )
                rendered |= {f"{side}_conventional_power", f"{side}_nuclear_power"}

        for side, scls in [("a", "side-a"), ("b", "side-b")]:
            sig = sd.get(f"{side}_signal_value")
            act = sd.get(f"{side}_action_value")
            gap = sd.get(f"signal_action_gap_{side}")
            if sig is not None:
                gap_str = f"   Gap: {gap:+d}" if isinstance(gap, int) else ""
                yield Static(
                    f"{_L(f'{side.upper()} signal')}Sig: {sig}   Act: {act}{gap_str}",
                    classes=f"event-body {scls}",
                )
                rendered |= {
                    f"{side}_signal_value",
                    f"{side}_action_value",
                    f"signal_action_gap_{side}",
                }

        return rendered

    # ── Situation Report ──────────────────────────────────────────────

    def _render_situation_report(self, evt: GameEvent):
        if evt.phase == "profiles":
            return (yield from self._render_profile(evt))
        if evt.phase == "scenario":
            return (yield from self._render_scenario(evt))

        rendered: set[str] = {"game_over", "end_reason"}

        # Parse body: "A: <status>, B: <status>. Territory: <value>"
        match = _SITREP_RE.match(evt.body)
        if match:
            a_status, b_status, territory = match.groups()
            yield Static(f"{_L('State A')}{a_status}", classes="event-body side-a")
            yield Static(f"{_L('State B')}{b_status}", classes="event-body side-b")
            yield Static(f"{_L('Territory')}{territory}", classes="event-body")
        elif evt.body:
            yield Static(_fmt_text(evt.body), classes="event-body")

        return rendered

    # ── Scenario Briefing (turn 0) ────────────────────────────────────

    def _render_scenario(self, evt: GameEvent):
        sd = evt.structured_data
        rendered: set[str] = {
            "scenario_key",
            "scenario_name",
            "context",
            "stakes",
            "pressure",
            "time_limit",
            "consequences",
        }

        scenario_key = sd.get("scenario_key", "")
        scenario_name = sd.get("scenario_name", "")
        if scenario_key:
            yield Static(f"{_L('Key:')}{scenario_key}", classes="event-body")
        if scenario_name and scenario_name != evt.title.removeprefix("Scenario: "):
            yield Static(f"{_L('Name:')}{scenario_name}", classes="event-body")

        time_limit = sd.get("time_limit")
        if time_limit is not None:
            yield Static(f"{_L('Deadline:')}{time_limit} turns", classes="event-body")

        for field, label in [
            ("context", "Context"),
            ("stakes", "Stakes"),
            ("pressure", "Pressure"),
            ("consequences", "Consequences"),
        ]:
            val = sd.get(field, "")
            if val:
                yield Static(f"[{_LC}]{label}:[/]", classes="event-data-key")
                yield Static(_fmt_text(val), classes="event-data-val")

        return rendered

    # ── State Profile (turn 0) ─────────────────────────────────────────

    def _render_profile(self, evt: GameEvent):
        sd = evt.structured_data
        side = sd.get("side", "")
        scls = _side_cls(side)
        rendered: set[str] = {"side", "model", "leader", "military", "assessment"}

        model = sd.get("model", "")
        if model:
            yield Static(f"{_L('Model:')}{model}", classes=f"event-body {scls}")

        # ── Leader ────────────────────────────────────────────────────
        leader = sd.get("leader", {})
        if isinstance(leader, dict) and leader:
            # Biography shown via evt.body; show structured fields here
            for lk, ll in [
                ("decision_style", "Style"),
                ("nuclear_doctrine", "Doctrine"),
                ("risk_tolerance", "Risk"),
            ]:
                lv = leader.get(lk, "")
                if lv:
                    yield Static(f"{_L(ll + ':')}{lv}", classes=f"event-body {scls}")

            traits = leader.get("traits", [])
            if traits:
                yield Static(f"{_L('Traits:')}{', '.join(traits)}", classes=f"event-body {scls}")

            concerns = leader.get("primary_concerns", [])
            if concerns:
                yield Static(
                    f"{_L('Concerns:')}{', '.join(concerns)}", classes=f"event-body {scls}"
                )

            factors = leader.get("decision_factors", {})
            if isinstance(factors, dict) and factors:
                parts = [f"{k.replace('_', ' ')}: {v:.0%}" for k, v in factors.items()]
                yield Static(f"{_L('Weighting:')}{';  '.join(parts)}", classes=f"event-body {scls}")

        # ── Military ──────────────────────────────────────────────────
        military = sd.get("military", {})
        if isinstance(military, dict) and military:
            conv_str = military.get("conventional_strength")
            if conv_str is not None:
                yield Static(f"{_L('Conv. str:')}{conv_str}", classes=f"event-body {scls}")

            nuc = military.get("nuclear_arsenal", {})
            if isinstance(nuc, dict) and nuc:
                warheads = nuc.get("total_warheads", "")
                icbms = nuc.get("icbms", "")
                subs = nuc.get("submarine_launched", "")
                bombers = nuc.get("bomber_delivered", "")
                if warheads:
                    wh_str = f"{warheads:,}" if isinstance(warheads, int) else str(warheads)
                    yield Static(f"{_L('Warheads:')}{wh_str}", classes=f"event-body {scls}")
                if icbms or subs or bombers:
                    yield Static(
                        f"{_L('  Delivery:')}" f"ICBMs: {icbms}  SLBMs: {subs}  Bombers: {bombers}",
                        classes=f"event-body {scls}",
                    )

            ds = military.get("delivery_systems", {})
            if isinstance(ds, dict) and ds:
                ds_parts = [f"{k.replace('_', ' ')}: {v}" for k, v in ds.items()]
                yield Static(
                    f"{_L('Del. sys:')}{';  '.join(ds_parts)}", classes=f"event-body {scls}"
                )

            # technological_advantage (State A key) or technological_status (State B key)
            tech = military.get("technological_advantage", military.get("technological_status", {}))
            if isinstance(tech, dict) and tech:
                tech_parts = [f"{k.replace('_', ' ')}: {v}" for k, v in tech.items()]
                yield Static(f"{_L('Tech:')}{';  '.join(tech_parts)}", classes=f"event-body {scls}")

            conv = military.get("conventional_forces", {})
            if isinstance(conv, dict) and conv:
                divs = conv.get("army_divisions", "")
                if divs:
                    yield Static(f"{_L('Divisions:')}{divs}", classes=f"event-body {scls}")
                for ck, cl in [
                    ("naval_superiority", "Naval"),
                    ("naval_capability", "Naval"),
                    ("air_force", "Air force"),
                    ("logistics", "Logistics"),
                ]:
                    cv = conv.get(ck, "")
                    if cv:
                        yield Static(f"{_L(cl + ':')}{cv}", classes=f"event-body {scls}")
                        break  # only one naval key

                for ck, cl in [("air_force", "Air force"), ("logistics", "Logistics")]:
                    cv = conv.get(ck, "")
                    if cv:
                        yield Static(f"{_L(cl + ':')}{cv}", classes=f"event-body {scls}")

            doctrine = military.get("strategic_doctrine", "")
            if doctrine:
                yield Static(f"{_L('Doctrine:')}{doctrine}", classes=f"event-body {scls}")

            strengths = military.get("key_strengths", [])
            if strengths:
                yield Static(
                    f"{_L('Strengths:')}{', '.join(strengths)}", classes=f"event-body {scls}"
                )
            weaknesses = military.get("key_weaknesses", [])
            if weaknesses:
                yield Static(
                    f"{_L('Weaknesses:')}{', '.join(weaknesses)}", classes=f"event-body {scls}"
                )

        # ── Assessment ────────────────────────────────────────────────
        assessment = sd.get("assessment", {})
        if isinstance(assessment, dict) and assessment:
            overall = assessment.get("overall", "")
            if overall:
                yield Static(f"[{_LC}]Assessment:[/]", classes="event-data-key")
                yield Static(overall, classes="event-data-val")

            opp_lead = assessment.get("opponent_leadership", {})
            if isinstance(opp_lead, dict) and opp_lead:
                for ok, ol in [
                    ("assessment", "Opp. assessment"),
                    ("predictability", "Predictability"),
                    ("risk_tolerance", "Opp. risk"),
                ]:
                    ov = opp_lead.get(ok, "")
                    if ov:
                        yield Static(f"{_L(ol + ':')}{ov}", classes=f"event-body {scls}")

            mil_threat = assessment.get("military_threat", {})
            if isinstance(mil_threat, dict) and mil_threat:
                for mk, ml in [
                    ("nuclear_capability", "Nuc. threat"),
                    ("conventional_threat", "Conv. threat"),
                    ("first_strike_assessment", "1st strike"),
                    ("escalation_tendency", "Escalation"),
                ]:
                    mv = mil_threat.get(mk, "")
                    if mv:
                        yield Static(f"{_L(ml + ':')}{mv}", classes=f"event-body {scls}")

            for list_key, list_label in [
                ("strategic_concerns", "Concerns"),
                ("strategic_assessment", "Assessment"),
                ("opportunities", "Opportunities"),
            ]:
                items = assessment.get(list_key, [])
                if items:
                    yield Static(
                        f"{_L(list_label + ':')}{', '.join(items)}",
                        classes=f"event-body {scls}",
                    )

            intel = assessment.get("intelligence_confidence", "")
            if intel:
                yield Static(f"{_L('Intel conf:')}{intel}", classes=f"event-body {scls}")

        # Biography shown as body
        if evt.body:
            yield Static(f"[{_LC}]Biography:[/]", classes="event-data-key")
            yield Static(_fmt_text(evt.body), classes="event-data-val")

        return rendered

    # ── Game Start (tabular) ──────────────────────────────────────────

    def _render_game_start(self, evt: GameEvent):
        sd = evt.structured_data
        rendered: set[str] = set()

        # ── Configuration fields ───────────────────────────────────
        for key, label in [
            ("scenario_key", "Scenario"),
            ("scenario_name", "Name"),
            ("aggressor_side", "Aggressor"),
            ("max_turns", "Max turns"),
            ("scenario_deadline", "Deadline"),
            ("start_balance", "Start bal."),
        ]:
            val = sd.get(key)
            if val is not None and val != "":
                yield Static(f"{_L(label + ':')}{val}", classes="event-body")
                rendered.add(key)

        # ── State A summary ────────────────────────────────────────
        display_a = sd.get("state_a_display_name", "State A")
        a_model = sd.get("state_a_model", "")
        a_leader = sd.get("state_a_leader", {})
        a_military = sd.get("state_a_military", {})
        a_assessment = sd.get("state_a_assessment", {})
        if a_model:
            yield Static(f"\n{_L(display_a + ':')}{a_model}", classes="event-body side-a")
            rendered.add("state_a_model")
        if isinstance(a_leader, dict):
            rendered.add("state_a_leader")  # always suppress raw-JSON fallback
            if a_leader:
                name = a_leader.get("name", "")
                if name:
                    yield Static(f"{_L('  Leader:')}{name}", classes="event-body side-a")
                traits = a_leader.get("traits", [])
                if traits:
                    yield Static(f"{_L('  Traits:')}{', '.join(traits)}", classes="event-body side-a")
                doctrine = a_leader.get("nuclear_doctrine", "")
                if doctrine:
                    yield Static(f"{_L('  Doctrine:')}{doctrine}", classes="event-body side-a")
                risk = a_leader.get("risk_tolerance", "")
                if risk:
                    yield Static(f"{_L('  Risk:')}{risk}", classes="event-body side-a")
        if isinstance(a_military, dict):
            rendered.add("state_a_military")
            if a_military:
                nuc = a_military.get("nuclear_arsenal", {})
                warheads = nuc.get("total_warheads", "") if isinstance(nuc, dict) else ""
                conv = a_military.get("conventional_forces", {})
                divisions = (
                    conv.get("army_divisions", conv.get("total_divisions", ""))
                    if isinstance(conv, dict)
                    else ""
                )
                if warheads:
                    wh = f"{warheads:,}" if isinstance(warheads, int) else str(warheads)
                    yield Static(f"{_L('  Warheads:')}{wh}", classes="event-body side-a")
                if divisions:
                    yield Static(f"{_L('  Divisions:')}{divisions}", classes="event-body side-a")
                strengths = a_military.get("key_strengths", [])
                if strengths:
                    yield Static(
                        f"{_L('  Strengths:')}{', '.join(strengths)}",
                        classes="event-body side-a",
                    )
        if isinstance(a_assessment, dict):
            rendered.add("state_a_assessment")
            if a_assessment:
                intel = a_assessment.get("intelligence_confidence", "")
                if intel:
                    yield Static(f"{_L('  Intel:')}{intel}", classes="event-body side-a")

        # ── State B summary ────────────────────────────────────────
        display_b = sd.get("state_b_display_name", "State B")
        b_model = sd.get("state_b_model", "")
        b_leader = sd.get("state_b_leader", {})
        b_military = sd.get("state_b_military", {})
        b_assessment = sd.get("state_b_assessment", {})
        if b_model:
            yield Static(f"\n{_L(display_b + ':')}{b_model}", classes="event-body side-b")
            rendered.add("state_b_model")
        if isinstance(b_leader, dict):
            rendered.add("state_b_leader")  # always suppress raw-JSON fallback
            if b_leader:
                name = b_leader.get("name", "")
                if name:
                    yield Static(f"{_L('  Leader:')}{name}", classes="event-body side-b")
                traits = b_leader.get("traits", [])
                if traits:
                    yield Static(f"{_L('  Traits:')}{', '.join(traits)}", classes="event-body side-b")
                doctrine = b_leader.get("nuclear_doctrine", "")
                if doctrine:
                    yield Static(f"{_L('  Doctrine:')}{doctrine}", classes="event-body side-b")
                risk = b_leader.get("risk_tolerance", "")
                if risk:
                    yield Static(f"{_L('  Risk:')}{risk}", classes="event-body side-b")
        if isinstance(b_military, dict):
            rendered.add("state_b_military")
            if b_military:
                nuc = b_military.get("nuclear_arsenal", {})
                warheads = nuc.get("total_warheads", "") if isinstance(nuc, dict) else ""
                conv = b_military.get("conventional_forces", {})
                divisions = (
                    conv.get("army_divisions", conv.get("total_divisions", ""))
                    if isinstance(conv, dict)
                    else ""
                )
                if warheads:
                    wh = f"{warheads:,}" if isinstance(warheads, int) else str(warheads)
                    yield Static(f"{_L('  Warheads:')}{wh}", classes="event-body side-b")
                if divisions:
                    yield Static(f"{_L('  Divisions:')}{divisions}", classes="event-body side-b")
                strengths = b_military.get("key_strengths", [])
                if strengths:
                    yield Static(
                        f"{_L('  Strengths:')}{', '.join(strengths)}",
                        classes="event-body side-b",
                    )
        if isinstance(b_assessment, dict):
            rendered.add("state_b_assessment")
            if b_assessment:
                intel = b_assessment.get("intelligence_confidence", "")
                if intel:
                    yield Static(f"{_L('  Intel:')}{intel}", classes="event-body side-b")

        # ── LLM defaults footer ────────────────────────────────────────
        llm_temp = sd.get("llm_temperature")
        llm_max = sd.get("llm_max_tokens")
        rendered |= {"llm_temperature", "llm_max_tokens",
                     "state_a_id", "state_b_id",
                     "state_a_display_name", "state_b_display_name"}
        if llm_temp is not None or llm_max is not None:
            yield Static(
                f"[{_LC}]llm defaults:[/] T={llm_temp}  max_tokens={llm_max}",
                classes="event-meta",
            )

        return rendered

    # ── Game End (tabular) ────────────────────────────────────────────

    def _render_game_end(self, evt: GameEvent):
        sd = evt.structured_data
        rendered: set[str] = set()

        for key, label in [
            ("end_reason", "Reason"),
            ("total_turns", "Turns"),
            ("final_territory", "Territory"),
            ("game_over", "Game over"),
        ]:
            val = sd.get(key)
            if val is not None:
                yield Static(f"{_L(label + ':')}{_fmt_val(val)}", classes="event-body")
                rendered.add(key)

        return rendered


# ── Split-view helpers ───────────────────────────────────────────────────────

# A single rendered field: (markup content, space-separated CSS classes).
_FieldSpec = tuple[str, str]


def _event_side(evt: GameEvent) -> str:
    """Return 'A', 'B', or '' for the event's side."""
    return str(evt.structured_data.get("side", "")).upper()


def _event_rows(evt: GameEvent) -> list[_FieldSpec]:
    """Return (markup, css_classes) for each visual row of *evt*.

    Used by the aligned split-view to pair corresponding rows from A and B
    events side-by-side.  Covers LLM_DECISION (all phases) in full; other
    event types emit title + meta + body only.
    """
    rows: list[_FieldSpec] = []
    data = evt.structured_data
    phase = evt.phase
    scls = _side_cls(str(data.get("side", "")))
    title_cls = _TITLE_CLS.get(evt.event_type, "")

    badge = _badge_text(evt)
    if badge:
        rows.append((badge, "source-badge"))

    rows.append((evt.title, f"event-title {title_cls}"))

    meta_parts = [f"seq={evt.sequence_number}", f"type={evt.event_type.value}"]
    if phase:
        meta_parts.append(f"phase={phase}")
    meta_parts.append(f"time={evt.timestamp.strftime('%H:%M:%S')}")
    if evt.parent_id:
        meta_parts.append(f"parent={evt.parent_id[:8]}")
    meta_parts.append(f"hash={evt.content_hash[:8]}")
    rows.append(("  ".join(meta_parts), "event-meta"))

    if evt.event_type == EventType.LLM_DECISION:
        if phase == "action":
            action_rung = data.get("action_rung", "")
            action_value = data.get("action_value", "")
            rows.append((f"{_L('Action: ')}{action_rung} ({action_value})", f"event-body {scls}"))
            accident_occurred = data.get("accident_occurred", "")
            accident_style = "event-body event-accident" if accident_occurred else "event-body"
            rows.append((f"{_L('accident_occurred: ')}{accident_occurred}", accident_style))
            cs = data.get("consistency_statement", "")
            rows.append((f"{_L('Consistency:')}{cs}", f"event-body {scls}"))

        elif phase == "forecast":
            predicted_opponent_action = data.get("predicted_opponent_action", "")
            predictive_confidence = data.get("predictive_confidence", "")
            rows.append((
                f"{_L('Prediction:')}{predicted_opponent_action}  (confidence: {predictive_confidence})",
                f"event-body {scls}",
            ))
            miscalculation_risk = data.get("miscalculation_risk", "")
            rows.append((f"{_L('Miscalc:')}{miscalculation_risk}", f"event-body {scls}"))

        elif phase == "signal":
            immediate_signal = data.get("immediate_signal", "")
            action_value = data.get("immediate_signal_value", "")
            rows.append((f"{_L('Signal:')} {immediate_signal} ({action_value})", f"event-body {scls}"))
            cond = data.get("conditional_signal", "")
            rows.append((f"{_L('Conditional:')} {cond}", f"event-body {scls}"))
            pub = data.get("public_statement", "")
            rows.append((f"{_L('Public:')} {pub}", f"event-body {scls}"))

        elif phase == "reflection":
            for key, label in [
                ("opponent_immediate_credibility", "Credibility"),
                ("my_forecasting_ability", "Forecast"),
                ("my_meta_cognitive_ability", "Meta-cog"),
                ("situational_assessment", "Assessment"),
            ]:
                v = data.get(key, "")
                if v:
                    rows.append((f"{_L(label + ':')}{v}", f"event-body {scls}"))
                    rows.append(("", "event-body"))

        if evt.body:
            rows.append((_fmt_text(evt.body), "event-body"))

    elif evt.body and evt.event_type != EventType.SITUATION_REPORT:
        rows.append((_fmt_text(evt.body), "event-body"))

    return rows


class _SplitPair(Widget):
    """Wraps the Horizontal rows for an A/B event pair.

    Handles double-click (opens edit modal for the side that was clicked)
    and right-click (posts context menu request).
    """

    def __init__(
        self,
        a_evt: "GameEvent | None",
        b_evt: "GameEvent | None",
        row_widgets: "list[Widget]",
    ) -> None:
        super().__init__(classes="split-pair")
        self._a_evt = a_evt
        self._b_evt = b_evt
        self._row_widgets = row_widgets

    def compose(self) -> "Any":  # type: ignore[override]
        yield from self._row_widgets

    def on_click(self, event: Click) -> None:
        """Handle double-click and right-click for split-view rows."""
        # Determine which side was clicked: left half = A, right half = B
        side_evt = (
            self._a_evt if event.x < self.size.width // 2 else self._b_evt
        )

        if event.button == 3:
            if side_evt is not None:
                self.post_message(
                    EventCardRightClicked(side_evt, event.screen_x, event.screen_y)
                )
        elif event.chain == 2:
            if side_evt is not None and side_evt.event_type == EventType.LLM_DECISION:
                self.post_message(EventCardDoubleClicked(side_evt))


def _build_aligned_pair(
    a_evt: "GameEvent | None",
    b_evt: "GameEvent | None",
    a_anns: "list[GameEvent] | None" = None,
    b_anns: "list[GameEvent] | None" = None,
) -> "_SplitPair":
    """Build an aligned :class:`_SplitPair` for an A/B event pair.

    Either event may be None (streaming — one side not yet arrived).
    The shorter row-list is padded with empty cells so fields stay aligned.
    Annotations for each side are appended beneath the main content rows.
    """
    a_rows: list[_FieldSpec] = _event_rows(a_evt) if a_evt is not None else []
    b_rows: list[_FieldSpec] = _event_rows(b_evt) if b_evt is not None else []

    max_len = max(len(a_rows), len(b_rows), 1)
    a_rows += [("", "")] * (max_len - len(a_rows))
    b_rows += [("", "")] * (max_len - len(b_rows))

    row_widgets: list[Widget] = []
    for (ac, acls), (bc, bcls) in zip(a_rows, b_rows):
        row_widgets.append(
            Horizontal(
                Static(ac, classes=f"split-field split-field-a {acls}".strip()),
                Static(bc, classes=f"split-field {bcls}".strip()),
                classes="split-field-row",
            )
        )

    # Annotation rows — TagCard boxes, one row per annotation pair, aligned A/B
    _a_anns = a_anns or []
    _b_anns = b_anns or []
    if _a_anns or _b_anns:
        max_ann = max(len(_a_anns), len(_b_anns))
        for i in range(max_ann):
            ann_a = _a_anns[i] if i < len(_a_anns) else None
            ann_b = _b_anns[i] if i < len(_b_anns) else None
            a_widget: Widget
            b_widget: Widget
            if ann_a is not None:
                a_widget = TagCard(ann_a, split=True)
                a_widget.add_class("split-field", "split-field-a")
            else:
                a_widget = Static("", classes="split-field split-field-a")
            if ann_b is not None:
                b_widget = TagCard(ann_b, split=True)
                b_widget.add_class("split-field")
            else:
                b_widget = Static("", classes="split-field")
            row_widgets.append(
                Horizontal(a_widget, b_widget, classes="split-field-row ann-split-row")
            )

    return _SplitPair(a_evt, b_evt, row_widgets)


def _build_sequential_children(
    events: list[GameEvent],
    ann_map: "dict[str, list[GameEvent]] | None" = None,
    show_dividers: bool = True,
) -> list[Widget]:
    """Stack event cards vertically with thin-rule dividers.

    Tags for each event are rendered as :class:`TagCard` widgets
    immediately after their parent event card, using tree-pipe prefix glyphs.
    Pass ``show_dividers=False`` to omit the horizontal rule between events
    (used for the End State group where dividers are visually noisy).
    """
    _ann = ann_map or {}
    children: list[Widget] = []
    for i, evt in enumerate(events):
        if i > 0 and show_dividers:
            children.append(Static(_THIN_RULE, classes="event-divider"))
        children.append(EventCard(evt))
        anns = _ann.get(evt.id, [])
        for j, tag in enumerate(anns):
            children.append(TagCard(tag, last=(j == len(anns) - 1)))
    return children


def _build_split_children(
    events: list[GameEvent],
    display_a: str = "State A",
    display_b: str = "State B",
    ann_map: "dict[str, list[GameEvent]] | None" = None,
    show_dividers: bool = True,
) -> list[Widget]:
    """Render events in a field-aligned A/B grid.

    Each visual row from the A event is paired with the corresponding row
    from the B event inside a ``Horizontal`` so the fields sit at the same
    vertical position for easy comparison.  Neutral events (no side) are
    rendered full-width above the grid.  Falls back to sequential layout
    when no A/B events are present.
    Pass ``show_dividers=False`` to omit horizontal rule dividers between events.
    """
    a_events = [e for e in events if _event_side(e) == "A"]
    b_events = [e for e in events if _event_side(e) == "B"]
    neutral_events = [e for e in events if _event_side(e) not in ("A", "B")]

    _ann = ann_map or {}

    if not a_events and not b_events:
        return _build_sequential_children(events, _ann, show_dividers)

    widgets: list[Widget] = []

    # Neutral events rendered full-width above the aligned grid
    for i, evt in enumerate(neutral_events):
        if i > 0 and show_dividers:
            widgets.append(Static(_THIN_RULE, classes="event-divider"))
        widgets.append(EventCard(evt))
        anns = _ann.get(evt.id, [])
        for j, tag in enumerate(anns):
            widgets.append(TagCard(tag, last=(j == len(anns) - 1)))

    # Column header row — always present so the grid has clear labels
    widgets.append(
        Horizontal(
            Static(display_a, classes="split-field split-field-a split-header split-header-a"),
            Static(display_b, classes="split-field split-header split-header-b"),
            classes="split-field-row",
        )
    )

    # Pair A[i] with B[i]; either may be None (streaming — one side pending)
    n_pairs = max(len(a_events), len(b_events))
    for i in range(n_pairs):
        if i > 0 and show_dividers:
            widgets.append(Static(_THIN_RULE, classes="event-divider"))
        a_evt = a_events[i] if i < len(a_events) else None
        b_evt = b_events[i] if i < len(b_events) else None
        a_anns = _ann.get(a_evt.id, []) if a_evt is not None else []
        b_anns = _ann.get(b_evt.id, []) if b_evt is not None else []
        widgets.append(_build_aligned_pair(a_evt, b_evt, a_anns, b_anns))

    return widgets


# ── ContentPane ─────────────────────────────────────────────────────────────


class ContentPane(VerticalScroll):
    """Main content area — shows event cards for the selected turn."""

    def __init__(
        self,
        store: EventStore,
        split_threshold: int = 100,
        double_newlines: bool = True,
        wrap_indent: int = 0,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        super().__init__(id=id, classes=classes)
        self._store = store
        self._current_turn: int | None = None
        self._split_threshold = split_threshold
        self._last_split: bool | None = None
        self._display_a: str = "State A"
        self._display_b: str = "State B"
        configure_text_format(double_newlines=double_newlines, wrap_indent=wrap_indent)

    def _load_display_names(self) -> None:
        """Extract actor display names from the GAME_START event (turn 0)."""
        for evt in self._store.get_events(turn=0, limit=50):
            if evt.event_type == EventType.GAME_START:
                sd = evt.structured_data or {}
                self._display_a = sd.get("state_a_display_name", "State A")
                self._display_b = sd.get("state_b_display_name", "State B")
                break

    def _build_initial_state(self, turn: int) -> Collapsible | None:
        """Build an 'Initial State' group from the previous turn's end-state data."""
        prev_turn = turn - 1
        events = self._store.get_events(turn=prev_turn, limit=1000)
        if not events:
            return None

        state_evt = None
        kpi_evt = None
        for e in events:
            if e.event_type == EventType.STATE_CHANGE and not e.phase:
                state_evt = e
            elif e.event_type == EventType.KPI_UPDATE:
                kpi_evt = e

        if not state_evt and not kpi_evt:
            return None

        children: list[Widget] = []

        if state_evt:
            sd = state_evt.structured_data
            territory = sd.get("territory_balance_after", sd.get("territory_balance_before", "?"))
            if isinstance(territory, (int, float)):
                children.append(Static(f"{_L('Territory')}{territory:+.4f}", classes="event-body"))

            for key, label, scls in [
                ("a_military_power", "A military", "side-a"),
                ("b_military_power", "B military", "side-b"),
            ]:
                mp = sd.get(key)
                if isinstance(mp, dict):
                    conv = mp.get("conventional", "?")
                    nuc = mp.get("nuclear", "?")
                    if isinstance(conv, (int, float)):
                        children.append(
                            Static(
                                f"{_L(label)}Conv: {conv:.1%}   Nuc: {nuc:.1%}",
                                classes=f"event-body {scls}",
                            )
                        )

        if kpi_evt:
            sd = kpi_evt.structured_data
            for side, scls in [("a", "side-a"), ("b", "side-b")]:
                sig = sd.get(f"{side}_signal_value")
                act = sd.get(f"{side}_action_value")
                if sig is not None:
                    children.append(
                        Static(
                            f"{_L(f'{side.upper()} signal')}Sig: {sig}   Act: {act}",
                            classes=f"event-body {scls}",
                        )
                    )

        if not children:
            return None

        return Collapsible(
            *children,
            title="Initial State",
            collapsed=False,
            classes="phase-group group-initialstate",
        )

    def load_turn(self, turn: int) -> None:
        """Clear and rebuild grouped event cards for *turn*."""
        if turn == self._current_turn:
            return
        self._current_turn = turn
        self.remove_children()

        # Determine whether to use side-by-side A/B split layout.
        # self.size.width is 0 before the first layout pass; fall back to an
        # estimate based on the terminal width and the 3fr/4fr CSS ratio.
        pane_width = self.size.width or max(0, (self.app.size.width * 3) // 4)
        use_split = self._split_threshold > 0 and pane_width >= self._split_threshold
        self._last_split = use_split

        # Show banner at top of turn 0, wrapped in a "Project Kahn" group
        if turn == 0:
            self.mount(
                Collapsible(
                    KahnBanner(),
                    title="Project Kahn",
                    collapsed=False,
                    classes="phase-group group-banner",
                )
            )

        # For turns >= 1, prepend "Initial State" from previous turn's end-state data
        if turn >= 1:
            initial = self._build_initial_state(turn)
            if initial:
                self.mount(initial)

        # Refresh display names from GAME_START (handles reload after new game data)
        self._load_display_names()

        events = self._store.get_events(turn=turn, limit=1000)

        # Build tag map: parent_id → [tag/annotation events]
        ann_map: dict[str, list[GameEvent]] = {}
        for evt in events:
            if evt.event_type in (EventType.TAG, EventType.ANNOTATION) and evt.parent_id:
                ann_map.setdefault(evt.parent_id, []).append(evt)

        groups = _group_events(events)

        for group in groups:
            show_div = group.css_class != "group-endstate"
            children = (
                _build_split_children(
                    group.events, self._display_a, self._display_b, ann_map,
                    show_dividers=show_div,
                )
                if use_split
                else _build_sequential_children(group.events, ann_map, show_dividers=show_div)
            )
            self.mount(
                Collapsible(
                    *children,
                    title=group.label,
                    collapsed=False,
                    classes=f"phase-group {group.css_class}",
                )
            )

        # Defer scroll_home until after layout has settled — mounts are
        # batched and laid out asynchronously, so calling scroll_home()
        # inline runs before widgets have computed positions.
        self.set_timer(0.05, lambda: self.scroll_home(animate=False))

    def scroll_to_group(self, group_slug: str) -> None:
        """Scroll so the first Collapsible with the given group CSS class is at the top.

        Uses a timer to ensure the layout pass has completed and widget
        virtual regions are fully computed before attempting to scroll.
        """
        css_cls = f"group-{group_slug}"

        def _do_scroll() -> None:
            results = self.query(f".{css_cls}")
            if results:
                target = results.first()
                # Use the widget's virtual_region (computed after layout)
                # to scroll to an exact y offset rather than relying on
                # scroll_to_widget which may misfire before layout settles.
                region = target.virtual_region
                self.scroll_to(y=region.y, animate=False)

        # Defer scroll until after layout has had time to compute geometry.
        # A short timer is more reliable than call_after_refresh for newly
        # mounted widget trees.
        self.set_timer(0.15, _do_scroll)

    def force_load_turn(self, turn: int) -> None:
        """Load a turn even if it's the same as the current one."""
        self._current_turn = None
        self.load_turn(turn)

    def on_resize(self, event: Resize) -> None:
        """Rerender the current turn when the split-view threshold is crossed."""
        if self._current_turn is None or self._split_threshold <= 0:
            return
        use_split = event.size.width >= self._split_threshold
        if use_split != self._last_split:
            self.force_load_turn(self._current_turn)
