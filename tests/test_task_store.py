"""Tests for slopr.task_store — JSONL-backed TaskStore."""

from __future__ import annotations

from pathlib import Path

import pytest

from slopr.task_store import TaskEntry, TaskStore


# ── helpers ────────────────────────────────────────────────────────────────


def _store(tmp_path: Path) -> TaskStore:
    return TaskStore(tmp_path / "sim.jsonl.tasks.jsonl")


# ── path convention ────────────────────────────────────────────────────────


def test_path_convention(tmp_path: Path) -> None:
    """TaskStore.path_for adds .tasks.jsonl suffix to the root JSONL path."""
    root = tmp_path / "sim-kargil.jsonl"
    result = TaskStore.path_for(root)
    assert str(result).endswith(".tasks.jsonl")
    assert "sim-kargil.jsonl" in str(result)


# ── add / reload ────────────────────────────────────────────────────────────


def test_add_persists(tmp_path: Path) -> None:
    """Adding a task immediately persists it; a fresh store reloads it."""
    store = _store(tmp_path)
    entry = TaskEntry.new("Analyze this event", "Battle starts", "claude-sonnet-4-6")
    store.add(entry)

    # New store object reads from the same file
    store2 = _store(tmp_path)
    entries = store2.list_all()
    assert len(entries) == 1
    assert entries[0].task_id == entry.task_id
    assert entries[0].skill_label == "Analyze this event"
    assert entries[0].status == "running"


# ── update ─────────────────────────────────────────────────────────────────


def test_update_status(tmp_path: Path) -> None:
    """Updating a task rewrites the file; the new status is visible on reload."""
    store = _store(tmp_path)
    entry = TaskEntry.new("Escalation risk", "State A fires", "claude-opus-4-6")
    store.add(entry)

    store.update(
        entry.task_id,
        status="done",
        result="Risk is high.",
        input_tokens=100,
        output_tokens=50,
        elapsed_s=2.5,
    )

    store2 = _store(tmp_path)
    loaded = store2.get(entry.task_id)
    assert loaded is not None
    assert loaded.status == "done"
    assert loaded.result == "Risk is high."
    assert loaded.input_tokens == 100
    assert loaded.output_tokens == 50
    assert loaded.elapsed_s == 2.5


def test_update_unknown_task_id_is_noop(tmp_path: Path) -> None:
    """Updating a task_id that doesn't exist should not raise."""
    store = _store(tmp_path)
    store.update("nonexistent-id", status="done")  # no exception
    assert store.list_all() == []


# ── list_all ordering ───────────────────────────────────────────────────────


def test_list_all_ordering(tmp_path: Path) -> None:
    """list_all returns tasks in insertion order."""
    store = _store(tmp_path)
    e1 = TaskEntry.new("First command", "Event Alpha", "claude-sonnet-4-6")
    e2 = TaskEntry.new("Second command", "Event Beta", "claude-opus-4-6")
    store.add(e1)
    store.add(e2)

    entries = store.list_all()
    assert len(entries) == 2
    assert entries[0].task_id == e1.task_id
    assert entries[1].task_id == e2.task_id


# ── get ─────────────────────────────────────────────────────────────────────


def test_get_returns_entry(tmp_path: Path) -> None:
    """get() returns the exact entry by task_id."""
    store = _store(tmp_path)
    entry = TaskEntry.new("Leader psychology", "Reflection", "claude-sonnet-4-6")
    store.add(entry)

    result = store.get(entry.task_id)
    assert result is not None
    assert result.task_id == entry.task_id
    assert result.model == "claude-sonnet-4-6"


def test_get_returns_none_for_missing(tmp_path: Path) -> None:
    """get() returns None when the task_id is not found."""
    store = _store(tmp_path)
    assert store.get("not-a-real-id") is None


# ── reload ──────────────────────────────────────────────────────────────────


def test_reload_picks_up_external_changes(tmp_path: Path) -> None:
    """reload() forces re-reading from disk, picking up changes by another store."""
    store_a = _store(tmp_path)
    store_b = _store(tmp_path)

    # Prime store_b's lazy cache before store_a writes anything
    assert store_b.list_all() == []

    entry = TaskEntry.new("Compare A vs B", "Action phase", "claude-sonnet-4-6")
    store_a.add(entry)

    # store_b's in-memory cache is stale; reload forces a fresh disk read
    store_b.reload()
    loaded = store_b.list_all()
    assert len(loaded) == 1
    assert loaded[0].task_id == entry.task_id


# ── TaskEntry.new ────────────────────────────────────────────────────────────


def test_task_entry_new_defaults() -> None:
    """TaskEntry.new() creates a running task with a unique UUID."""
    e1 = TaskEntry.new("cmd", "title", "model")
    e2 = TaskEntry.new("cmd", "title", "model")
    assert e1.task_id != e2.task_id
    assert e1.status == "running"
    assert e1.elapsed_s is None
    assert e1.input_tokens == 0
    assert e1.output_tokens == 0
    assert e1.prompt == ""
    assert e1.result == ""
    assert e1.error == ""


# ── malformed lines ─────────────────────────────────────────────────────────


def test_malformed_lines_are_skipped(tmp_path: Path) -> None:
    """Corrupt lines in the backing file are silently ignored on load."""
    path = tmp_path / "sim.jsonl.tasks.jsonl"
    # Write one valid and one invalid line
    entry = TaskEntry.new("cmd", "title", "model")
    import json
    with open(path, "w") as f:
        f.write(json.dumps(entry.to_dict()) + "\n")
        f.write("not valid json{{{\n")
        f.write('{"task_id": "partial"}\n')  # missing required fields — loaded with defaults

    store = TaskStore(path)
    entries = store.list_all()
    # At least the valid entry is present
    assert any(e.task_id == entry.task_id for e in entries)
