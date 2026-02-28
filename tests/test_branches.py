"""Unit tests for the branch management system (vorpal/branches.py)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from slopr.branches import BranchEntry, BranchManifest, BranchStatus, BranchStore
from slopr.fixtures import write_sample_game
from slopr.models import EventType


# ── Helpers ───────────────────────────────────────────────────────────────────


def _root_store_and_path(tmp_path: Path, n_turns: int = 5, seed: int = 42):
    root_path = write_sample_game(tmp_path / "root.jsonl", n_turns=n_turns, seed=seed)
    return root_path


# ── BranchStore.init ──────────────────────────────────────────────────────────


class TestInit:
    def test_creates_manifest_file(self, tmp_path: Path) -> None:
        root = _root_store_and_path(tmp_path)
        bs = BranchStore.init(root)
        assert bs.manifest_path.exists()

    def test_manifest_path_convention(self, tmp_path: Path) -> None:
        root = _root_store_and_path(tmp_path)
        bs = BranchStore.init(root)
        expected = tmp_path / "root.jsonl.branches"
        assert bs.manifest_path == expected

    def test_manifest_roundtrip(self, tmp_path: Path) -> None:
        root = _root_store_and_path(tmp_path)
        bs = BranchStore.init(root)
        raw = json.loads(bs.manifest_path.read_text())
        assert raw["root_file"] == "root.jsonl"
        assert raw["branches"] == []

    def test_root_store_has_events(self, tmp_path: Path) -> None:
        root = _root_store_and_path(tmp_path)
        bs = BranchStore.init(root)
        store = bs.get_store(None)
        assert store.event_count() > 0

    def test_load_existing_manifest(self, tmp_path: Path) -> None:
        root = _root_store_and_path(tmp_path)
        BranchStore.init(root)  # creates manifest
        # Reload from manifest path
        manifest_path = tmp_path / "root.jsonl.branches"
        bs2 = BranchStore(manifest_path)
        assert bs2.get_store(None).event_count() > 0

    def test_manifest_path_for_helper(self, tmp_path: Path) -> None:
        root = tmp_path / "game.jsonl"
        root.touch()
        expected = tmp_path / "game.jsonl.branches"
        assert BranchStore.manifest_path_for(root) == expected


# ── create_branch ─────────────────────────────────────────────────────────────


class TestCreateBranch:
    def test_creates_branch_jsonl(self, tmp_path: Path) -> None:
        root = _root_store_and_path(tmp_path)
        bs = BranchStore.init(root)
        root_store = bs.get_store()
        fork_evt = root_store.get_events(turn=2, event_type=EventType.STATE_CHANGE)[0]

        entry = bs.create_branch(
            parent_branch_id=None,
            parent_event_id=fork_evt.id,
            label="Test fork",
        )
        branch_path = tmp_path / entry.events_file
        assert branch_path.exists()

    def test_branch_has_events_up_to_fork(self, tmp_path: Path) -> None:
        root = _root_store_and_path(tmp_path)
        bs = BranchStore.init(root)
        root_store = bs.get_store()
        fork_evt = root_store.get_events(turn=2, event_type=EventType.STATE_CHANGE)[0]
        expected_count = sum(
            1 for e in root_store._events if e.sequence_number <= fork_evt.sequence_number
        )

        entry = bs.create_branch(None, fork_evt.id, "fork")
        branch_store = bs.get_store(entry.id)
        assert branch_store.event_count() == expected_count

    def test_branch_does_not_contain_events_after_fork(self, tmp_path: Path) -> None:
        root = _root_store_and_path(tmp_path)
        bs = BranchStore.init(root)
        root_store = bs.get_store()
        fork_evt = root_store.get_events(turn=2, event_type=EventType.STATE_CHANGE)[0]
        entry = bs.create_branch(None, fork_evt.id, "fork")
        branch_store = bs.get_store(entry.id)
        assert all(
            e.sequence_number <= fork_evt.sequence_number
            for e in branch_store._events
        )

    def test_branch_entry_fields(self, tmp_path: Path) -> None:
        root = _root_store_and_path(tmp_path)
        bs = BranchStore.init(root)
        root_store = bs.get_store()
        fork_evt = root_store.get_events(turn=2, event_type=EventType.STATE_CHANGE)[0]

        entry = bs.create_branch(
            None, fork_evt.id, label="My branch", annotation="some note"
        )
        assert entry.label == "My branch"
        assert entry.annotation == "some note"
        assert entry.parent_branch_id is None
        assert entry.parent_event_id == fork_evt.id
        assert entry.fork_turn == 2
        assert entry.fork_sequence == fork_evt.sequence_number
        assert entry.sim_status == BranchStatus.PENDING

    def test_branch_appears_in_manifest(self, tmp_path: Path) -> None:
        root = _root_store_and_path(tmp_path)
        bs = BranchStore.init(root)
        root_store = bs.get_store()
        fork_evt = root_store.get_events(turn=2, event_type=EventType.STATE_CHANGE)[0]
        entry = bs.create_branch(None, fork_evt.id, "fork")
        assert any(b.id == entry.id for b in bs.manifest.branches)

    def test_manifest_persisted_after_create(self, tmp_path: Path) -> None:
        root = _root_store_and_path(tmp_path)
        bs = BranchStore.init(root)
        root_store = bs.get_store()
        fork_evt = root_store.get_events(turn=2, event_type=EventType.STATE_CHANGE)[0]
        entry = bs.create_branch(None, fork_evt.id, "fork")

        # Reload manifest from disk
        raw = json.loads(bs.manifest_path.read_text())
        ids = [b["id"] for b in raw["branches"]]
        assert entry.id in ids

    def test_invalid_parent_event_id_raises(self, tmp_path: Path) -> None:
        root = _root_store_and_path(tmp_path)
        bs = BranchStore.init(root)
        with pytest.raises(ValueError, match="not found"):
            bs.create_branch(None, "nonexistent-uuid", "bad fork")


# ── Nested branches ───────────────────────────────────────────────────────────


class TestNestedBranches:
    def test_create_child_of_child(self, tmp_path: Path) -> None:
        root = _root_store_and_path(tmp_path, n_turns=8)
        bs = BranchStore.init(root)
        root_store = bs.get_store()
        fork_evt1 = root_store.get_events(turn=3, event_type=EventType.STATE_CHANGE)[0]
        branch1 = bs.create_branch(None, fork_evt1.id, "Branch 1")

        branch1_store = bs.get_store(branch1.id)
        fork_evt2 = branch1_store.get_events(turn=2, event_type=EventType.STATE_CHANGE)[0]
        branch2 = bs.create_branch(branch1.id, fork_evt2.id, "Branch 2")

        assert branch2.parent_branch_id == branch1.id
        assert branch2.id in [e.id for e in bs.manifest.branches]

    def test_children_of(self, tmp_path: Path) -> None:
        root = _root_store_and_path(tmp_path)
        bs = BranchStore.init(root)
        root_store = bs.get_store()
        fork_evt = root_store.get_events(turn=2, event_type=EventType.STATE_CHANGE)[0]
        b1 = bs.create_branch(None, fork_evt.id, "B1")
        b2 = bs.create_branch(None, fork_evt.id, "B2")

        children = bs.children_of(None)
        ids = [c.id for c in children]
        assert b1.id in ids
        assert b2.id in ids


# ── delete_branch ─────────────────────────────────────────────────────────────


class TestDeleteBranch:
    def test_deletes_jsonl_file(self, tmp_path: Path) -> None:
        root = _root_store_and_path(tmp_path)
        bs = BranchStore.init(root)
        root_store = bs.get_store()
        fork_evt = root_store.get_events(turn=2, event_type=EventType.STATE_CHANGE)[0]
        entry = bs.create_branch(None, fork_evt.id, "to delete")
        branch_path = tmp_path / entry.events_file

        bs.delete_branch(entry.id)

        assert not branch_path.exists()

    def test_removes_from_manifest(self, tmp_path: Path) -> None:
        root = _root_store_and_path(tmp_path)
        bs = BranchStore.init(root)
        root_store = bs.get_store()
        fork_evt = root_store.get_events(turn=2, event_type=EventType.STATE_CHANGE)[0]
        entry = bs.create_branch(None, fork_evt.id, "to delete")
        bs.delete_branch(entry.id)

        assert not any(b.id == entry.id for b in bs.manifest.branches)

    def test_deletes_children_recursively(self, tmp_path: Path) -> None:
        root = _root_store_and_path(tmp_path, n_turns=8)
        bs = BranchStore.init(root)
        root_store = bs.get_store()
        fork_evt = root_store.get_events(turn=3, event_type=EventType.STATE_CHANGE)[0]
        parent = bs.create_branch(None, fork_evt.id, "Parent")
        parent_store = bs.get_store(parent.id)
        fork_evt2 = parent_store.get_events(turn=2, event_type=EventType.STATE_CHANGE)[0]
        child = bs.create_branch(parent.id, fork_evt2.id, "Child")

        bs.delete_branch(parent.id)

        assert not any(b.id == parent.id for b in bs.manifest.branches)
        assert not any(b.id == child.id for b in bs.manifest.branches)


# ── update_status ─────────────────────────────────────────────────────────────


class TestUpdateStatus:
    def test_persists_status(self, tmp_path: Path) -> None:
        root = _root_store_and_path(tmp_path)
        bs = BranchStore.init(root)
        root_store = bs.get_store()
        fork_evt = root_store.get_events(turn=2, event_type=EventType.STATE_CHANGE)[0]
        entry = bs.create_branch(None, fork_evt.id, "fork")

        bs.update_status(entry.id, BranchStatus.COMPLETE)

        raw = json.loads(bs.manifest_path.read_text())
        found = next(b for b in raw["branches"] if b["id"] == entry.id)
        assert found["sim_status"] == "complete"

    def test_persists_pid(self, tmp_path: Path) -> None:
        root = _root_store_and_path(tmp_path)
        bs = BranchStore.init(root)
        root_store = bs.get_store()
        fork_evt = root_store.get_events(turn=2, event_type=EventType.STATE_CHANGE)[0]
        entry = bs.create_branch(None, fork_evt.id, "fork")

        bs.update_status(entry.id, BranchStatus.RUNNING, pid=12345)

        raw = json.loads(bs.manifest_path.read_text())
        found = next(b for b in raw["branches"] if b["id"] == entry.id)
        assert found["sim_pid"] == 12345


# ── Manifest roundtrip ────────────────────────────────────────────────────────


class TestManifestRoundtrip:
    def test_reload_preserves_all_fields(self, tmp_path: Path) -> None:
        root = _root_store_and_path(tmp_path)
        bs = BranchStore.init(root)
        root_store = bs.get_store()
        fork_evt = root_store.get_events(turn=2, event_type=EventType.STATE_CHANGE)[0]
        entry = bs.create_branch(
            None, fork_evt.id, label="Reload test", annotation="An annotation"
        )

        # Reload from disk
        bs2 = BranchStore(bs.manifest_path)
        reloaded = bs2.get_entry(entry.id)
        assert reloaded.label == "Reload test"
        assert reloaded.annotation == "An annotation"
        assert reloaded.fork_turn == entry.fork_turn
        assert reloaded.fork_sequence == entry.fork_sequence
        assert reloaded.parent_branch_id is None
        assert reloaded.sim_status == BranchStatus.PENDING

    def test_reload_restores_store(self, tmp_path: Path) -> None:
        root = _root_store_and_path(tmp_path)
        bs = BranchStore.init(root)
        root_store = bs.get_store()
        fork_evt = root_store.get_events(turn=2, event_type=EventType.STATE_CHANGE)[0]
        entry = bs.create_branch(None, fork_evt.id, "fork")
        original_count = bs.get_store(entry.id).event_count()

        bs2 = BranchStore(bs.manifest_path)
        assert bs2.get_store(entry.id).event_count() == original_count


# ── get_store ─────────────────────────────────────────────────────────────────


class TestGetStore:
    def test_root_store_independent_of_branch(self, tmp_path: Path) -> None:
        root = _root_store_and_path(tmp_path)
        bs = BranchStore.init(root)
        root_store = bs.get_store()
        fork_evt = root_store.get_events(turn=2, event_type=EventType.STATE_CHANGE)[0]
        entry = bs.create_branch(None, fork_evt.id, "fork")

        rs = bs.get_store(None)
        bs2 = bs.get_store(entry.id)
        # Root has more events than branch
        assert rs.event_count() > bs2.event_count()

    def test_unknown_branch_raises(self, tmp_path: Path) -> None:
        root = _root_store_and_path(tmp_path)
        bs = BranchStore.init(root)
        with pytest.raises(KeyError):
            bs.get_store("nonexistent-uuid")


# ── Two-branch fixture roundtrip ──────────────────────────────────────────────


class TestBranchedStoreFixture:
    """Exercises the shared `branched_store` fixture from conftest."""

    def test_fixture_has_one_branch(self, branched_store) -> None:
        bs, entry = branched_store
        assert len(bs.manifest.branches) == 1
        assert bs.manifest.branches[0].id == entry.id

    def test_root_has_more_events_than_branch(self, branched_store) -> None:
        bs, entry = branched_store
        assert bs.get_store(None).event_count() > bs.get_store(entry.id).event_count()

    def test_branch_label_preserved(self, branched_store) -> None:
        bs, entry = branched_store
        assert entry.label == "Test branch"
        assert entry.annotation == "Created in fixture"
