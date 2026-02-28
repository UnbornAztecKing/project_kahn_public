"""Unit tests for vorpal.sim_queue."""

from __future__ import annotations

from pathlib import Path

import pytest

from slopr.sim_queue import SimQueue, SimRequest, SimStatus


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_queue(tmp_path: Path) -> SimQueue:
    return SimQueue(tmp_path / "sim.sims.jsonl")


def _add_one(q: SimQueue, label: str = "test", branch_id: str = "b1") -> SimRequest:
    return q.add(
        branch_id=branch_id,
        branch_label=label,
        scenario="v11_nuclear_kargil",
        model_a="claude-sonnet-4-6",
        model_b="gpt-5.2",
        turns=10,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestSimQueueAdd:
    def test_add_creates_entry(self, tmp_path: Path) -> None:
        q = _make_queue(tmp_path)
        req = _add_one(q)
        assert req.status == SimStatus.QUEUED
        assert req.branch_id == "b1"
        assert req.branch_label == "test"
        assert req.turns == 10

    def test_add_creates_file(self, tmp_path: Path) -> None:
        q = _make_queue(tmp_path)
        _add_one(q)
        assert q.path.exists()

    def test_add_multiple_entries(self, tmp_path: Path) -> None:
        q = _make_queue(tmp_path)
        _add_one(q, label="first",  branch_id="b1")
        _add_one(q, label="second", branch_id="b2")
        assert len(q.list_all()) == 2


class TestSimQueueUpdate:
    def test_update_status(self, tmp_path: Path) -> None:
        q = _make_queue(tmp_path)
        req = _add_one(q)
        q.update(req.id, status=SimStatus.RUNNING, pid=12345)
        updated = q.get(req.id)
        assert updated is not None
        assert updated.status == SimStatus.RUNNING
        assert updated.pid == 12345

    def test_update_persists_to_disk(self, tmp_path: Path) -> None:
        q = _make_queue(tmp_path)
        req = _add_one(q)
        q.update(req.id, status=SimStatus.COMPLETE)
        # Reload from disk
        q2 = SimQueue(q.path)
        updated = q2.get(req.id)
        assert updated is not None
        assert updated.status == SimStatus.COMPLETE

    def test_update_sets_completed_at_on_terminal(self, tmp_path: Path) -> None:
        q = _make_queue(tmp_path)
        req = _add_one(q)
        q.update(req.id, status=SimStatus.COMPLETE)
        updated = q.get(req.id)
        assert updated is not None
        assert updated.completed_at is not None

    def test_update_nonexistent_is_noop(self, tmp_path: Path) -> None:
        q = _make_queue(tmp_path)
        # Should not raise
        q.update("nonexistent-id", status=SimStatus.RUNNING)


class TestSimQueueClearFinished:
    def test_clear_removes_complete(self, tmp_path: Path) -> None:
        q = _make_queue(tmp_path)
        req = _add_one(q)
        q.update(req.id, status=SimStatus.COMPLETE)
        q.clear_finished()
        assert q.list_all() == []

    def test_clear_removes_failed(self, tmp_path: Path) -> None:
        q = _make_queue(tmp_path)
        req = _add_one(q)
        q.update(req.id, status=SimStatus.FAILED)
        q.clear_finished()
        assert q.list_all() == []

    def test_clear_keeps_running(self, tmp_path: Path) -> None:
        q = _make_queue(tmp_path)
        req = _add_one(q)
        q.update(req.id, status=SimStatus.RUNNING)
        q.clear_finished()
        assert len(q.list_all()) == 1

    def test_clear_keeps_queued(self, tmp_path: Path) -> None:
        q = _make_queue(tmp_path)
        _add_one(q)
        q.clear_finished()
        assert len(q.list_all()) == 1

    def test_clear_mixed(self, tmp_path: Path) -> None:
        q = _make_queue(tmp_path)
        r1 = _add_one(q, label="done",    branch_id="b1")
        r2 = _add_one(q, label="running", branch_id="b2")
        r3 = _add_one(q, label="queued",  branch_id="b3")
        q.update(r1.id, status=SimStatus.COMPLETE)
        q.update(r2.id, status=SimStatus.RUNNING)
        q.clear_finished()
        remaining_ids = {r.id for r in q.list_all()}
        assert r2.id in remaining_ids
        assert r3.id in remaining_ids
        assert r1.id not in remaining_ids


class TestSimQueuePathFor:
    def test_path_convention(self, tmp_path: Path) -> None:
        root = tmp_path / "sim-kargil.jsonl"
        path = SimQueue.path_for(root)
        assert path.name == "sim-kargil.sims.jsonl"
        assert path.parent == tmp_path

    def test_path_different_stem(self, tmp_path: Path) -> None:
        root = tmp_path / "run_alpha.jsonl"
        path = SimQueue.path_for(root)
        assert path.name == "run_alpha.sims.jsonl"


class TestSimQueueRoundtrip:
    def test_jsonl_roundtrip(self, tmp_path: Path) -> None:
        q = _make_queue(tmp_path)
        req = _add_one(q)
        q.update(req.id, status=SimStatus.RUNNING, pid=99)
        # Reload from scratch
        q2 = SimQueue(q.path)
        reloaded = q2.get(req.id)
        assert reloaded is not None
        assert reloaded.status == SimStatus.RUNNING
        assert reloaded.pid == 99
        assert reloaded.scenario == req.scenario
        assert reloaded.model_a == req.model_a

    def test_multiple_requests_ordered(self, tmp_path: Path) -> None:
        q = _make_queue(tmp_path)
        labels = ["alpha", "beta", "gamma"]
        for label in labels:
            _add_one(q, label=label, branch_id=label)
        all_labels = [r.branch_label for r in q.list_all()]
        assert all_labels == labels


class TestSimQueueGet:
    def test_get_existing(self, tmp_path: Path) -> None:
        q = _make_queue(tmp_path)
        req = _add_one(q)
        found = q.get(req.id)
        assert found is not None
        assert found.id == req.id

    def test_get_missing_returns_none(self, tmp_path: Path) -> None:
        q = _make_queue(tmp_path)
        assert q.get("no-such-id") is None

    def test_reload(self, tmp_path: Path) -> None:
        q = _make_queue(tmp_path)
        req = _add_one(q)
        # Mutate on disk by a second instance
        q2 = SimQueue(q.path)
        q2.update(req.id, status=SimStatus.FAILED)
        # Reload original
        q.reload()
        updated = q.get(req.id)
        assert updated is not None
        assert updated.status == SimStatus.FAILED
