"""Event stores — read interface over JSONL event streams.

The TUI depends only on the :class:`EventStore` ABC.  The concrete
:class:`JSONLEventStore` reads a JSONL file into an in-memory index and is
fast enough for games under ~10 000 events.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from collections import defaultdict
from pathlib import Path
from typing import Optional

from slopr.models import EventSource, EventType, GameEvent

logger = logging.getLogger(__name__)


class EventStore(ABC):
    """Read interface over the event stream.  TUI depends only on this."""

    @abstractmethod
    def get_event(self, event_id: str) -> GameEvent | None:
        """Return event by id, or ``None`` if not found."""
        ...

    @abstractmethod
    def get_events(
        self,
        turn: Optional[int] = None,
        event_type: Optional[EventType] = None,
        source: Optional[EventSource] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[GameEvent]:
        """Filtered, paginated event retrieval."""
        ...

    @abstractmethod
    def get_turn_numbers(self) -> list[int]:
        """Distinct turn numbers in ascending order."""
        ...

    @abstractmethod
    def get_turn_summary(self, turn: int) -> dict:
        """Aggregate info for sidebar display.

        Returns a dict with keys: ``turn``, ``event_count``, ``has_llm``,
        ``has_edit``, ``phases``.
        """
        ...

    @abstractmethod
    def search(self, query: str, limit: int = 50) -> list[GameEvent]:
        """Case-insensitive substring search across event titles and bodies."""
        ...

    @abstractmethod
    def get_latest_sequence(self) -> int:
        """Highest sequence number seen — used for tail polling."""
        ...

    @abstractmethod
    def event_count(self) -> int:
        """Total number of events in the store."""
        ...

    @abstractmethod
    def append_event(self, event: "GameEvent") -> None:
        """Persist *event* to the backing store and update the in-memory index."""
        ...

    @abstractmethod
    def get_tags_for(self, event_id: str) -> "list[GameEvent]":
        """Return all TAG (and legacy ANNOTATION) events whose ``parent_id`` equals *event_id*."""
        ...


class JSONLEventStore(EventStore):
    """Reads directly from a JSONL file and builds an in-memory index.

    For games < 10 000 events this is fast enough.  For larger games a future
    ``SQLiteCacheStore`` can wrap this with FTS5 indexing.
    """

    def __init__(self, path: Path | str | None = None) -> None:
        self._events: list[GameEvent] = []
        self._by_id: dict[str, GameEvent] = {}
        self._by_turn: dict[int, list[GameEvent]] = defaultdict(list)
        self._max_seq: int = 0
        self._path: Path | None = None

        if path is not None:
            self.load(Path(path))

    # ── Loading ─────────────────────────────────────────────────────────

    def load(self, path: Path) -> None:
        """Parse every line of *path* and rebuild the in-memory index."""
        self._path = path
        self._events.clear()
        self._by_id.clear()
        self._by_turn.clear()
        self._max_seq = 0

        if not path.exists() or path.stat().st_size == 0:
            return

        with open(path, "r", encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    event = GameEvent.model_validate_json(line)
                    self._index(event)
                except Exception as exc:
                    logger.warning("Skipping invalid JSONL line %d: %s", lineno, exc)

    def reload(self) -> None:
        """Re-read the backing file from disk, refreshing the in-memory index.

        Used after a background sim completes to pick up newly written events.
        """
        if self._path is not None and self._path.exists():
            self.load(self._path)

    def append(self, event: GameEvent) -> None:
        """Add a single event (used for incremental tail updates).

        Skips events whose ID is already indexed to avoid duplicates when
        ``append_event`` writes to disk and the Tailer subsequently re-reads
        the same bytes.
        """
        if event.id not in self._by_id:
            self._index(event)

    def _index(self, event: GameEvent) -> None:
        self._events.append(event)
        self._by_id[event.id] = event
        self._by_turn[event.turn_number].append(event)
        if event.sequence_number > self._max_seq:
            self._max_seq = event.sequence_number

    # ── Query interface ─────────────────────────────────────────────────

    def get_event(self, event_id: str) -> GameEvent | None:
        return self._by_id.get(event_id)

    def get_events(
        self,
        turn: Optional[int] = None,
        event_type: Optional[EventType] = None,
        source: Optional[EventSource] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[GameEvent]:
        candidates = self._by_turn[turn] if turn is not None else self._events
        result: list[GameEvent] = []
        for evt in candidates:
            if event_type is not None and evt.event_type != event_type:
                continue
            if source is not None and evt.source != source:
                continue
            result.append(evt)
        return result[offset : offset + limit]

    def get_turn_numbers(self) -> list[int]:
        return sorted(self._by_turn.keys())

    def get_turn_summary(self, turn: int) -> dict:
        events = self._by_turn.get(turn, [])
        phases: set[str] = set()
        has_llm = False
        has_edit = False
        for evt in events:
            if evt.phase:
                phases.add(evt.phase)
            if evt.source == EventSource.LLM:
                has_llm = True
            if evt.source == EventSource.HUMAN:
                has_edit = True
        return {
            "turn": turn,
            "event_count": len(events),
            "has_llm": has_llm,
            "has_edit": has_edit,
            "phases": sorted(phases),
        }

    def search(self, query: str, limit: int = 50) -> list[GameEvent]:
        q = query.lower()
        results: list[GameEvent] = []
        for evt in self._events:
            if q in evt.title.lower() or q in evt.body.lower():
                results.append(evt)
                if len(results) >= limit:
                    break
        return results

    def get_latest_sequence(self) -> int:
        return self._max_seq

    def event_count(self) -> int:
        return len(self._events)

    def append_event(self, event: GameEvent) -> None:
        """Append *event* to the JSONL file and update the in-memory index.

        Raises :class:`RuntimeError` if no backing file has been loaded.
        """
        if self._path is None:
            raise RuntimeError("JSONLEventStore has no backing path; call load() first")
        from slopr.event_writer import EventWriter  # lazy import to avoid cycle

        with EventWriter(self._path) as writer:
            writer.write(event)
        self._index(event)

    def get_tags_for(self, event_id: str) -> list[GameEvent]:
        """Return all TAG and legacy ANNOTATION events whose ``parent_id`` equals *event_id*."""
        return [
            e for e in self._events
            if e.event_type in (EventType.TAG, EventType.ANNOTATION) and e.parent_id == event_id
        ]
