"""Tail mode — poll a JSONL file for new events and push them to the store.

Uses a simple file-offset polling strategy that works reliably across
platforms, driven by Textual's ``set_interval`` timer.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from slopr.models import GameEvent
from slopr.store import JSONLEventStore

logger = logging.getLogger(__name__)


class Tailer:
    """Polls a JSONL file for new lines and feeds them to *store*.

    Call :meth:`poll` on a regular interval (e.g. via ``set_interval``).
    """

    def __init__(
        self,
        path: Path,
        store: JSONLEventStore,
        on_new_events: Callable[[], None] | None = None,
    ) -> None:
        self._path = path
        self._store = store
        self._on_new_events = on_new_events
        self._offset = path.stat().st_size if path.exists() else 0

    def poll(self) -> None:
        """Read any bytes appended since the last poll.

        Safe to call frequently — returns immediately when nothing changed.
        """
        try:
            size = self._path.stat().st_size
        except FileNotFoundError:
            return

        if size <= self._offset:
            return

        new_count = 0
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                fh.seek(self._offset)
                new_data = fh.read()
                self._offset = fh.tell()
        except Exception as exc:
            logger.warning("Failed to read new lines: %s", exc)
            return

        for line in new_data.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = GameEvent.model_validate_json(line)
                self._store.append(event)
                new_count += 1
            except Exception as exc:
                logger.warning("Skipping invalid tail line: %s", exc)

        if new_count > 0 and self._on_new_events:
            self._on_new_events()
