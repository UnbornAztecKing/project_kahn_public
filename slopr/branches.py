"""Branch management for Project Kahn simulations.

A *branch* is a fork of an event stream created when an analyst edits an event
and wants to explore how the simulation would have evolved from that point.

Structure
---------
Each branch is stored as a JSONL file containing all events up to and including
the fork point (copied from the parent), followed by new events from the
background simulation that continues from that fork.

The branch manifest (``{root_jsonl}.branches``) tracks the complete family
structure — all branch labels, descriptions, edited events, and parent/child
relationships.  Simulation results live only in the JSONL files.

Example file layout for ``sim-kargil.jsonl``::

    sim-kargil.jsonl                     ← root event log
    sim-kargil.jsonl.branches            ← manifest (JSON)
    sim-kargil.d-escalates-turn-3.jsonl  ← branch event log

Manifest schema:

.. code-block:: json

    {
        "root_file": "sim-kargil.jsonl",
        "branches": [
            {
                "id": "...",
                "label": "D escalates at turn 3",
                "annotation": "Testing pre-delegation trigger",
                "edited_event": { ... },
                "parent_branch_id": null,
                "parent_event_id": "...",
                "fork_turn": 3,
                "fork_sequence": 42,
                "events_file": "sim-kargil.d-escalates-turn-3.jsonl",
                "created_at": "...",
                "sim_status": "complete",
                "sim_pid": null
            }
        ]
    }

Usage
-----
::

    # Create from a root JSONL
    bs = BranchStore.init(Path("sim-kargil.jsonl"))

    # Load an existing manifest
    bs = BranchStore(Path("sim-kargil.jsonl.branches"))

    # Fork after event with id=<parent_event_id>
    entry = bs.create_branch(
        parent_branch_id=None,
        parent_event_id="<id>",
        label="D nuclear signal at turn 3",
        annotation="",
    )

    # Spawn a background simulation for this branch
    import asyncio
    proc = await bs.spawn_sim(entry.id, scenario="v11_nuclear_kargil", ...)
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sys
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

# Absolute path to sim.py (two levels up from this file: two levels up from this file: slopr/ → project root)
_SIM_SCRIPT = Path(__file__).parent.parent / "sim.py"
from typing import Any

from pydantic import BaseModel, Field

from slopr.event_writer import EventWriter
from slopr.store import JSONLEventStore

logger = logging.getLogger(__name__)


def _sanitize_label(label: str) -> str:
    """Convert a branch label to a safe, lowercase filesystem slug (max 50 chars)."""
    slug = label.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug[:50] or "branch"


# ── Data models ─────────────────────────────────────────────────────────────


class BranchStatus(str, Enum):
    """Lifecycle state of a branch simulation."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class BranchEntry(BaseModel):
    """Metadata for one branch in the manifest."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    label: str
    annotation: str = ""
    edited_event: dict[str, Any] | None = None
    """The analyst-edited event that defines this fork (stored verbatim in manifest)."""
    peer_edited_event: dict[str, Any] | None = None
    """The counterparty's edited event when forking from an A/B event group."""
    parent_branch_id: str | None = None
    """None means forked from the root stream."""
    parent_event_id: str
    """ID of the last event included in this branch (the fork point)."""
    fork_turn: int
    fork_sequence: int
    """sequence_number of the fork-point event."""
    events_file: str
    """Relative path from the manifest directory."""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sim_status: BranchStatus = BranchStatus.PENDING
    sim_pid: int | None = None


class BranchManifest(BaseModel):
    """Root manifest linking a simulation JSONL to its derived branches."""

    root_file: str
    """Relative path from the manifest directory."""
    branches: list[BranchEntry] = []


# ── BranchStore ──────────────────────────────────────────────────────────────


class BranchStore:
    """Manages a manifest file and per-branch :class:`JSONLEventStore` instances.

    Parameters
    ----------
    manifest_path:
        Path to an existing or to-be-created ``*.branches`` file.
    """

    def __init__(self, manifest_path: Path) -> None:
        self.manifest_path = manifest_path.resolve()
        self._manifest: BranchManifest | None = None
        self._stores: dict[str | None, JSONLEventStore] = {}
        # None key → root store
        if self.manifest_path.exists():
            self.load()

    # ── Initialisation ───────────────────────────────────────────────────

    @classmethod
    def init(cls, root_jsonl: Path) -> "BranchStore":
        """Create a fresh manifest alongside *root_jsonl* and return a store."""
        root_jsonl = root_jsonl.resolve()
        manifest_path = root_jsonl.parent / (root_jsonl.name + ".branches")
        manifest = BranchManifest(root_file=root_jsonl.name)
        bs = cls.__new__(cls)
        bs.manifest_path = manifest_path
        bs._manifest = manifest
        bs._stores = {None: JSONLEventStore(root_jsonl)}
        bs.save_manifest()
        return bs

    @classmethod
    def manifest_path_for(cls, root_jsonl: Path) -> Path:
        """Return the conventional manifest path for *root_jsonl*.

        Convention: ``{root_jsonl.name}.branches`` — e.g.
        ``sim-kargil.jsonl`` → ``sim-kargil.jsonl.branches``.
        """
        root_jsonl = root_jsonl.resolve()
        return root_jsonl.parent / (root_jsonl.name + ".branches")

    # ── Persistence ──────────────────────────────────────────────────────

    def load(self) -> None:
        """(Re)load the manifest and rebuild in-memory stores."""
        raw = self.manifest_path.read_text(encoding="utf-8")
        self._manifest = BranchManifest.model_validate_json(raw)
        manifest_dir = self.manifest_path.parent

        # Root store
        root_path = manifest_dir / self._manifest.root_file
        self._stores = {None: JSONLEventStore(root_path)}

        # Branch stores
        for entry in self._manifest.branches:
            branch_path = manifest_dir / entry.events_file
            self._stores[entry.id] = JSONLEventStore(branch_path)

    def save_manifest(self) -> None:
        """Write the manifest atomically (write to tmp → rename)."""
        assert self._manifest is not None
        tmp = self.manifest_path.with_name(self.manifest_path.name + ".tmp")
        tmp.write_text(
            self._manifest.model_dump_json(indent=2), encoding="utf-8"
        )
        tmp.replace(self.manifest_path)

    # ── Queries ──────────────────────────────────────────────────────────

    @property
    def manifest(self) -> BranchManifest:
        assert self._manifest is not None, "BranchStore not loaded"
        return self._manifest

    def get_store(self, branch_id: str | None = None) -> JSONLEventStore:
        """Return the event store for *branch_id* (``None`` = root)."""
        if branch_id not in self._stores:
            raise KeyError(f"No store for branch {branch_id!r}")
        return self._stores[branch_id]

    def get_entry(self, branch_id: str) -> BranchEntry:
        """Return the manifest entry for *branch_id*."""
        for entry in self.manifest.branches:
            if entry.id == branch_id:
                return entry
        raise KeyError(f"Branch {branch_id!r} not found in manifest")

    def get_jsonl_path(self, branch_id: str | None) -> Path:
        """Return the JSONL path for a branch (None = root)."""
        manifest_dir = self.manifest_path.parent
        if branch_id is None:
            return manifest_dir / self.manifest.root_file
        return manifest_dir / self.get_entry(branch_id).events_file

    def get_log_path(self, branch_id: str) -> Path:
        """Return the sim-process log path for a branch.

        Convention: ``{events_file}.log`` — e.g.
        ``sim-kargil.d-escalates.jsonl`` → ``sim-kargil.d-escalates.jsonl.log``.
        """
        return self.get_jsonl_path(branch_id).with_suffix(
            self.get_jsonl_path(branch_id).suffix + ".log"
        )

    def children_of(self, branch_id: str | None) -> list[BranchEntry]:
        """Return all direct children of *branch_id*."""
        return [e for e in self.manifest.branches if e.parent_branch_id == branch_id]

    # ── Mutation ─────────────────────────────────────────────────────────

    def create_branch(
        self,
        parent_branch_id: str | None,
        parent_event_id: str,
        label: str,
        annotation: str = "",
        edited_event: dict[str, Any] | None = None,
        peer_edited_event: dict[str, Any] | None = None,
    ) -> BranchEntry:
        """Fork a new branch from *parent_event_id* in the parent stream.

        Events up to and including *parent_event_id* are copied into the new
        JSONL file.  The new branch starts with ``sim_status=PENDING`` — call
        :meth:`spawn_sim` to run a simulation that continues from the fork.

        The branch event log is named ``{root_stem}.{label_slug}.jsonl``.
        If that file already exists a short UUID suffix is appended to
        ensure uniqueness.

        Returns the newly created :class:`BranchEntry`.
        """
        parent_store = self.get_store(parent_branch_id)
        manifest_dir = self.manifest_path.parent

        # Find the fork-point event
        fork_event = parent_store.get_event(parent_event_id)
        if fork_event is None:
            raise ValueError(f"Event {parent_event_id!r} not found in parent store")

        # Collect events up to and including the fork point (by sequence number)
        fork_seq = fork_event.sequence_number
        events_to_copy = [
            e for e in parent_store._events if e.sequence_number <= fork_seq
        ]

        # Derive a human-readable filename from the branch label
        root_stem = Path(self.manifest.root_file).stem
        label_slug = _sanitize_label(label)
        branch_filename = f"{root_stem}.{label_slug}.jsonl"
        branch_path = manifest_dir / branch_filename
        # Append a short UUID fragment if the file already exists
        if branch_path.exists():
            branch_filename = f"{root_stem}.{label_slug}-{str(uuid.uuid4())[:8]}.jsonl"
            branch_path = manifest_dir / branch_filename

        with EventWriter(branch_path) as writer:
            for evt in events_to_copy:
                writer.write(evt)

        # Patch edited events into the branch JSONL so the TUI shows the
        # analyst's version rather than the original event content.
        # edited_event["parent_id"] is the original event's ID; we match on that.
        if edited_event:
            orig_id = edited_event.get("parent_id")
            if orig_id:
                self._patch_event_by_parent_id(branch_path, orig_id, edited_event)
        if peer_edited_event:
            orig_id = peer_edited_event.get("parent_id")
            if orig_id:
                self._patch_event_by_parent_id(branch_path, orig_id, peer_edited_event)

        branch_id = str(uuid.uuid4())
        entry = BranchEntry(
            id=branch_id,
            label=label,
            annotation=annotation,
            edited_event=edited_event,
            peer_edited_event=peer_edited_event,
            parent_branch_id=parent_branch_id,
            parent_event_id=parent_event_id,
            fork_turn=fork_event.turn_number,
            fork_sequence=fork_seq,
            events_file=branch_filename,
        )
        self.manifest.branches.append(entry)
        self._stores[branch_id] = JSONLEventStore(branch_path)
        self.save_manifest()
        return entry

    def delete_branch(self, branch_id: str) -> None:
        """Remove a branch from the manifest and delete its JSONL file.

        Child branches of the deleted branch are also removed recursively.
        """
        self._delete_recursive(branch_id)
        self.save_manifest()

    def _delete_recursive(self, branch_id: str) -> None:
        for child in self.children_of(branch_id):
            self._delete_recursive(child.id)

        try:
            entry = self.get_entry(branch_id)
        except KeyError:
            return

        branch_path = self.manifest_path.parent / entry.events_file
        if branch_path.exists():
            branch_path.unlink()

        self.manifest.branches = [
            e for e in self.manifest.branches if e.id != branch_id
        ]
        self._stores.pop(branch_id, None)

    def update_status(
        self,
        branch_id: str,
        status: BranchStatus,
        pid: int | None = None,
    ) -> None:
        """Update sim_status (and optionally pid) in the manifest and persist."""
        entry = self.get_entry(branch_id)
        idx = self.manifest.branches.index(entry)
        self.manifest.branches[idx] = entry.model_copy(
            update={"sim_status": status, "sim_pid": pid}
        )
        self.save_manifest()

    def update_branch(
        self,
        branch_id: str,
        *,
        label: str | None = None,
        annotation: str | None = None,
        event_title: str | None = None,
        event_body: str | None = None,
    ) -> BranchEntry:
        """Update branch label and/or annotation and optionally its edited event.

        If *label* changes the JSONL file is renamed to match the new slug.
        If *event_title* or *event_body* are provided the ``edited_event`` field
        in the manifest is updated, and the corresponding event line in the branch
        JSONL is rewritten in-place.

        Returns the updated :class:`BranchEntry`.
        """
        entry = self.get_entry(branch_id)
        idx = next(i for i, e in enumerate(self.manifest.branches) if e.id == branch_id)
        manifest_dir = self.manifest_path.parent
        updates: dict[str, Any] = {}

        if label is not None and label != entry.label:
            old_path = manifest_dir / entry.events_file
            root_stem = Path(self.manifest.root_file).stem
            label_slug = _sanitize_label(label)
            new_filename = f"{root_stem}.{label_slug}.jsonl"
            new_path = manifest_dir / new_filename
            if new_path.exists() and new_path != old_path:
                suffix = str(uuid.uuid4())[:8]
                new_filename = f"{root_stem}.{label_slug}-{suffix}.jsonl"
                new_path = manifest_dir / new_filename
            old_path.rename(new_path)
            self._stores[branch_id] = JSONLEventStore(new_path)
            updates["label"] = label
            updates["events_file"] = new_filename
        elif label is not None:
            updates["label"] = label

        if annotation is not None:
            updates["annotation"] = annotation

        if (event_title is not None or event_body is not None) and entry.edited_event is not None:
            new_edited = dict(entry.edited_event)
            if event_title is not None:
                new_edited["title"] = event_title
            if event_body is not None:
                new_edited["body"] = event_body
            updates["edited_event"] = new_edited
            # Patch the event in the branch JSONL so the TUI shows updated content.
            event_id = new_edited.get("id")
            if event_id:
                events_file = updates.get("events_file") or entry.events_file
                branch_path = manifest_dir / events_file
                if branch_path.exists():
                    self._patch_event_in_jsonl(branch_path, event_id, new_edited)
                    # Reload the in-memory store so the TUI reflects the change.
                    self._stores[branch_id] = JSONLEventStore(branch_path)

        if updates:
            self.manifest.branches[idx] = entry.model_copy(update=updates)
            self.save_manifest()

        return self.manifest.branches[idx]

    def _patch_event_in_jsonl(
        self, path: Path, event_id: str, updated_fields: dict[str, Any]
    ) -> None:
        """Rewrite *path* replacing the event whose ``id`` matches *event_id*.

        Only the keys present in *updated_fields* are changed; all other fields
        in the matching line are preserved.
        """
        lines = path.read_text(encoding="utf-8").splitlines(keepends=False)
        new_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                data = json.loads(stripped)
                if data.get("id") == event_id:
                    data.update(updated_fields)
                new_lines.append(json.dumps(data, ensure_ascii=False))
            except Exception:
                new_lines.append(stripped)
        path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    def _patch_event_by_parent_id(
        self, path: Path, parent_id: str, edited: dict[str, Any]
    ) -> None:
        """Patch the event whose ``id`` matches *parent_id* with visible fields from *edited*.

        Used when a branch is created with an ``edited_event`` — the branch JSONL
        contains the original event (matched by its ``id`` == *parent_id*) and we
        want to update its visible title/body/source so the TUI shows the analyst's
        version rather than the original.
        """
        _VISIBLE_FIELDS = ("title", "body", "source", "source_detail", "structured_data")
        lines = path.read_text(encoding="utf-8").splitlines(keepends=False)
        new_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                data = json.loads(stripped)
                if data.get("id") == parent_id:
                    for field in _VISIBLE_FIELDS:
                        if field in edited:
                            data[field] = edited[field]
                new_lines.append(json.dumps(data, ensure_ascii=False))
            except Exception:
                new_lines.append(stripped)
        path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    def reset_branch_to_fork(self, branch_id: str) -> None:
        """Truncate the branch JSONL back to the fork point.

        Removes all post-fork events so a new sim can be spawned from the
        same fork.  Resets ``sim_status`` to ``PENDING`` and clears ``sim_pid``.
        """
        entry = self.get_entry(branch_id)
        manifest_dir = self.manifest_path.parent
        branch_path = manifest_dir / entry.events_file

        # Load fresh events from disk and keep only those up to the fork point
        fresh_store = JSONLEventStore(branch_path)
        events_to_keep = [
            e for e in fresh_store._events if e.sequence_number <= entry.fork_sequence
        ]

        # Rewrite atomically
        tmp = branch_path.with_name(branch_path.name + ".tmp")
        with EventWriter(tmp) as writer:
            for evt in events_to_keep:
                writer.write(evt)
        tmp.replace(branch_path)

        # Reload the in-memory store
        self._stores[branch_id] = JSONLEventStore(branch_path)

        # Reset status to PENDING
        idx = next(i for i, e in enumerate(self.manifest.branches) if e.id == branch_id)
        self.manifest.branches[idx] = self.manifest.branches[idx].model_copy(
            update={"sim_status": BranchStatus.PENDING, "sim_pid": None}
        )
        self.save_manifest()

    def reload_store(self, branch_id: str | None) -> None:
        """Re-read a branch JSONL from disk (used after live sim writes new events)."""
        path = self.get_jsonl_path(branch_id)
        store = JSONLEventStore(path)
        self._stores[branch_id] = store

    # ── Background simulation spawning ───────────────────────────────────

    async def spawn_sim(
        self,
        branch_id: str,
        *,
        model_a: str,
        model_b: str,
        turns: int,
        extra_args: list[str] | None = None,
    ) -> asyncio.subprocess.Process:
        """Spawn a background ``sim.py`` process continuing from *branch_id*.

        The process writes new events to the branch's JSONL file (appending
        after the copied fork events).  All game parameters (scenario, aggressor,
        state configs) are read from the existing JSONL via ``--resume-from-turn``
        so there is no risk of parameter drift between parent and branch.

        The caller is responsible for:
        - Calling :meth:`update_status` with RUNNING / COMPLETE / FAILED.
        - Starting a :class:`~slopr.tail.Tailer` on the branch JSONL so the
          TUI picks up new events in real time.

        Returns the ``asyncio.subprocess.Process`` so the caller can await it.
        """
        entry = self.get_entry(branch_id)
        branch_path = self.manifest_path.parent / entry.events_file

        cmd: list[str] = [
            sys.executable,
            str(_SIM_SCRIPT),
            "--events-file",
            str(branch_path),
            "--resume-from-turn",
            str(entry.fork_turn),
            "--model_a",
            model_a,
            "--model_b",
            model_b,
            "--turns",
            str(turns),
        ]
        if extra_args:
            cmd.extend(extra_args)

        log_path = self.get_log_path(branch_id)
        logger.info("Spawning branch sim: %s  (log: %s)", " ".join(cmd), log_path)
        log_fh = open(log_path, "w", encoding="utf-8", buffering=1)  # line-buffered
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=log_fh,
            stderr=log_fh,
            cwd=str(_SIM_SCRIPT.parent),  # run from project root so imports resolve
        )
        log_fh.close()  # subprocess inherits the fd; we can close our copy
        self.update_status(branch_id, BranchStatus.RUNNING, pid=proc.pid)
        return proc
