"""Turn sidebar — ``Tree``-based turn index for the wargame TUI."""

from __future__ import annotations

from rich.style import Style
from rich.text import Text

from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Static, Tree
from textual.widgets.tree import TreeNode
from textual.containers import Container, Horizontal

from slopr.models import EventSource, EventType
from slopr.store import EventStore

# ── Phase label mapping (matches content_pane._PHASE_LABELS) ──────────────

_PHASE_LABELS: dict[str, str] = {
    "reflection": "Reflection",
    "forecast": "Forecast",
    "signal": "Signal",
    "action": "Action",
    "scenario": "Scenario",
    "profiles": "State Profiles",
}

# Canonical phase ordering
_PHASE_ORDER = ["scenario", "profiles", "reflection", "forecast", "signal", "action"]

# Colors — hex values mirrored exactly from wargame.tcss group border colors
_PHASE_COLORS: dict[str, str] = {
    "reflection": "#00bcd4",
    "forecast": "#42a5f5",
    "signal": "#ab47bc",
    "action": "#ffa726",
    "scenario": "#4caf50",
    "profiles": "#7986cb",
    "initialstate": "#546e7a",
    "endstate": "#90a4ae",
    "parameters": "#26a69a",
    "game": "#4caf50",
    "gameover": "#ef5350",
    "banner": "#daa520",
}


# ── Messages ──────────────────────────────────────────────────────────────


class TurnSelected(Message):
    """Posted when the user selects a turn in the sidebar."""

    def __init__(self, turn: int) -> None:
        super().__init__()
        self.turn = turn


class PhaseSelected(Message):
    """Posted when the user clicks a phase leaf in the sidebar tree."""

    def __init__(self, turn: int, group: str) -> None:
        super().__init__()
        self.turn = turn
        self.group = group


# ── Node data ─────────────────────────────────────────────────────────────

# Each tree node stores a dict: {"turn": int, "group": str | None}
# Turn-level nodes have group=None; phase leaves have a group slug.

NodeData = dict[str, object]


def _colored_label(text: str, group: str) -> Text:
    """Return a Rich Text label colored to match the main pane phase."""
    color = _PHASE_COLORS.get(group, "")
    return Text(text, style=color)


# ── TurnIndex ─────────────────────────────────────────────────────────────


class TurnIndex(Tree[NodeData]):
    """Navigable tree of turns with expandable phase sub-items."""

    def __init__(self, store: EventStore) -> None:
        super().__init__("Turns", id="turn-index")
        self._store = store
        self._loaded_turn: int | None = None
        self.show_root = False
        self.guide_depth = 3
        self.auto_expand = False  # We manage expand/collapse ourselves
        # Set of event IDs edited in the *current* branch (used for ~ glyph)
        self._branch_edited_ids: set[str] = set()

    def render_label(self, node: TreeNode[NodeData], base_style: Style, style: Style) -> Text:
        """Render labels without ▶/▼ toggle arrows."""
        node_label = node._label.copy()
        node_label.stylize(style)
        return node_label

    def on_mount(self) -> None:
        self.refresh_turns()

    def refresh_turns(self) -> None:
        """Rebuild the tree from the store, preserving current expansion state."""
        # Snapshot which turns were expanded before we wipe the tree
        expanded_turns: set[int] = set()
        for child in self.root.children:
            if child.is_expanded and child.data is not None:
                t = child.data.get("turn")
                if isinstance(t, int):
                    expanded_turns.add(t)

        self.clear()
        turns = self._store.get_turn_numbers()
        for t in turns:
            # Check what event types exist in this turn
            turn_events = self._store.get_events(turn=t, limit=1000)

            # Skip turns whose only events are PHASE_TRANSITION markers —
            # they have no displayable content yet (common during live streaming).
            if not any(e.event_type != EventType.PHASE_TRANSITION for e in turn_events):
                continue

            summary = self._store.get_turn_summary(t)
            count = summary["event_count"]
            llm_glyph = " *" if summary["has_llm"] else ""
            edit_glyph = " ~" if summary["has_edit"] else ""

            # Fork-suggestion glyph — appears when an action value exceeds the
            # threshold, signalling this turn is an interesting branching point.
            has_fork_signal = any(
                (
                    isinstance(e.structured_data, dict)
                    and (
                        e.structured_data.get("a_action_value", 0) > 0.6
                        or e.structured_data.get("b_action_value", 0) > 0.6
                    )
                )
                for e in turn_events
                if e.event_type == EventType.KPI_UPDATE
            )
            fork_glyph = " ⚡" if has_fork_signal else ""

            has_annotations = any(
                e.event_type in (EventType.TAG, EventType.ANNOTATION) for e in turn_events
            )
            ann_glyph = " †" if has_annotations else ""

            has_accident = any(
                isinstance(e.structured_data, dict)
                and e.structured_data.get("accident_occurred")
                for e in turn_events
                if e.event_type == EventType.LLM_DECISION
            )
            acc_glyph = " !" if has_accident else ""

            label = f"Turn {t}  ({count} events){llm_glyph}{edit_glyph}{fork_glyph}{ann_glyph}{acc_glyph}"

            turn_node = self.root.add(label, data={"turn": t, "group": None}, allow_expand=True)

            has_sim = any(
                e.event_type
                in {EventType.STATE_CHANGE, EventType.KPI_UPDATE, EventType.SITUATION_REPORT}
                for e in turn_events
            )
            has_game_end = any(e.event_type == EventType.GAME_END for e in turn_events)
            has_game_start = any(e.event_type == EventType.GAME_START for e in turn_events)

            # Parameters (when GAME_START event exists)
            if has_game_start:
                turn_node.add_leaf(
                    _colored_label("Parameters", "parameters"),
                    data={"turn": t, "group": "parameters"},
                )

            # Initial State (turns >= 1, before phase groups)
            if has_sim and t >= 1:
                turn_node.add_leaf(
                    _colored_label("Initial State", "initialstate"),
                    data={"turn": t, "group": "initialstate"},
                )

            # Phase leaves based on what phases exist in this turn
            phases: list[str] = summary.get("phases", [])  # type: ignore[assignment]
            for phase in _PHASE_ORDER:
                if phase in phases:
                    phase_label = _PHASE_LABELS.get(phase, phase.title())

                    # Per-phase indicator glyphs
                    phase_evts = [
                        e for e in turn_events
                        if e.phase == phase and e.event_type != EventType.PHASE_TRANSITION
                    ]
                    p_llm = any(e.source == EventSource.LLM for e in phase_evts)
                    p_ann = any(e.event_type in (EventType.TAG, EventType.ANNOTATION) for e in phase_evts)
                    p_edit = any(e.id in self._branch_edited_ids for e in phase_evts)

                    # Action-phase extras: hotspot ⚡ and accident !
                    if phase == "action":
                        p_fork = " ⚡" if has_fork_signal else ""
                        p_acc = " !" if any(
                            isinstance(e.structured_data, dict)
                            and e.structured_data.get("accident_occurred")
                            for e in phase_evts
                            if e.event_type == EventType.LLM_DECISION
                        ) else ""
                    else:
                        p_fork = ""
                        p_acc = ""

                    # Collect unique skill glyphs from TAG events in this phase
                    _skill_glyphs = " ".join(dict.fromkeys(
                        e.structured_data.get("skill_glyph", "")
                        for e in phase_evts
                        if e.event_type in (EventType.TAG, EventType.ANNOTATION)
                        and isinstance(e.structured_data, dict)
                        and e.structured_data.get("skill_glyph")
                    ))
                    p_skill = f" {_skill_glyphs}" if _skill_glyphs else ""

                    p_glyphs = (
                        (" *" if p_llm else "")
                        + (" †" if p_ann else "")
                        + (" ~" if p_edit else "")
                        + p_fork
                        + p_acc
                        + p_skill
                    )

                    turn_node.add_leaf(
                        _colored_label(phase_label + p_glyphs, phase),
                        data={"turn": t, "group": phase},
                    )

            # End State (after phase groups)
            if has_sim:
                has_ann_endstate = any(
                    e.event_type in (EventType.TAG, EventType.ANNOTATION)
                    for e in turn_events
                    if e.phase == ""
                )
                endstate_glyph = "  †" if has_ann_endstate else ""
                turn_node.add_leaf(
                    _colored_label("End State" + endstate_glyph, "endstate"),
                    data={"turn": t, "group": "endstate"},
                )

            # Game Over (always last)
            if has_game_end:
                turn_node.add_leaf(
                    _colored_label("Game Over", "gameover"),
                    data={"turn": t, "group": "gameover"},
                )

        # Restore expansion state — any turn that was open before stays open
        if expanded_turns:
            for child in self.root.children:
                if child.data is not None:
                    ct = child.data.get("turn")
                    if isinstance(ct, int) and ct in expanded_turns:
                        child.expand()

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted[NodeData]) -> None:
        """When cursor moves to a turn node, expand it to reveal phase children.

        NodeHighlighted fires reliably on both mouse click and keyboard
        navigation.  We use it purely for sidebar expansion so the user
        always sees the phase list without needing a second click.
        """
        node: TreeNode[NodeData] = event.node
        data = node.data
        if data is None or data.get("group") is not None:
            return  # Skip phase-leaf nodes and root

        # Turn-level node: expand if collapsed; collapse other turns.
        for child in self.root.children:
            if child is not node and child.is_expanded:
                child.collapse()
        if not node.is_expanded:
            node.expand()

    def on_tree_node_selected(self, event: Tree.NodeSelected[NodeData]) -> None:
        """Clicking (or pressing Enter) on a node triggers content navigation.

        Turn-level nodes only expand / collapse the tree — they never change the
        content pane.  Navigation happens exclusively when the user selects a
        phase leaf, which posts :class:`PhaseSelected`.
        """
        node: TreeNode[NodeData] = event.node
        data = node.data
        if data is None:
            return

        group: str | None = data["group"]  # type: ignore[assignment]

        if group is None:
            # Turn-level node — toggle expand/collapse only; no content navigation.
            if node.is_expanded:
                node.collapse()
            else:
                node.expand()
        else:
            # Phase leaf node — navigate to that group in the content pane.
            turn: int = data["turn"]  # type: ignore[assignment]
            self._loaded_turn = turn
            self.post_message(PhaseSelected(turn, group))


# ── PaneNavBar ────────────────────────────────────────────────────────────────


class PaneNavSelected(Message):
    """Posted when the user clicks a nav tab to switch the active pane."""

    def __init__(self, pane: str) -> None:
        super().__init__()
        self.pane = pane
        """One of ``"events"``, ``"branches"``, ``"sims"``."""


class NavTab(Static):
    """Minimal text tab — posts :class:`PaneNavSelected` when clicked."""

    DEFAULT_CSS = """
    NavTab {
        width: auto;
        height: 1;
        padding: 0 1;
        color: $text-disabled;
    }
    NavTab:hover {
        color: $text;
    }
    NavTab.--active {
        color: $accent;
        text-style: bold;
    }
    """

    def __init__(self, label: str, pane: str, active: bool = False) -> None:
        super().__init__(label)
        self._pane = pane
        if active:
            self.add_class("--active")

    def on_click(self) -> None:  # type: ignore[override]
        self.post_message(PaneNavSelected(self._pane))


class PaneNavBar(Widget):
    """Tab strip at the bottom of the sidebar for pane switching."""

    DEFAULT_CSS = """
    PaneNavBar {
        height: 1;
        dock: bottom;
        layout: horizontal;
        align: left middle;
        background: $surface;
        border-top: solid $surface-lighten-2;
        padding: 0 1;
    }
    .nav-sep {
        color: $text-disabled;
        width: 1;
        height: 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield NavTab("Events",         pane="events",      active=True)
        yield Static("│", classes="nav-sep")
        yield NavTab("Branches ^B",    pane="branches")
        yield Static("│", classes="nav-sep")
        yield NavTab("Sims ^S",        pane="sims")
        yield Static("│", classes="nav-sep")
        yield NavTab("Tasks ^T",       pane="tasks")
        yield Static("│", classes="nav-sep")
        yield NavTab("Tags ^G",        pane="tags")
        yield Static("│", classes="nav-sep")
        yield NavTab("Skills ^K",      pane="skills")
        yield Static("│", classes="nav-sep")
        yield NavTab("Config ^P",      pane="config")

    def set_active(self, pane: str) -> None:
        """Toggle ``--active`` CSS class on the matching tab."""
        for tab in self.query(NavTab):
            if tab._pane == pane:
                tab.add_class("--active")
            else:
                tab.remove_class("--active")


# ── GlyphLegend ───────────────────────────────────────────────────────────────

_LEGEND_LINES = (
    "*  llm",
    "~  edited",
    "⚡  hotspot",
    "†  tagged",
    "!  accident",
)

_LEGEND_TEXT = "\n".join(_LEGEND_LINES)


class GlyphLegend(Static):
    """Compact glyph-key legend rendered at the bottom of the sidebar."""

    DEFAULT_CSS = """
    GlyphLegend {
        color: $text-disabled;
        height: auto;
        padding: 0 1;
        border-top: solid $surface-lighten-1;
    }
    """

    def __init__(self) -> None:
        super().__init__(_LEGEND_TEXT)


# ── TurnSidebar ───────────────────────────────────────────────────────────────


class TurnSidebar(Container):
    """Sidebar container wrapping the turn index and pane navigation bar."""

    def __init__(self, store: EventStore) -> None:
        super().__init__()
        self._store = store

    def compose(self):  # type: ignore[override]
        yield Static("Event Index", classes="sidebar-header")
        yield TurnIndex(self._store)
        yield GlyphLegend()
        yield PaneNavBar()
