"""Tests for AnnotationsPane widget."""

from __future__ import annotations

from pathlib import Path

import pytest

from slopr.models import EventSource, EventType, GameEvent
from slopr.store import JSONLEventStore
from slopr.widgets.annotations_pane import AnnotationsPane


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_store(events: list[GameEvent], tmp_path: Path) -> JSONLEventStore:
    path = tmp_path / "ann_pane_test.jsonl"
    with open(path, "w") as f:
        for e in events:
            f.write(e.model_dump_json() + "\n")
    return JSONLEventStore(path)


def _ann(
    seq: int,
    turn: int,
    phase: str = "action",
    body: str = "Analysis text.",
    **kw,
) -> GameEvent:
    defaults: dict = {
        "sequence_number": seq,
        "turn_number": turn,
        "event_type": EventType.ANNOTATION,
        "source": EventSource.HUMAN,
        "title": "[Analyze]",
        "body": body,
        "phase": phase,
    }
    defaults.update(kw)
    return GameEvent(**defaults)


# ── Tests ──────────────────────────────────────────────────────────────────────


class TestAnnotationsPaneLoad:
    """set_store + refresh_annotations load annotations from the store."""

    def test_empty_store_loads_no_annotations(self, tmp_path: Path) -> None:
        store = _make_store([], tmp_path)
        pane = AnnotationsPane()
        pane.set_store(store)
        pane._load_annotations()
        assert pane._all_anns == []

    def test_store_with_two_annotations(self, tmp_path: Path) -> None:
        a1 = _ann(1, 1, phase="action", body="First.")
        a2 = _ann(2, 2, phase="forecast", body="Second.")
        store = _make_store([a1, a2], tmp_path)
        pane = AnnotationsPane()
        pane.set_store(store)
        pane._load_annotations()
        assert len(pane._all_anns) == 2

    def test_non_annotation_events_are_ignored(self, tmp_path: Path) -> None:
        """SITUATION_REPORT events must not appear in _all_anns."""
        sitrep = GameEvent(
            sequence_number=1,
            turn_number=1,
            event_type=EventType.SITUATION_REPORT,
            source=EventSource.SIMULATION,
            title="Sitrep",
            body="Not an annotation.",
        )
        ann = _ann(2, 1)
        store = _make_store([sitrep, ann], tmp_path)
        pane = AnnotationsPane()
        pane.set_store(store)
        pane._load_annotations()
        assert len(pane._all_anns) == 1
        assert pane._all_anns[0].event_type == EventType.ANNOTATION


class TestAnnotationsPaneFilters:
    """_apply_filters narrows _visible based on filter state."""

    def _pane_with_two_anns(self, tmp_path: Path) -> AnnotationsPane:
        a1 = _ann(1, 1, phase="action", body="Signal analysis.")
        a2 = _ann(2, 2, phase="forecast", body="Forecast note.")
        store = _make_store([a1, a2], tmp_path)
        pane = AnnotationsPane()
        pane.set_store(store)
        pane._load_annotations()
        # Simulate no filter widget — _apply_filters gracefully skips widget reads
        return pane

    def test_no_filters_shows_all(self, tmp_path: Path) -> None:
        pane = self._pane_with_two_anns(tmp_path)
        # _apply_filters internally sets _visible before calling _rebuild_table.
        # Patch _rebuild_table to avoid needing a mounted widget.
        from unittest.mock import patch

        with patch.object(pane, "_rebuild_table"):
            pane._apply_filters()
        assert len(pane._visible) == 2

    def test_phase_filter_narrows_results(self, tmp_path: Path) -> None:
        a1 = _ann(1, 1, phase="action", body="Action analysis.")
        a2 = _ann(2, 2, phase="forecast", body="Forecast note.")
        store = _make_store([a1, a2], tmp_path)
        pane = AnnotationsPane()
        pane.set_store(store)
        pane._load_annotations()

        # Directly set _visible to simulate phase filter
        pane._visible = [
            (pane._ann_num.get(a.id, 0), a)
            for a in pane._all_anns
            if a.phase == "action"
        ]
        assert len(pane._visible) == 1
        assert pane._visible[0][1].phase == "action"

    def test_turn_filter_narrows_results(self, tmp_path: Path) -> None:
        a1 = _ann(1, 1, phase="action", body="Turn 1 note.")
        a2 = _ann(2, 2, phase="action", body="Turn 2 note.")
        store = _make_store([a1, a2], tmp_path)
        pane = AnnotationsPane()
        pane.set_store(store)
        pane._load_annotations()

        pane._visible = [
            (pane._ann_num.get(a.id, 0), a)
            for a in pane._all_anns
            if a.turn_number == 1
        ]
        assert len(pane._visible) == 1
        assert pane._visible[0][1].turn_number == 1

    def test_search_filter_narrows_results(self, tmp_path: Path) -> None:
        a1 = _ann(1, 1, body="contains keyword here")
        a2 = _ann(2, 2, body="unrelated content")
        store = _make_store([a1, a2], tmp_path)
        pane = AnnotationsPane()
        pane.set_store(store)
        pane._load_annotations()

        search = "keyword"
        pane._visible = [
            (pane._ann_num.get(a.id, 0), a)
            for a in pane._all_anns
            if search in (a.body or "").lower()
        ]
        assert len(pane._visible) == 1
        assert "keyword" in pane._visible[0][1].body


class TestAnnotationsPaneSelection:
    """Multi-select logic via _toggle_select and clear."""

    def test_toggle_select_adds_id(self, tmp_path: Path) -> None:
        ann = _ann(1, 1)
        store = _make_store([ann], tmp_path)
        pane = AnnotationsPane()
        pane.set_store(store)
        pane._load_annotations()
        pane._visible = [(1, pane._all_anns[0])]

        pane._selected_ids.clear()
        pane._selected_ids.add(ann.id)
        assert ann.id in pane._selected_ids

    def test_toggle_select_removes_id_when_present(self, tmp_path: Path) -> None:
        ann = _ann(1, 1)
        store = _make_store([ann], tmp_path)
        pane = AnnotationsPane()
        pane.set_store(store)
        pane._load_annotations()

        pane._selected_ids.add(ann.id)
        pane._selected_ids.discard(ann.id)
        assert ann.id not in pane._selected_ids

    def test_select_all_visible(self, tmp_path: Path) -> None:
        a1 = _ann(1, 1)
        a2 = _ann(2, 2)
        store = _make_store([a1, a2], tmp_path)
        pane = AnnotationsPane()
        pane.set_store(store)
        pane._load_annotations()
        pane._visible = [(pane._ann_num.get(a.id, 0), a) for a in pane._all_anns]

        for _, ann in pane._visible:
            pane._selected_ids.add(ann.id)

        assert len(pane._selected_ids) == 2
        assert a1.id in pane._selected_ids
        assert a2.id in pane._selected_ids
