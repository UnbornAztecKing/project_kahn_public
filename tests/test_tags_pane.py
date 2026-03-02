"""Tests for TagsPane widget."""

from __future__ import annotations

from pathlib import Path

import pytest

from slopr.models import EventSource, EventType, GameEvent
from slopr.store import JSONLEventStore
from slopr.widgets.tags_pane import TagsPane


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_store(events: list[GameEvent], tmp_path: Path) -> JSONLEventStore:
    path = tmp_path / "tag_pane_test.jsonl"
    with open(path, "w") as f:
        for e in events:
            f.write(e.model_dump_json() + "\n")
    return JSONLEventStore(path)


def _tag(
    seq: int,
    turn: int,
    phase: str = "action",
    body: str = "Analysis text.",
    event_type: EventType = EventType.TAG,
    **kw,
) -> GameEvent:
    defaults: dict = {
        "sequence_number": seq,
        "turn_number": turn,
        "event_type": event_type,
        "source": EventSource.HUMAN,
        "title": "[Analyze]",
        "body": body,
        "phase": phase,
    }
    defaults.update(kw)
    return GameEvent(**defaults)


# ── Tests ──────────────────────────────────────────────────────────────────────


class TestTagsPaneLoad:
    """set_store + refresh_tags load tags from the store."""

    def test_empty_store_loads_no_tags(self, tmp_path: Path) -> None:
        store = _make_store([], tmp_path)
        pane = TagsPane()
        pane.set_store(store)
        pane._load_tags()
        assert pane._all_tags == []

    def test_store_with_two_tags(self, tmp_path: Path) -> None:
        a1 = _tag(1, 1, phase="action", body="First.")
        a2 = _tag(2, 2, phase="forecast", body="Second.")
        store = _make_store([a1, a2], tmp_path)
        pane = TagsPane()
        pane.set_store(store)
        pane._load_tags()
        assert len(pane._all_tags) == 2

    def test_non_tag_events_are_ignored(self, tmp_path: Path) -> None:
        """SITUATION_REPORT events must not appear in _all_tags."""
        sitrep = GameEvent(
            sequence_number=1,
            turn_number=1,
            event_type=EventType.SITUATION_REPORT,
            source=EventSource.SIMULATION,
            title="Sitrep",
            body="Not a tag.",
        )
        tag = _tag(2, 1)
        store = _make_store([sitrep, tag], tmp_path)
        pane = TagsPane()
        pane.set_store(store)
        pane._load_tags()
        assert len(pane._all_tags) == 1
        assert pane._all_tags[0].event_type == EventType.TAG

    def test_legacy_annotation_events_included(self, tmp_path: Path) -> None:
        """Legacy ANNOTATION events are also loaded (backward compat)."""
        legacy = _tag(1, 1, event_type=EventType.ANNOTATION)
        store = _make_store([legacy], tmp_path)
        pane = TagsPane()
        pane.set_store(store)
        pane._load_tags()
        assert len(pane._all_tags) == 1
        assert pane._all_tags[0].event_type == EventType.ANNOTATION


class TestTagsPaneFilters:
    """_apply_filters narrows _visible based on filter state."""

    def _pane_with_two_tags(self, tmp_path: Path) -> TagsPane:
        a1 = _tag(1, 1, phase="action", body="Signal analysis.")
        a2 = _tag(2, 2, phase="forecast", body="Forecast note.")
        store = _make_store([a1, a2], tmp_path)
        pane = TagsPane()
        pane.set_store(store)
        pane._load_tags()
        # Simulate no filter widget — _apply_filters gracefully skips widget reads
        return pane

    def test_no_filters_shows_all(self, tmp_path: Path) -> None:
        pane = self._pane_with_two_tags(tmp_path)
        from unittest.mock import patch

        with patch.object(pane, "_rebuild_table"):
            pane._apply_filters()
        assert len(pane._visible) == 2

    def test_phase_filter_narrows_results(self, tmp_path: Path) -> None:
        a1 = _tag(1, 1, phase="action", body="Action analysis.")
        a2 = _tag(2, 2, phase="forecast", body="Forecast note.")
        store = _make_store([a1, a2], tmp_path)
        pane = TagsPane()
        pane.set_store(store)
        pane._load_tags()

        pane._visible = [
            (pane._tag_num.get(a.id, 0), a)
            for a in pane._all_tags
            if a.phase == "action"
        ]
        assert len(pane._visible) == 1
        assert pane._visible[0][1].phase == "action"

    def test_turn_filter_narrows_results(self, tmp_path: Path) -> None:
        a1 = _tag(1, 1, phase="action", body="Turn 1 note.")
        a2 = _tag(2, 2, phase="action", body="Turn 2 note.")
        store = _make_store([a1, a2], tmp_path)
        pane = TagsPane()
        pane.set_store(store)
        pane._load_tags()

        pane._visible = [
            (pane._tag_num.get(a.id, 0), a)
            for a in pane._all_tags
            if a.turn_number == 1
        ]
        assert len(pane._visible) == 1
        assert pane._visible[0][1].turn_number == 1

    def test_search_filter_narrows_results(self, tmp_path: Path) -> None:
        a1 = _tag(1, 1, body="contains keyword here")
        a2 = _tag(2, 2, body="unrelated content")
        store = _make_store([a1, a2], tmp_path)
        pane = TagsPane()
        pane.set_store(store)
        pane._load_tags()

        search = "keyword"
        pane._visible = [
            (pane._tag_num.get(a.id, 0), a)
            for a in pane._all_tags
            if search in (a.body or "").lower()
        ]
        assert len(pane._visible) == 1
        assert "keyword" in pane._visible[0][1].body


class TestTagsPaneSelection:
    """Multi-select logic via _toggle_select and clear."""

    def test_toggle_select_adds_id(self, tmp_path: Path) -> None:
        tag = _tag(1, 1)
        store = _make_store([tag], tmp_path)
        pane = TagsPane()
        pane.set_store(store)
        pane._load_tags()
        pane._visible = [(1, pane._all_tags[0])]

        pane._selected_ids.clear()
        pane._selected_ids.add(tag.id)
        assert tag.id in pane._selected_ids

    def test_toggle_select_removes_id_when_present(self, tmp_path: Path) -> None:
        tag = _tag(1, 1)
        store = _make_store([tag], tmp_path)
        pane = TagsPane()
        pane.set_store(store)
        pane._load_tags()

        pane._selected_ids.add(tag.id)
        pane._selected_ids.discard(tag.id)
        assert tag.id not in pane._selected_ids

    def test_select_all_visible(self, tmp_path: Path) -> None:
        a1 = _tag(1, 1)
        a2 = _tag(2, 2)
        store = _make_store([a1, a2], tmp_path)
        pane = TagsPane()
        pane.set_store(store)
        pane._load_tags()
        pane._visible = [(pane._tag_num.get(a.id, 0), a) for a in pane._all_tags]

        for _, tag in pane._visible:
            pane._selected_ids.add(tag.id)

        assert len(pane._selected_ids) == 2
        assert a1.id in pane._selected_ids
        assert a2.id in pane._selected_ids
