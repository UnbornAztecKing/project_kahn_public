"""Shared test fixtures for wargame TUI tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from slopr.branches import BranchStore
from slopr.fixtures import write_sample_game
from slopr.models import EventSource, EventType, GameEvent
from slopr.store import JSONLEventStore


def _make_event(
    seq: int,
    turn: int,
    event_type: EventType = EventType.SITUATION_REPORT,
    source: EventSource = EventSource.SIMULATION,
    **overrides: object,
) -> GameEvent:
    defaults: dict = {
        "sequence_number": seq,
        "turn_number": turn,
        "event_type": event_type,
        "source": source,
        "title": f"Event {seq}",
        "body": f"Body for event {seq}",
    }
    defaults.update(overrides)
    return GameEvent(**defaults)


@pytest.fixture()
def sample_event() -> GameEvent:
    """A single valid GameEvent."""
    return _make_event(seq=1, turn=1)


@pytest.fixture()
def sample_events_list() -> list[GameEvent]:
    """A 5-turn game with realistic event progression."""
    events: list[GameEvent] = []
    seq = 0

    # Turn 0: game start
    seq += 1
    events.append(
        _make_event(
            seq=seq,
            turn=0,
            event_type=EventType.GAME_START,
            source=EventSource.SIMULATION,
            title="Game started",
            body="claude-sonnet vs gpt-5.2, scenario=v7_alliance",
            structured_data={
                "state_a_model": "claude-sonnet-4-20250514",
                "state_b_model": "gpt-5.2",
                "scenario_key": "v7_alliance",
            },
        )
    )

    for turn in range(1, 6):
        # Phase transition
        seq += 1
        events.append(
            _make_event(
                seq=seq,
                turn=turn,
                event_type=EventType.PHASE_TRANSITION,
                source=EventSource.SYSTEM,
                phase="reflection",
                title="Phase 1: Reflection",
            )
        )
        # LLM decisions (2 per turn: one per side)
        for side in ("A", "B"):
            seq += 1
            events.append(
                _make_event(
                    seq=seq,
                    turn=turn,
                    event_type=EventType.LLM_DECISION,
                    source=EventSource.LLM,
                    phase="reflection",
                    source_detail=f"model_{side.lower()}",
                    title=f"State {side} reflection",
                    structured_data={"side": side, "phase": "reflection"},
                )
            )
        # State change
        seq += 1
        events.append(
            _make_event(
                seq=seq,
                turn=turn,
                event_type=EventType.STATE_CHANGE,
                source=EventSource.SIMULATION,
                title="Territory and military update",
                structured_data={
                    "territory_balance": round(0.15 * turn, 2),
                    "territory_change": 0.15,
                },
            )
        )
        # KPI update
        seq += 1
        events.append(
            _make_event(
                seq=seq,
                turn=turn,
                event_type=EventType.KPI_UPDATE,
                source=EventSource.SIMULATION,
                title=f"Turn {turn} KPIs",
                structured_data={
                    "territory_balance": round(0.15 * turn, 2),
                    "a_conventional_power": max(0.5, 1.0 - 0.05 * turn),
                    "b_conventional_power": max(0.5, 1.0 - 0.03 * turn),
                },
            )
        )
        # Situation report
        seq += 1
        events.append(
            _make_event(
                seq=seq,
                turn=turn,
                event_type=EventType.SITUATION_REPORT,
                source=EventSource.SIMULATION,
                title=f"Turn {turn} summary",
                body=f"Turn {turn} completed. Territory balance: {0.15 * turn:.2f}",
            )
        )

    return events


@pytest.fixture()
def jsonl_file(sample_events_list: list[GameEvent], tmp_path: Path) -> Path:
    """Write sample events to a temporary JSONL file."""
    path = tmp_path / "test_game.jsonl"
    with open(path, "w") as f:
        for event in sample_events_list:
            f.write(event.model_dump_json() + "\n")
    return path


@pytest.fixture()
def empty_jsonl_file(tmp_path: Path) -> Path:
    """An empty JSONL file for edge-case testing."""
    path = tmp_path / "empty_game.jsonl"
    path.touch()
    return path


@pytest.fixture()
def demo_jsonl(tmp_path: Path) -> Path:
    """Generate a 5-turn demo JSONL file (shared across test modules)."""
    return write_sample_game(tmp_path / "demo.jsonl", n_turns=5)


@pytest.fixture()
def demo_store(demo_jsonl: Path) -> JSONLEventStore:
    """Return a JSONLEventStore loaded from the demo JSONL file."""
    return JSONLEventStore(demo_jsonl)


@pytest.fixture()
def branched_store(tmp_path: Path):
    """Root JSONL (5-turn game) + one child branch, linked by a manifest.

    Returns ``(BranchStore, BranchEntry)`` where the entry is forked after the
    first STATE_CHANGE event in turn 2.
    """
    root = write_sample_game(tmp_path / "root.jsonl", n_turns=5, seed=1)
    bs = BranchStore.init(root)
    root_store = bs.get_store(None)
    fork_evt = root_store.get_events(turn=2, event_type=EventType.STATE_CHANGE)[0]
    entry = bs.create_branch(
        parent_branch_id=None,
        parent_event_id=fork_evt.id,
        label="Test branch",
        annotation="Created in fixture",
    )
    return bs, entry
