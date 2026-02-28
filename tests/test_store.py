"""Tests for vorpal.store — EventStore ABC + JSONLEventStore."""

from __future__ import annotations

from pathlib import Path

import pytest

from slopr.event_writer import EventWriter
from slopr.models import EventSource, EventType, GameEvent
from slopr.store import JSONLEventStore


def _evt(seq: int, turn: int, **kw: object) -> GameEvent:
    defaults: dict = {
        "sequence_number": seq,
        "turn_number": turn,
        "event_type": EventType.SITUATION_REPORT,
        "source": EventSource.SIMULATION,
        "title": f"Event {seq}",
        "body": f"Body for event {seq}",
    }
    defaults.update(kw)
    return GameEvent(**defaults)


class TestJSONLEventStoreLoad:
    """Loading from JSONL files."""

    def test_loads_from_file(self, jsonl_file: Path) -> None:
        store = JSONLEventStore(jsonl_file)
        assert store.event_count() > 0

    def test_empty_file(self, empty_jsonl_file: Path) -> None:
        store = JSONLEventStore(empty_jsonl_file)
        assert store.event_count() == 0
        assert store.get_turn_numbers() == []
        assert store.get_latest_sequence() == 0

    def test_nonexistent_path(self, tmp_path: Path) -> None:
        store = JSONLEventStore(tmp_path / "nope.jsonl")
        assert store.event_count() == 0

    def test_no_path(self) -> None:
        store = JSONLEventStore()
        assert store.event_count() == 0


class TestRoundTrip:
    """Write events → load into store → query."""

    def test_write_then_load(self, tmp_path: Path) -> None:
        path = tmp_path / "game.jsonl"
        events = [_evt(i + 1, turn=1) for i in range(5)]
        with EventWriter(path) as w:
            for e in events:
                w.write(e)

        store = JSONLEventStore(path)
        assert store.event_count() == 5
        for e in events:
            loaded = store.get_event(e.id)
            assert loaded is not None
            assert loaded.title == e.title

    def test_large_event_set(self, tmp_path: Path) -> None:
        path = tmp_path / "big.jsonl"
        n = 500
        with EventWriter(path) as w:
            for i in range(n):
                w.write(_evt(i + 1, turn=(i // 10) + 1))
        store = JSONLEventStore(path)
        assert store.event_count() == n
        assert len(store.get_turn_numbers()) == 50  # 500 events / 10 per turn


class TestGetEvents:
    """Filtered retrieval."""

    def test_filter_by_turn(self, sample_events_list: list[GameEvent], jsonl_file: Path) -> None:
        store = JSONLEventStore(jsonl_file)
        turn_3 = store.get_events(turn=3)
        assert all(e.turn_number == 3 for e in turn_3)
        assert len(turn_3) > 0

    def test_filter_by_event_type(self, jsonl_file: Path) -> None:
        store = JSONLEventStore(jsonl_file)
        llm_events = store.get_events(event_type=EventType.LLM_DECISION)
        assert all(e.event_type == EventType.LLM_DECISION for e in llm_events)
        assert len(llm_events) > 0

    def test_filter_by_source(self, jsonl_file: Path) -> None:
        store = JSONLEventStore(jsonl_file)
        llm_sourced = store.get_events(source=EventSource.LLM)
        assert all(e.source == EventSource.LLM for e in llm_sourced)

    def test_filter_combined(self, jsonl_file: Path) -> None:
        store = JSONLEventStore(jsonl_file)
        result = store.get_events(turn=2, event_type=EventType.LLM_DECISION)
        assert all(e.turn_number == 2 and e.event_type == EventType.LLM_DECISION for e in result)

    def test_pagination(self, jsonl_file: Path) -> None:
        store = JSONLEventStore(jsonl_file)
        all_events = store.get_events(limit=1000)
        page_1 = store.get_events(limit=5, offset=0)
        page_2 = store.get_events(limit=5, offset=5)
        assert len(page_1) == 5
        assert page_1[0].id == all_events[0].id
        assert page_2[0].id == all_events[5].id


class TestTurnNumbers:
    """Distinct turn listing."""

    def test_sorted_ascending(self, jsonl_file: Path) -> None:
        store = JSONLEventStore(jsonl_file)
        turns = store.get_turn_numbers()
        assert turns == sorted(turns)

    def test_includes_turn_zero(self, jsonl_file: Path) -> None:
        store = JSONLEventStore(jsonl_file)
        turns = store.get_turn_numbers()
        assert 0 in turns  # GAME_START is turn 0

    def test_expected_turns(self, jsonl_file: Path) -> None:
        store = JSONLEventStore(jsonl_file)
        turns = store.get_turn_numbers()
        assert turns == [0, 1, 2, 3, 4, 5]


class TestTurnSummary:
    """Aggregated turn information."""

    def test_event_count(self, jsonl_file: Path) -> None:
        store = JSONLEventStore(jsonl_file)
        summary = store.get_turn_summary(1)
        assert summary["turn"] == 1
        assert summary["event_count"] > 0

    def test_has_llm_flag(self, jsonl_file: Path) -> None:
        store = JSONLEventStore(jsonl_file)
        summary = store.get_turn_summary(1)
        assert summary["has_llm"] is True

    def test_has_edit_flag_false(self, jsonl_file: Path) -> None:
        store = JSONLEventStore(jsonl_file)
        summary = store.get_turn_summary(1)
        assert summary["has_edit"] is False

    def test_nonexistent_turn(self, jsonl_file: Path) -> None:
        store = JSONLEventStore(jsonl_file)
        summary = store.get_turn_summary(999)
        assert summary["event_count"] == 0


class TestSearch:
    """Substring search."""

    def test_finds_by_title(self, jsonl_file: Path) -> None:
        store = JSONLEventStore(jsonl_file)
        results = store.search("Reflection")
        assert len(results) > 0
        assert all("reflection" in e.title.lower() for e in results)

    def test_finds_by_body(self, jsonl_file: Path) -> None:
        store = JSONLEventStore(jsonl_file)
        results = store.search("Territory balance")
        assert len(results) > 0

    def test_case_insensitive(self, jsonl_file: Path) -> None:
        store = JSONLEventStore(jsonl_file)
        lower = store.search("reflection")
        upper = store.search("REFLECTION")
        assert len(lower) == len(upper)

    def test_no_results(self, jsonl_file: Path) -> None:
        store = JSONLEventStore(jsonl_file)
        results = store.search("zzz_nonexistent_query_zzz")
        assert results == []

    def test_respects_limit(self, jsonl_file: Path) -> None:
        store = JSONLEventStore(jsonl_file)
        results = store.search("Event", limit=2)
        assert len(results) <= 2


class TestLatestSequence:
    """Sequence tracking."""

    def test_tracks_max(self, jsonl_file: Path) -> None:
        store = JSONLEventStore(jsonl_file)
        assert store.get_latest_sequence() > 0

    def test_zero_on_empty(self, empty_jsonl_file: Path) -> None:
        store = JSONLEventStore(empty_jsonl_file)
        assert store.get_latest_sequence() == 0


class TestAppend:
    """Incremental updates (used for tail mode)."""

    def test_append_increments_count(self) -> None:
        store = JSONLEventStore()
        assert store.event_count() == 0
        store.append(_evt(1, turn=1))
        assert store.event_count() == 1
        store.append(_evt(2, turn=1))
        assert store.event_count() == 2

    def test_append_updates_index(self) -> None:
        store = JSONLEventStore()
        evt = _evt(1, turn=5)
        store.append(evt)
        assert store.get_event(evt.id) is not None
        assert 5 in store.get_turn_numbers()
        assert store.get_latest_sequence() == 1
