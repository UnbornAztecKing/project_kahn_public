"""Task store — JSONL-backed persistence for LLM analysis task records.

Each task is stored as a single JSON object on a line in a ``.tasks.jsonl``
file alongside the parent simulation JSONL file.

Layout::

    {sim-name}.jsonl              ← simulation events
    {sim-name}.jsonl.tasks.jsonl  ← task records
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class TaskEntry:
    """A single analysis task record."""

    task_id: str
    """UUID4 string identifier."""
    skill_label: str
    """Human-readable name of the skill."""
    event_title: str
    """Title of the event being analysed."""
    model: str
    """Model used for the analysis call."""
    status: str
    """One of: ``running``, ``done``, ``error``."""
    created_at: str
    """ISO-8601 timestamp when the task was created."""
    elapsed_s: float | None = None
    """Wall-clock seconds from start to finish (None if still running)."""
    input_tokens: int = 0
    """Input tokens consumed by the API call."""
    output_tokens: int = 0
    """Output tokens produced by the API call."""
    prompt: str = ""
    """Full prompt text sent to the model."""
    result: str = ""
    """Full response text from the model."""
    error: str = ""
    """Error message if ``status == "error"``."""

    @classmethod
    def new(
        cls,
        skill_label: str,
        event_title: str,
        model: str,
    ) -> "TaskEntry":
        """Create a new RUNNING task with a fresh UUID."""
        return cls(
            task_id=str(uuid.uuid4()),
            skill_label=skill_label,
            event_title=event_title,
            model=model,
            status="running",
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TaskEntry":
        return cls(
            task_id=d.get("task_id", ""),
            skill_label=d.get("skill_label") or d.get("command_label", ""),
            event_title=d.get("event_title", ""),
            model=d.get("model", ""),
            status=d.get("status", "running"),
            created_at=d.get("created_at", ""),
            elapsed_s=d.get("elapsed_s"),
            input_tokens=d.get("input_tokens", 0),
            output_tokens=d.get("output_tokens", 0),
            prompt=d.get("prompt", ""),
            result=d.get("result", ""),
            error=d.get("error", ""),
        )


class TaskStore:
    """JSONL-backed store for :class:`TaskEntry` records.

    The backing file is created on first write; reads return an empty list if
    the file does not yet exist.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._entries: list[TaskEntry] = []
        self._loaded = False

    # ── Path convention ───────────────────────────────────────────────────

    @staticmethod
    def path_for(root_jsonl: Path) -> Path:
        """Return the conventional task-store path for *root_jsonl*.

        Example: ``sim-kargil.jsonl`` → ``sim-kargil.jsonl.tasks.jsonl``
        """
        return Path(str(root_jsonl) + ".tasks.jsonl")

    # ── Public API ────────────────────────────────────────────────────────

    def add(self, entry: TaskEntry) -> None:
        """Append a new task entry and persist it immediately."""
        self._ensure_loaded()
        self._entries.append(entry)
        self._append_line(entry)

    def update(self, task_id: str, **kwargs: Any) -> None:
        """Update fields on an existing entry and rewrite the store."""
        self._ensure_loaded()
        for entry in self._entries:
            if entry.task_id == task_id:
                for k, v in kwargs.items():
                    if hasattr(entry, k):
                        object.__setattr__(entry, k, v)
                break
        self._rewrite()

    def get(self, task_id: str) -> TaskEntry | None:
        """Return the entry with *task_id*, or None."""
        self._ensure_loaded()
        for entry in self._entries:
            if entry.task_id == task_id:
                return entry
        return None

    def list_all(self) -> list[TaskEntry]:
        """Return all entries in insertion order."""
        self._ensure_loaded()
        return list(self._entries)

    def reload(self) -> None:
        """Re-read the backing file from disk."""
        self._loaded = False
        self._entries.clear()
        self._ensure_loaded()

    # ── Internal ──────────────────────────────────────────────────────────

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self._path.exists():
            return
        try:
            with open(self._path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            self._entries.append(TaskEntry.from_dict(json.loads(line)))
                        except (json.JSONDecodeError, KeyError):
                            pass
        except OSError:
            pass

    def _append_line(self, entry: TaskEntry) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict()) + "\n")

    def _rewrite(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                for entry in self._entries:
                    f.write(json.dumps(entry.to_dict()) + "\n")
            tmp.replace(self._path)
        except OSError:
            tmp.unlink(missing_ok=True)
