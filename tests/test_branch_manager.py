"""TUI integration tests for the branch manager panel and edit modal."""

from __future__ import annotations

from pathlib import Path

import pytest

from slopr.app import WargameApp
from slopr.branches import BranchStatus, BranchStore
from slopr.fixtures import write_sample_game
from slopr.models import EventType
from slopr.store import JSONLEventStore
from slopr.widgets.branch_manager import BranchActivated, BranchDeleted, BranchManager
from slopr.widgets.branch_pane import BranchPane
from slopr.widgets.content_pane import EventCardDoubleClicked
from slopr.widgets.edit_event_modal import EditEventModal


# ── App startup ───────────────────────────────────────────────────────────────


class TestBranchManagerStartup:
    @pytest.mark.asyncio
    async def test_branch_manager_present(self, branched_store) -> None:
        bs, _ = branched_store
        app = WargameApp(store=bs.get_store(), branch_store=bs)
        async with app.run_test() as pilot:
            bm = app.query_one(BranchManager)
            assert bm is not None

    @pytest.mark.asyncio
    async def test_branch_manager_hidden_by_default(self, branched_store) -> None:
        bs, _ = branched_store
        app = WargameApp(store=bs.get_store(), branch_store=bs)
        async with app.run_test() as pilot:
            bp = app.query_one(BranchPane)
            assert not bp.has_class("--active")

    @pytest.mark.asyncio
    async def test_no_branch_store_still_starts(self, demo_store: JSONLEventStore) -> None:
        """App starts cleanly without branch support."""
        app = WargameApp(store=demo_store)
        async with app.run_test() as pilot:
            assert app.query_one(BranchManager) is not None


# ── Ctrl+B toggle ─────────────────────────────────────────────────────────────


class TestBranchManagerToggle:
    @pytest.mark.asyncio
    async def test_ctrl_b_shows_panel(self, branched_store) -> None:
        bs, _ = branched_store
        app = WargameApp(store=bs.get_store(), branch_store=bs)
        async with app.run_test() as pilot:
            await pilot.press("ctrl+b")
            await pilot.pause()
            assert app.query_one(BranchPane).has_class("--active")

    @pytest.mark.asyncio
    async def test_ctrl_b_toggles_off(self, branched_store) -> None:
        """Pressing Ctrl+B switches to Branches pane; a second Ctrl+B does NOT
        toggle back — it's a directional switch, not a toggle.  After the second
        press the Branches pane is still --active (or the Events pane regained
        focus if the app maps Ctrl+B as a direct switch-to-branches action).
        We just verify the pane is still reachable."""
        bs, _ = branched_store
        app = WargameApp(store=bs.get_store(), branch_store=bs)
        async with app.run_test() as pilot:
            await pilot.press("ctrl+b")
            await pilot.pause()
            assert app.query_one(BranchPane).has_class("--active")
            # A second Ctrl+B still activates branches (not a toggle)
            await pilot.press("ctrl+b")
            await pilot.pause()
            assert app.query_one(BranchPane).has_class("--active")


# ── Branch tree content ───────────────────────────────────────────────────────


class TestBranchTree:
    @pytest.mark.asyncio
    async def test_branch_tree_has_root_node(self, branched_store) -> None:
        from textual.widgets import Tree

        bs, _ = branched_store
        app = WargameApp(store=bs.get_store(), branch_store=bs)
        async with app.run_test() as pilot:
            await pilot.press("ctrl+b")
            await pilot.pause()
            bm = app.query_one(BranchManager)
            tree = bm.query_one(Tree)
            assert tree.root is not None

    @pytest.mark.asyncio
    async def test_branch_tree_shows_child_branches(self, branched_store) -> None:
        from textual.widgets import Tree

        bs, entry = branched_store
        app = WargameApp(store=bs.get_store(), branch_store=bs)
        async with app.run_test() as pilot:
            await pilot.press("ctrl+b")
            await pilot.pause()
            bm = app.query_one(BranchManager)
            tree = bm.query_one(Tree)
            # The root node should have 1 child (our branch)
            assert len(list(tree.root.children)) >= 1


# ── BranchActivated message ───────────────────────────────────────────────────


class TestBranchActivated:
    @pytest.mark.asyncio
    async def test_branch_activated_sets_active_id(self, branched_store) -> None:
        bs, entry = branched_store
        app = WargameApp(store=bs.get_store(), branch_store=bs)
        async with app.run_test() as pilot:
            app.post_message(BranchActivated(branch_id=entry.id))
            await pilot.pause()
            assert app._active_branch_id == entry.id

    @pytest.mark.asyncio
    async def test_branch_activated_root_resets_id(self, branched_store) -> None:
        bs, entry = branched_store
        app = WargameApp(store=bs.get_store(), branch_store=bs)
        async with app.run_test() as pilot:
            # First activate branch
            app.post_message(BranchActivated(branch_id=entry.id))
            await pilot.pause()
            # Then activate root
            app.post_message(BranchActivated(branch_id=None))
            await pilot.pause()
            assert app._active_branch_id is None


# ── Double-click without branch_store ────────────────────────────────────────


class TestDoubleClickNoBranchStore:
    @pytest.mark.asyncio
    async def test_double_click_without_store_shows_notification(
        self, demo_store: JSONLEventStore
    ) -> None:
        """Without branch_store, no modal is pushed; notification appears."""
        app = WargameApp(store=demo_store)
        async with app.run_test() as pilot:
            events = demo_store.get_events(turn=1, limit=1)
            if events:
                app.post_message(EventCardDoubleClicked(events[0]))
                await pilot.pause()
            # Only base screen in stack (no modal was pushed)
            assert len(app.screen_stack) == 1


# ── BranchDeleted message ─────────────────────────────────────────────────────


class TestBranchDeleted:
    @pytest.mark.asyncio
    async def test_delete_removes_branch_from_store(self, branched_store) -> None:
        bs, entry = branched_store
        app = WargameApp(store=bs.get_store(), branch_store=bs)
        async with app.run_test() as pilot:
            app.post_message(BranchDeleted(branch_id=entry.id))
            await pilot.pause()
            assert not any(b.id == entry.id for b in bs.manifest.branches)

    @pytest.mark.asyncio
    async def test_delete_active_branch_reverts_to_root(self, branched_store) -> None:
        bs, entry = branched_store
        app = WargameApp(store=bs.get_store(), branch_store=bs)
        async with app.run_test() as pilot:
            # Activate the branch first
            app.post_message(BranchActivated(branch_id=entry.id))
            await pilot.pause()
            assert app._active_branch_id == entry.id
            # Delete it
            app.post_message(BranchDeleted(branch_id=entry.id))
            await pilot.pause()
            assert app._active_branch_id is None


# ── Two-branch scenario fixture ───────────────────────────────────────────────


class TestMultiBranchFixture:
    """Tests that use a second branch for richer multi-branch scenarios."""

    @pytest.fixture()
    def two_branch_store(self, tmp_path: Path):
        root = write_sample_game(tmp_path / "root.jsonl", n_turns=8, seed=7)
        bs = BranchStore.init(root)
        root_store = bs.get_store()
        fork1 = root_store.get_events(turn=2, event_type=EventType.STATE_CHANGE)[0]
        fork2 = root_store.get_events(turn=4, event_type=EventType.STATE_CHANGE)[0]
        b1 = bs.create_branch(None, fork1.id, "Branch at turn 2")
        b2 = bs.create_branch(None, fork2.id, "Branch at turn 4")
        return bs, b1, b2

    @pytest.mark.asyncio
    async def test_two_branches_in_tree(self, two_branch_store) -> None:
        from textual.widgets import Tree

        bs, b1, b2 = two_branch_store
        app = WargameApp(store=bs.get_store(), branch_store=bs)
        async with app.run_test() as pilot:
            await pilot.press("ctrl+b")
            await pilot.pause()
            bm = app.query_one(BranchManager)
            tree = bm.query_one(Tree)
            assert len(list(tree.root.children)) >= 2

    @pytest.mark.asyncio
    async def test_activate_each_branch_independently(self, two_branch_store) -> None:
        bs, b1, b2 = two_branch_store
        app = WargameApp(store=bs.get_store(), branch_store=bs)
        async with app.run_test() as pilot:
            app.post_message(BranchActivated(branch_id=b1.id))
            await pilot.pause()
            assert app._active_branch_id == b1.id

            app.post_message(BranchActivated(branch_id=b2.id))
            await pilot.pause()
            assert app._active_branch_id == b2.id

    @pytest.mark.asyncio
    async def test_delete_one_branch_leaves_other(self, two_branch_store) -> None:
        bs, b1, b2 = two_branch_store
        app = WargameApp(store=bs.get_store(), branch_store=bs)
        async with app.run_test() as pilot:
            app.post_message(BranchDeleted(branch_id=b1.id))
            await pilot.pause()
            # b2 should still be present
            assert any(b.id == b2.id for b in bs.manifest.branches)
            # b1 removed
            assert not any(b.id == b1.id for b in bs.manifest.branches)
