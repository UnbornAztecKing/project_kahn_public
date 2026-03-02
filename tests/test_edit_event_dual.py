"""Tests for the _find_peer_event logic (Feature 2).

The function lives in WargameApp but its logic is pure: given an event and
a store, return the counterparty's LLM_DECISION in the same turn/phase.
We replicate the logic here so we can test it without a running Textual app.
"""

from __future__ import annotations

from slopr.models import EventSource, EventType, GameEvent
from slopr.store import JSONLEventStore


# ── helper: replicate the _find_peer_event logic ─────────────────────────────


def _find_peer(event: GameEvent, store: JSONLEventStore) -> GameEvent | None:
    """Standalone replica of WargameApp._find_peer_event()."""
    sd = event.structured_data or {}
    side = sd.get("side")
    if side not in ("A", "B"):
        return None
    peer_side = "B" if side == "A" else "A"
    candidates = [
        e for e in store.get_events(turn=event.turn_number, limit=100)
        if e.event_type == EventType.LLM_DECISION
        and e.phase == event.phase
        and (e.structured_data or {}).get("side") == peer_side
    ]
    return candidates[0] if candidates else None


def _evt(
    seq: int,
    turn: int = 1,
    phase: str = "action",
    side: str | None = None,
    **kw: object,
) -> GameEvent:
    sd: dict = {"side": side} if side else {}
    sd.update(kw)
    return GameEvent(
        sequence_number=seq,
        turn_number=turn,
        event_type=EventType.LLM_DECISION,
        source=EventSource.LLM,
        title=f"Event {seq}",
        body="",
        phase=phase,
        structured_data=sd,
    )


def _store_with(*events: GameEvent) -> JSONLEventStore:
    store = JSONLEventStore()
    for evt in events:
        store.append(evt)
    return store


# ── tests ─────────────────────────────────────────────────────────────────────


def test_find_peer_uses_side_field() -> None:
    """_find_peer returns the B-side event when given the A-side event."""
    evt_a = _evt(1, side="A")
    evt_b = _evt(2, side="B")
    store = _store_with(evt_a, evt_b)

    peer = _find_peer(evt_a, store)
    assert peer is not None
    assert (peer.structured_data or {}).get("side") == "B"


def test_find_peer_b_finds_a() -> None:
    """_find_peer returns the A-side event when given the B-side event."""
    evt_a = _evt(1, side="A")
    evt_b = _evt(2, side="B")
    store = _store_with(evt_a, evt_b)

    peer = _find_peer(evt_b, store)
    assert peer is not None
    assert (peer.structured_data or {}).get("side") == "A"


def test_find_peer_returns_none_no_side() -> None:
    """Events without a 'side' field never get a peer."""
    evt = _evt(1)  # no side
    store = _store_with(evt)
    assert _find_peer(evt, store) is None


def test_find_peer_returns_none_no_counterpart() -> None:
    """When there is no B-side event for the A-side event, return None."""
    evt_a = _evt(1, side="A")
    store = _store_with(evt_a)
    assert _find_peer(evt_a, store) is None


def test_find_peer_respects_phase() -> None:
    """Peer must be in the same phase — a different-phase B event is not a peer."""
    evt_a = _evt(1, turn=1, phase="action",  side="A")
    evt_b = _evt(2, turn=1, phase="signal",  side="B")  # different phase
    store = _store_with(evt_a, evt_b)
    assert _find_peer(evt_a, store) is None


def test_find_peer_respects_turn() -> None:
    """Peer must be in the same turn — a different-turn B event is not a peer."""
    evt_a = _evt(1, turn=1, side="A")
    evt_b = _evt(2, turn=2, side="B")  # different turn
    store = _store_with(evt_a, evt_b)
    assert _find_peer(evt_a, store) is None


def test_find_peer_ignores_non_llm_decision() -> None:
    """Only LLM_DECISION events qualify as peers."""
    evt_a = _evt(1, side="A")
    # Create a B-side event that is NOT an LLM_DECISION
    non_llm_b = GameEvent(
        sequence_number=2,
        turn_number=1,
        event_type=EventType.STATE_CHANGE,
        source=EventSource.SIMULATION,
        title="State change",
        body="",
        phase="action",
        structured_data={"side": "B"},
    )
    store = _store_with(evt_a, non_llm_b)
    # STATE_CHANGE events should not be returned as peers
    peer = _find_peer(evt_a, store)
    if peer is not None:
        assert peer.event_type == EventType.LLM_DECISION
