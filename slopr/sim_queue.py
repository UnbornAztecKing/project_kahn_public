"""Simulation queue — JSONL-backed tracker of branch simulation requests.

Each running simulation gets a :class:`SimRequest` entry in the queue.
When a sim completes (COMPLETE or FAILED) the entry can be cleaned up
via :meth:`SimQueue.clear_finished`.

File layout::

    sim-kargil.jsonl              ← root event log
    sim-kargil.jsonl.branches     ← branch manifest
    sim-kargil.sims.jsonl         ← simulation queue (this module)

The queue file is a flat JSONL — one :class:`SimRequest` per line.
Writes are atomic: write to ``{path}.tmp`` then rename.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


# ── Status enum ──────────────────────────────────────────────────────────────


class SimStatus(str, Enum):
    """Lifecycle state of a queued simulation."""

    QUEUED   = "queued"
    RUNNING  = "running"
    COMPLETE = "complete"
    FAILED   = "failed"


# ── SimRequest model ─────────────────────────────────────────────────────────


class SimRequest(BaseModel):
    """One simulation run tracked by the queue."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    branch_id: str
    branch_label: str
    scenario: str
    model_a: str
    model_b: str
    turns: int
    pid: int | None = None
    status: SimStatus = SimStatus.QUEUED
    current_turn: int | None = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    completed_at: datetime | None = None


# ── SimQueue ─────────────────────────────────────────────────────────────────


class SimQueue:
    """JSONL-backed list of simulation requests.

    Parameters
    ----------
    path:
        Path to the ``*.sims.jsonl`` file.  Created on first write if it
        does not yet exist.
    """

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self._requests: list[SimRequest] = []
        if self.path.exists():
            self._load()

    # ── Class helpers ────────────────────────────────────────────────────

    @classmethod
    def path_for(cls, root_jsonl: Path) -> Path:
        """Return the conventional queue path for *root_jsonl*.

        Convention: ``{root_jsonl.stem}.sims.jsonl`` — e.g.
        ``sim-kargil.jsonl`` → ``sim-kargil.sims.jsonl``.
        """
        root_jsonl = root_jsonl.resolve()
        return root_jsonl.parent / (root_jsonl.stem + ".sims.jsonl")

    # ── Persistence ──────────────────────────────────────────────────────

    def _load(self) -> None:
        """Parse the JSONL file into in-memory request list."""
        self._requests = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    self._requests.append(SimRequest.model_validate_json(line))
                except Exception:
                    pass  # skip malformed lines

    def _save(self) -> None:
        """Atomically rewrite the queue JSONL file."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        lines = [r.model_dump_json() for r in self._requests]
        tmp.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        tmp.replace(self.path)

    # ── Queries ──────────────────────────────────────────────────────────

    def list_all(self) -> list[SimRequest]:
        """Return all requests in insertion order."""
        return list(self._requests)

    def get(self, request_id: str) -> SimRequest | None:
        """Return a single request by id, or ``None``."""
        for r in self._requests:
            if r.id == request_id:
                return r
        return None

    # ── Mutations ────────────────────────────────────────────────────────

    def add(
        self,
        branch_id: str,
        branch_label: str,
        scenario: str,
        model_a: str,
        model_b: str,
        turns: int,
    ) -> SimRequest:
        """Append a new QUEUED request and persist."""
        req = SimRequest(
            branch_id=branch_id,
            branch_label=branch_label,
            scenario=scenario,
            model_a=model_a,
            model_b=model_b,
            turns=turns,
        )
        self._requests.append(req)
        self._save()
        return req

    def update(self, request_id: str, **kwargs: Any) -> None:
        """Update fields on the request with *request_id* and persist.

        Automatically sets ``completed_at`` when status transitions to
        COMPLETE or FAILED.
        """
        for i, r in enumerate(self._requests):
            if r.id == request_id:
                update: dict[str, Any] = dict(kwargs)
                status = update.get("status")
                if status in (SimStatus.COMPLETE, SimStatus.FAILED):
                    update.setdefault("completed_at", datetime.now(timezone.utc))
                self._requests[i] = r.model_copy(update=update)
                break
        self._save()

    def clear_finished(self) -> None:
        """Remove all COMPLETE and FAILED entries and persist."""
        self._requests = [
            r for r in self._requests
            if r.status not in (SimStatus.COMPLETE, SimStatus.FAILED)
        ]
        self._save()

    def reload(self) -> None:
        """Re-read the queue file from disk (used by the poll timer)."""
        if self.path.exists():
            self._load()
