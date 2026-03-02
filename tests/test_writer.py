"""Tests for vorpal.event_writer — JSONL append-only writer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from slopr.event_writer import EventWriter
from slopr.models import EventSource, EventType, GameEvent


def _evt(seq: int, turn: int = 1, title: str = "test") -> GameEvent:
    return GameEvent(
        sequence_number=seq,
        turn_number=turn,
        event_type=EventType.SITUATION_REPORT,
        source=EventSource.SIMULATION,
        title=title,
        body=f"Body {seq}",
    )


class TestEventWriter:
    """Core write behaviour."""

    def test_creates_file(self, tmp_path: Path) -> None:
        path = tmp_path / "game.jsonl"
        with EventWriter(path) as w:
            w.write(_evt(1))
        assert path.exists()
        assert path.stat().st_size > 0

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "deep" / "nested" / "game.jsonl"
        with EventWriter(path) as w:
            w.write(_evt(1))
        assert path.exists()

    def test_each_line_is_valid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "game.jsonl"
        with EventWriter(path) as w:
            for i in range(5):
                w.write(_evt(i + 1))

        lines = path.read_text().strip().split("\n")
        assert len(lines) == 5
        for line in lines:
            parsed = json.loads(line)
            assert "event_type" in parsed
            assert "title" in parsed

    def test_lines_deserialise_to_game_event(self, tmp_path: Path) -> None:
        path = tmp_path / "game.jsonl"
        original = _evt(42, title="round-trip test")
        with EventWriter(path) as w:
            w.write(original)

        line = path.read_text().strip()
        restored = GameEvent.model_validate_json(line)
        assert restored.id == original.id
        assert restored.sequence_number == 42
        assert restored.title == "round-trip test"
        assert restored.content_hash == original.content_hash

    def test_append_mode(self, tmp_path: Path) -> None:
        path = tmp_path / "game.jsonl"
        with EventWriter(path) as w:
            w.write(_evt(1))
        with EventWriter(path) as w:
            w.write(_evt(2))

        lines = path.read_text().strip().split("\n")
        assert len(lines) == 2

    def test_next_seq(self, tmp_path: Path) -> None:
        path = tmp_path / "game.jsonl"
        with EventWriter(path) as w:
            assert w.sequence == 0
            assert w.next_seq() == 1
            assert w.next_seq() == 2
            assert w.sequence == 2


class TestContextManager:
    """Context manager cleans up correctly."""

    def test_close_on_exit(self, tmp_path: Path) -> None:
        path = tmp_path / "game.jsonl"
        w = EventWriter(path)
        w.write(_evt(1))
        assert not w._fh.closed
        w.close()
        assert w._fh.closed

    def test_with_block_closes(self, tmp_path: Path) -> None:
        path = tmp_path / "game.jsonl"
        with EventWriter(path) as w:
            fh = w._fh
            w.write(_evt(1))
        assert fh.closed

    def test_double_close_is_safe(self, tmp_path: Path) -> None:
        path = tmp_path / "game.jsonl"
        w = EventWriter(path)
        w.close()
        w.close()  # should not raise
