"""Append-only JSONL writer for simulation events.

Usage on the simulation side::

    writer = EventWriter(Path("runs/game_001.jsonl"))
    writer.write(event)   # fsync after each write for tail safety
    writer.close()

Or as a context manager::

    with EventWriter(path) as w:
        w.write(event)

When *path* is ``None`` the writer emits to ``sys.stdout`` (no fsync)
so events can be captured via pipe::

    python sim.py --model_a ... --model_b ... | tee game.jsonl
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from typing import IO

from slopr.models import GameEvent


class EventWriter:
    """Append-only JSONL writer.  One file per game run.

    Each ``write()`` call serialises a single :class:`GameEvent` as one JSON
    line, flushes the buffer, and — when writing to a file — calls
    ``os.fsync`` so that ``tail -f`` and inotify-based watchers see the data
    immediately.

    If *path* is ``None`` the writer streams to ``sys.stdout`` instead.
    """

    def __init__(self, path: Path | str | None = None, initial_seq: int = 0) -> None:
        self._seq: int = initial_seq
        if path is not None:
            self.path: Path | None = Path(path)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._fh: IO[str] = open(self.path, "a", encoding="utf-8")
            self._owns_fh = True
        else:
            self.path = None
            self._fh = sys.stdout
            self._owns_fh = False

    @property
    def sequence(self) -> int:
        return self._seq

    def next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def write(self, event: GameEvent) -> None:
        h = self._fh
        h.write(event.model_dump_json())
        h.write("\n")
        h.flush()
        if self._owns_fh:
            os.fsync(h.fileno())

    def close(self) -> None:
        if self._owns_fh and not self._fh.closed:
            self._fh.flush()
            self._fh.close()

    def __enter__(self) -> "EventWriter":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
