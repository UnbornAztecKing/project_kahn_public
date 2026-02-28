"""Tests for sim-process log file creation (Feature 4: branches.py spawn_sim)."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from slopr.branches import BranchStatus, BranchStore
from slopr.fixtures import write_sample_game
from slopr.models import EventType


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_branched_store(tmp_path: Path):
    """Return (BranchStore, BranchEntry) forked at turn-2 STATE_CHANGE."""
    root = write_sample_game(tmp_path / "root.jsonl", n_turns=5, seed=42)
    bs = BranchStore.init(root)
    root_store = bs.get_store(None)
    fork_evt = root_store.get_events(turn=2, event_type=EventType.STATE_CHANGE)[0]
    entry = bs.create_branch(
        parent_branch_id=None,
        parent_event_id=fork_evt.id,
        label="Sim log test branch",
    )
    return bs, entry


# ── get_log_path convention ───────────────────────────────────────────────────


class TestGetLogPathConvention:
    """get_log_path() returns the branch JSONL path with a `.log` suffix appended."""

    def test_log_path_is_jsonl_plus_log(self, tmp_path: Path) -> None:
        bs, entry = _make_branched_store(tmp_path)
        branch_jsonl = bs.get_jsonl_path(entry.id)
        log_path = bs.get_log_path(entry.id)
        # e.g. root.sim-log-test-branch.jsonl  →  root.sim-log-test-branch.jsonl.log
        assert log_path == branch_jsonl.parent / (branch_jsonl.name + ".log")

    def test_log_path_ends_with_dot_log(self, tmp_path: Path) -> None:
        bs, entry = _make_branched_store(tmp_path)
        assert bs.get_log_path(entry.id).name.endswith(".log")

    def test_log_path_is_sibling_of_jsonl(self, tmp_path: Path) -> None:
        bs, entry = _make_branched_store(tmp_path)
        log_path = bs.get_log_path(entry.id)
        branch_jsonl = bs.get_jsonl_path(entry.id)
        assert log_path.parent == branch_jsonl.parent

    def test_log_path_different_from_jsonl(self, tmp_path: Path) -> None:
        bs, entry = _make_branched_store(tmp_path)
        assert bs.get_log_path(entry.id) != bs.get_jsonl_path(entry.id)

    def test_log_stem_includes_jsonl_extension(self, tmp_path: Path) -> None:
        """The stem of the log file should contain '.jsonl', e.g. 'foo.jsonl.log'."""
        bs, entry = _make_branched_store(tmp_path)
        log_name = bs.get_log_path(entry.id).name
        assert ".jsonl" in log_name


# ── spawn_sim creates log file ────────────────────────────────────────────────


class TestSpawnSimCreatesLogFile:
    """spawn_sim() opens the log file before launching the subprocess."""

    async def test_log_file_created_on_spawn(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bs, entry = _make_branched_store(tmp_path)
        log_path = bs.get_log_path(entry.id)

        # Monkeypatch asyncio.create_subprocess_exec so no real process is launched.
        mock_proc = MagicMock()
        mock_proc.pid = 99999

        async def _fake_exec(*args, **kwargs):
            return mock_proc

        monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

        await bs.spawn_sim(
            entry.id,
            model_a="model-a",
            model_b="model-b",
            turns=3,
        )

        assert log_path.exists(), f"Expected log file at {log_path}"

    async def test_log_file_is_writable_text_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bs, entry = _make_branched_store(tmp_path)
        log_path = bs.get_log_path(entry.id)

        mock_proc = MagicMock()
        mock_proc.pid = 99999

        async def _fake_exec(*args, **kwargs):
            return mock_proc

        monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

        await bs.spawn_sim(
            entry.id,
            model_a="model-a",
            model_b="model-b",
            turns=3,
        )

        # File should be openable for reading without error
        content = log_path.read_text(encoding="utf-8")
        assert isinstance(content, str)

    async def test_spawn_sim_sets_running_status(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bs, entry = _make_branched_store(tmp_path)

        mock_proc = MagicMock()
        mock_proc.pid = 55555

        async def _fake_exec(*args, **kwargs):
            return mock_proc

        monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

        await bs.spawn_sim(
            entry.id,
            model_a="model-a",
            model_b="model-b",
            turns=3,
        )

        reloaded = bs.get_entry(entry.id)
        assert reloaded.sim_status == BranchStatus.RUNNING

    async def test_spawn_sim_records_pid(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bs, entry = _make_branched_store(tmp_path)

        mock_proc = MagicMock()
        mock_proc.pid = 77777

        async def _fake_exec(*args, **kwargs):
            return mock_proc

        monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

        await bs.spawn_sim(
            entry.id,
            model_a="model-a",
            model_b="model-b",
            turns=3,
        )

        reloaded = bs.get_entry(entry.id)
        assert reloaded.sim_pid == 77777

    async def test_log_file_in_same_dir_as_jsonl(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        bs, entry = _make_branched_store(tmp_path)
        branch_jsonl = bs.get_jsonl_path(entry.id)

        mock_proc = MagicMock()
        mock_proc.pid = 11111

        async def _fake_exec(*args, **kwargs):
            return mock_proc

        monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_exec)

        await bs.spawn_sim(
            entry.id,
            model_a="model-a",
            model_b="model-b",
            turns=3,
        )

        log_path = bs.get_log_path(entry.id)
        assert log_path.parent == branch_jsonl.parent
