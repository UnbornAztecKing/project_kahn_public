"""Tests for vorpal.models — Pydantic event model validation."""

from __future__ import annotations

import json

import pytest

from slopr.models import EventSource, EventType, GameEvent


class TestGameEventConstruction:
    """Basic construction and field defaults."""

    def test_minimal_construction(self) -> None:
        evt = GameEvent(
            sequence_number=1,
            turn_number=1,
            event_type=EventType.SITUATION_REPORT,
            source=EventSource.SIMULATION,
            title="Test event",
        )
        assert evt.sequence_number == 1
        assert evt.turn_number == 1
        assert evt.event_type == EventType.SITUATION_REPORT
        assert evt.source == EventSource.SIMULATION
        assert evt.title == "Test event"
        assert evt.body == ""
        assert evt.structured_data == {}
        assert evt.parent_id is None
        assert evt.phase == ""
        assert evt.source_detail == ""

    def test_id_is_auto_generated(self) -> None:
        a = GameEvent(
            sequence_number=1,
            turn_number=1,
            event_type=EventType.GAME_START,
            source=EventSource.SIMULATION,
            title="A",
        )
        b = GameEvent(
            sequence_number=2,
            turn_number=1,
            event_type=EventType.GAME_START,
            source=EventSource.SIMULATION,
            title="B",
        )
        assert a.id != b.id
        assert len(a.id) == 36  # UUID format

    def test_timestamp_auto_set(self) -> None:
        evt = GameEvent(
            sequence_number=1,
            turn_number=0,
            event_type=EventType.GAME_START,
            source=EventSource.SIMULATION,
            title="Start",
        )
        assert evt.timestamp is not None

    def test_structured_data_with_values(self) -> None:
        data = {"territory_balance": 1.5, "models": ["a", "b"]}
        evt = GameEvent(
            sequence_number=1,
            turn_number=1,
            event_type=EventType.KPI_UPDATE,
            source=EventSource.SIMULATION,
            title="KPIs",
            structured_data=data,
        )
        assert evt.structured_data["territory_balance"] == 1.5
        assert evt.structured_data["models"] == ["a", "b"]


class TestContentHash:
    """content_hash is deterministic and derived from body + sequence_number."""

    def test_hash_is_generated(self) -> None:
        evt = GameEvent(
            sequence_number=1,
            turn_number=1,
            event_type=EventType.SITUATION_REPORT,
            source=EventSource.SIMULATION,
            title="Test",
            body="Hello world",
        )
        assert len(evt.content_hash) == 16
        assert evt.content_hash != ""

    def test_hash_is_deterministic(self) -> None:
        kwargs = dict(
            sequence_number=42,
            turn_number=3,
            event_type=EventType.LLM_DECISION,
            source=EventSource.LLM,
            title="Decision",
            body="Some reasoning text",
        )
        a = GameEvent(**kwargs)
        b = GameEvent(**kwargs)
        assert a.content_hash == b.content_hash

    def test_different_body_different_hash(self) -> None:
        base = dict(
            sequence_number=1,
            turn_number=1,
            event_type=EventType.SITUATION_REPORT,
            source=EventSource.SIMULATION,
            title="Test",
        )
        a = GameEvent(body="alpha", **base)
        b = GameEvent(body="beta", **base)
        assert a.content_hash != b.content_hash

    def test_different_seq_different_hash(self) -> None:
        base = dict(
            turn_number=1,
            event_type=EventType.SITUATION_REPORT,
            source=EventSource.SIMULATION,
            title="Test",
            body="same body",
        )
        a = GameEvent(sequence_number=1, **base)
        b = GameEvent(sequence_number=2, **base)
        assert a.content_hash != b.content_hash

    def test_explicit_hash_preserved(self) -> None:
        evt = GameEvent(
            sequence_number=1,
            turn_number=1,
            event_type=EventType.SITUATION_REPORT,
            source=EventSource.SIMULATION,
            title="Test",
            content_hash="custom_hash_12345",
        )
        assert evt.content_hash == "custom_hash_12345"


class TestFrozenModel:
    """GameEvent is immutable (frozen=True)."""

    def test_cannot_set_attribute(self) -> None:
        evt = GameEvent(
            sequence_number=1,
            turn_number=1,
            event_type=EventType.SITUATION_REPORT,
            source=EventSource.SIMULATION,
            title="Test",
        )
        with pytest.raises(Exception):  # ValidationError for frozen model
            evt.title = "Modified"  # type: ignore[misc]

    def test_cannot_set_body(self) -> None:
        evt = GameEvent(
            sequence_number=1,
            turn_number=1,
            event_type=EventType.SITUATION_REPORT,
            source=EventSource.SIMULATION,
            title="Test",
        )
        with pytest.raises(Exception):
            evt.body = "changed"  # type: ignore[misc]


class TestSerialization:
    """JSON round-trip serialization via Pydantic."""

    def test_model_dump_json(self) -> None:
        evt = GameEvent(
            sequence_number=1,
            turn_number=1,
            event_type=EventType.LLM_DECISION,
            source=EventSource.LLM,
            title="Decision",
            source_detail="claude-sonnet",
            body="Reasoning here",
            structured_data={"action": "hold"},
        )
        raw = evt.model_dump_json()
        parsed = json.loads(raw)
        assert parsed["event_type"] == "llm_decision"
        assert parsed["source"] == "llm"
        assert parsed["source_detail"] == "claude-sonnet"
        assert parsed["structured_data"]["action"] == "hold"

    def test_round_trip(self) -> None:
        original = GameEvent(
            sequence_number=7,
            turn_number=3,
            phase="action",
            event_type=EventType.LLM_DECISION,
            source=EventSource.LLM,
            source_detail="gpt-5.2",
            title="State A action",
            body="Private rationale here",
            structured_data={"action_rung": "Military Posturing", "action_value": 40},
        )
        raw = original.model_dump_json()
        restored = GameEvent.model_validate_json(raw)
        assert restored.id == original.id
        assert restored.sequence_number == original.sequence_number
        assert restored.turn_number == original.turn_number
        assert restored.phase == original.phase
        assert restored.event_type == original.event_type
        assert restored.source == original.source
        assert restored.source_detail == original.source_detail
        assert restored.title == original.title
        assert restored.body == original.body
        assert restored.structured_data == original.structured_data
        assert restored.content_hash == original.content_hash

    def test_all_event_types_serialize(self) -> None:
        for et in EventType:
            evt = GameEvent(
                sequence_number=1,
                turn_number=0,
                event_type=et,
                source=EventSource.SYSTEM,
                title=et.value,
            )
            raw = evt.model_dump_json()
            restored = GameEvent.model_validate_json(raw)
            assert restored.event_type == et

    def test_all_sources_serialize(self) -> None:
        for src in EventSource:
            evt = GameEvent(
                sequence_number=1,
                turn_number=0,
                event_type=EventType.ANNOTATION,
                source=src,
                title=src.value,
            )
            raw = evt.model_dump_json()
            restored = GameEvent.model_validate_json(raw)
            assert restored.source == src


class TestValidation:
    """Pydantic validation rejects bad inputs."""

    def test_missing_required_field(self) -> None:
        with pytest.raises(Exception):
            GameEvent(turn_number=1, event_type=EventType.GAME_START, source=EventSource.SIMULATION, title="X")  # type: ignore[call-arg]

    def test_invalid_event_type(self) -> None:
        with pytest.raises(Exception):
            GameEvent(
                sequence_number=1,
                turn_number=1,
                event_type="not_a_type",  # type: ignore[arg-type]
                source=EventSource.SIMULATION,
                title="X",
            )

    def test_invalid_source(self) -> None:
        with pytest.raises(Exception):
            GameEvent(
                sequence_number=1,
                turn_number=1,
                event_type=EventType.GAME_START,
                source="bad_source",  # type: ignore[arg-type]
                title="X",
            )


class TestConftest:
    """Verify the conftest fixtures produce valid models."""

    def test_sample_event_is_valid(self, sample_event: GameEvent) -> None:
        assert sample_event.sequence_number == 1
        assert sample_event.turn_number == 1
        assert sample_event.content_hash != ""

    def test_sample_events_list_sizes(self, sample_events_list: list[GameEvent]) -> None:
        # 1 GAME_START + 5 turns * 6 events each = 31
        assert len(sample_events_list) == 31

    def test_sample_events_sequence_monotonic(self, sample_events_list: list[GameEvent]) -> None:
        seqs = [e.sequence_number for e in sample_events_list]
        assert seqs == sorted(seqs)
        assert len(set(seqs)) == len(seqs)  # all unique
