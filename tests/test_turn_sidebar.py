"""Tests for TurnSidebar / TurnIndex — phase glyphs and endstate annotation glyph."""

from __future__ import annotations

from slopr.models import EventSource, EventType, GameEvent
from slopr.store import JSONLEventStore
from slopr.widgets.turn_sidebar import TurnIndex


def _make_store_with_events(events: list[GameEvent], tmp_path) -> JSONLEventStore:
    """Write *events* to a temp JSONL and return a loaded store."""
    import json

    path = tmp_path / "sidebar_test.jsonl"
    with open(path, "w") as f:
        for e in events:
            f.write(e.model_dump_json() + "\n")
    return JSONLEventStore(path)


def _evt(seq: int, turn: int, **kw) -> GameEvent:
    defaults = {
        "sequence_number": seq,
        "turn_number": turn,
        "event_type": EventType.SITUATION_REPORT,
        "source": EventSource.SIMULATION,
        "title": f"Event {seq}",
        "body": "",
    }
    defaults.update(kw)
    return GameEvent(**defaults)


class TestEndstateAnnotationGlyph:
    """TurnIndex.refresh_turns() appends † to 'End State' leaf when phase='' annotations exist."""

    def test_endstate_leaf_has_dagger_when_annotation_exists(self, tmp_path) -> None:
        """Turn with a TAG(phase='') produces 'End State  †' leaf label."""
        state_change = _evt(
            1, 1,
            event_type=EventType.STATE_CHANGE,
            source=EventSource.SIMULATION,
            title="State changed",
        )
        annotation = _evt(
            2, 1,
            event_type=EventType.TAG,
            source=EventSource.HUMAN,
            title="[Note]",
            body="Analysis text.",
            phase="",   # end-state tag
        )
        store = _make_store_with_events([state_change, annotation], tmp_path)

        index = TurnIndex(store)
        index.refresh_turns()

        # Collect all leaf labels for turn 1
        leaf_labels: list[str] = []
        for turn_node in index.root.children:
            for leaf in turn_node.children:
                leaf_labels.append(str(leaf._label.plain))

        assert any("End State" in lbl and "†" in lbl for lbl in leaf_labels), (
            f"Expected 'End State  †' leaf but got: {leaf_labels}"
        )

    def test_endstate_leaf_no_dagger_without_annotation(self, tmp_path) -> None:
        """Turn without phase='' annotations renders 'End State' with no †."""
        state_change = _evt(
            1, 1,
            event_type=EventType.STATE_CHANGE,
            source=EventSource.SIMULATION,
            title="State changed",
        )
        store = _make_store_with_events([state_change], tmp_path)

        index = TurnIndex(store)
        index.refresh_turns()

        leaf_labels: list[str] = []
        for turn_node in index.root.children:
            for leaf in turn_node.children:
                leaf_labels.append(str(leaf._label.plain))

        endstate_labels = [lbl for lbl in leaf_labels if "End State" in lbl]
        assert endstate_labels, "Expected at least one End State leaf"
        assert not any("†" in lbl for lbl in endstate_labels), (
            f"Did not expect † in End State leaf but got: {endstate_labels}"
        )

    def test_phase_annotation_glyph_not_on_endstate_leaf(self, tmp_path) -> None:
        """ANNOTATION with phase='action' adds † to the action leaf, not End State."""
        state_change = _evt(
            1, 1,
            event_type=EventType.STATE_CHANGE,
            source=EventSource.SIMULATION,
            title="State changed",
        )
        llm = _evt(
            2, 1,
            event_type=EventType.LLM_DECISION,
            source=EventSource.LLM,
            title="Decision",
            phase="action",
        )
        annotation = _evt(
            3, 1,
            event_type=EventType.TAG,
            source=EventSource.HUMAN,
            title="[Note]",
            body="Note on action.",
            phase="action",
        )
        store = _make_store_with_events([state_change, llm, annotation], tmp_path)

        index = TurnIndex(store)
        index.refresh_turns()

        leaf_labels: list[str] = []
        for turn_node in index.root.children:
            for leaf in turn_node.children:
                leaf_labels.append(str(leaf._label.plain))

        endstate_labels = [lbl for lbl in leaf_labels if "End State" in lbl]
        action_labels = [lbl for lbl in leaf_labels if "Action" in lbl]

        # End State should NOT have †
        assert endstate_labels
        assert not any("†" in lbl for lbl in endstate_labels)
        # Action leaf SHOULD have †
        assert action_labels
        assert any("†" in lbl for lbl in action_labels)
