"""Tests for vorpal.app — Textual pilot smoke tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from slopr.app import WargameApp
from slopr.fixtures import generate_sample_game, write_sample_game
from slopr.models import EventSource, EventType
from slopr.store import JSONLEventStore
from slopr.widgets.banner import KahnBanner
from slopr.widgets.content_pane import ContentPane, EventCard, _group_events
from slopr.widgets.kpi_bar import (
    KPIBar,
    KPIIndicator,
    _territory_class,
    _power_class,
    _trend_arrow,
)
from slopr.widgets.kpi_panel import KPIPanel
from textual.widgets import DataTable, Collapsible
from slopr.widgets.search_bar import SearchBar
from slopr.widgets.search_modal import SearchModal
from slopr.widgets.turn_sidebar import TurnSidebar, TurnIndex


@pytest.fixture()
def demo_jsonl(tmp_path: Path) -> Path:
    """Generate a 5-turn demo JSONL file."""
    return write_sample_game(tmp_path / "demo.jsonl", n_turns=5)


@pytest.fixture()
def demo_store(demo_jsonl: Path) -> JSONLEventStore:
    return JSONLEventStore(demo_jsonl)


class TestAppMounts:
    """Basic app lifecycle tests."""

    @pytest.mark.asyncio
    async def test_app_starts_and_stops(self, demo_store: JSONLEventStore) -> None:
        app = WargameApp(store=demo_store)
        async with app.run_test() as pilot:
            assert app.title == "Project Kahn — Wargame Viewer"

    @pytest.mark.asyncio
    async def test_sidebar_present(self, demo_store: JSONLEventStore) -> None:
        app = WargameApp(store=demo_store)
        async with app.run_test() as pilot:
            sidebar = app.query_one(TurnSidebar)
            assert sidebar is not None

    @pytest.mark.asyncio
    async def test_content_pane_present(self, demo_store: JSONLEventStore) -> None:
        app = WargameApp(store=demo_store)
        async with app.run_test() as pilot:
            pane = app.query_one(ContentPane)
            assert pane is not None

    @pytest.mark.asyncio
    async def test_empty_store(self) -> None:
        app = WargameApp(store=JSONLEventStore())
        async with app.run_test() as pilot:
            sidebar = app.query_one(TurnSidebar)
            assert sidebar is not None


class TestSidebarTurns:
    """Sidebar shows correct turns from store."""

    @pytest.mark.asyncio
    async def test_sidebar_has_turn_entries(self, demo_store: JSONLEventStore) -> None:
        app = WargameApp(store=demo_store)
        async with app.run_test() as pilot:
            index = app.query_one(TurnIndex)
            assert len(index.root.children) > 0

    @pytest.mark.asyncio
    async def test_sidebar_turn_count_matches_store(self, demo_store: JSONLEventStore) -> None:
        app = WargameApp(store=demo_store)
        async with app.run_test() as pilot:
            index = app.query_one(TurnIndex)
            expected = len(demo_store.get_turn_numbers())
            assert len(index.root.children) == expected


class TestContentPane:
    """Content pane shows cards for a selected turn."""

    @pytest.mark.asyncio
    async def test_initial_load_shows_cards(self, demo_store: JSONLEventStore) -> None:
        app = WargameApp(store=demo_store, start_turn=0)
        async with app.run_test() as pilot:
            pane = app.query_one(ContentPane)
            cards = pane.query(EventCard)
            # Turn 0 has at least the GAME_START event
            assert len(cards) > 0

    @pytest.mark.asyncio
    async def test_load_turn_replaces_cards(self, demo_store: JSONLEventStore) -> None:
        app = WargameApp(store=demo_store, start_turn=0)
        async with app.run_test() as pilot:
            pane = app.query_one(ContentPane)
            initial_count = len(pane.query(EventCard))

            # Load a different turn
            pane.load_turn(1)
            await pilot.pause()
            new_count = len(pane.query(EventCard))
            # Turn 1 has more events than turn 0
            assert new_count > initial_count

    @pytest.mark.asyncio
    async def test_source_css_classes(self, demo_store: JSONLEventStore) -> None:
        app = WargameApp(store=demo_store, start_turn=1)
        async with app.run_test() as pilot:
            pane = app.query_one(ContentPane)
            cards = pane.query(EventCard)
            # At least one card should have source-llm class
            llm_cards = [c for c in cards if c.has_class("source-llm")]
            assert len(llm_cards) > 0


class TestStartTurn:
    """App respects --turn option."""

    @pytest.mark.asyncio
    async def test_start_turn_0(self, demo_store: JSONLEventStore) -> None:
        app = WargameApp(store=demo_store, start_turn=0)
        async with app.run_test() as pilot:
            pane = app.query_one(ContentPane)
            cards = pane.query(EventCard)
            assert len(cards) > 0

    @pytest.mark.asyncio
    async def test_start_turn_invalid_falls_back(self, demo_store: JSONLEventStore) -> None:
        app = WargameApp(store=demo_store, start_turn=999)
        async with app.run_test() as pilot:
            pane = app.query_one(ContentPane)
            cards = pane.query(EventCard)
            # Falls back to first turn
            assert len(cards) > 0


class TestKPIBar:
    """KPI bar renders and updates."""

    @pytest.mark.asyncio
    async def test_kpi_bar_present(self, demo_store: JSONLEventStore) -> None:
        app = WargameApp(store=demo_store)
        async with app.run_test() as pilot:
            bar = app.query_one(KPIBar)
            assert bar is not None

    @pytest.mark.asyncio
    async def test_kpi_indicators_present(self, demo_store: JSONLEventStore) -> None:
        app = WargameApp(store=demo_store)
        async with app.run_test() as pilot:
            bar = app.query_one(KPIBar)
            indicators = bar.query(KPIIndicator)
            assert len(indicators) == 9

    @pytest.mark.asyncio
    async def test_kpi_updates_on_turn(self, demo_store: JSONLEventStore) -> None:
        app = WargameApp(store=demo_store, start_turn=1)
        async with app.run_test() as pilot:
            bar = app.query_one(KPIBar)
            # After loading turn 1, the bar should have been updated
            bar._update_kpis(1)
            assert bar._prev_kpi is not None


class TestKPIHelpers:
    """Unit tests for KPI threshold and trend helpers."""

    def test_territory_normal(self) -> None:
        assert _territory_class(0.5) == "kpi-normal"

    def test_territory_warning(self) -> None:
        assert _territory_class(2.0) == "kpi-warning"

    def test_territory_critical(self) -> None:
        assert _territory_class(4.0) == "kpi-critical"

    def test_territory_negative(self) -> None:
        assert _territory_class(-3.5) == "kpi-critical"

    def test_power_normal(self) -> None:
        assert _power_class(0.9) == "kpi-normal"

    def test_power_warning(self) -> None:
        assert _power_class(0.5) == "kpi-warning"

    def test_power_critical(self) -> None:
        assert _power_class(0.2) == "kpi-critical"

    def test_trend_arrow_up(self) -> None:
        result = _trend_arrow(1.5, 1.0)
        assert "\u25b2" in result  # ▲

    def test_trend_arrow_down(self) -> None:
        result = _trend_arrow(0.5, 1.0)
        assert "\u25bc" in result  # ▼

    def test_trend_arrow_flat(self) -> None:
        result = _trend_arrow(1.0, 1.0)
        assert "\u2500" in result  # ─

    def test_trend_arrow_no_previous(self) -> None:
        assert _trend_arrow(1.0, None) == ""


class TestSearchBar:
    """Inline search bar tests."""

    @pytest.mark.asyncio
    async def test_search_bar_present(self, demo_store: JSONLEventStore) -> None:
        app = WargameApp(store=demo_store)
        async with app.run_test() as pilot:
            bar = app.query_one(SearchBar)
            assert bar is not None

    @pytest.mark.asyncio
    async def test_search_bar_hidden_by_default(self, demo_store: JSONLEventStore) -> None:
        app = WargameApp(store=demo_store)
        async with app.run_test() as pilot:
            bar = app.query_one(SearchBar)
            assert bar.display is False

    @pytest.mark.asyncio
    async def test_search_bar_toggle(self, demo_store: JSONLEventStore) -> None:
        app = WargameApp(store=demo_store)
        async with app.run_test() as pilot:
            bar = app.query_one(SearchBar)
            bar.toggle()
            assert bar.display is True
            bar.toggle()
            assert bar.display is False


class TestSearchModal:
    """Search modal tests."""

    @pytest.mark.asyncio
    async def test_modal_opens(self, demo_store: JSONLEventStore) -> None:
        app = WargameApp(store=demo_store)
        async with app.run_test() as pilot:
            await pilot.press("ctrl+f")
            await pilot.pause()
            # Modal should be on the screen stack
            assert len(app.screen_stack) > 1

    @pytest.mark.asyncio
    async def test_modal_closes_on_escape(self, demo_store: JSONLEventStore) -> None:
        app = WargameApp(store=demo_store)
        async with app.run_test() as pilot:
            await pilot.press("ctrl+f")
            await pilot.pause()
            assert len(app.screen_stack) > 1
            await pilot.press("escape")
            await pilot.pause()
            assert len(app.screen_stack) == 1


class TestEventGrouping:
    """Tests for _group_events() logic."""

    def test_game_over_after_end_state(self, demo_store: JSONLEventStore) -> None:
        """Game Over group must appear after End State group."""
        # Find the last turn (which should have a GAME_END)
        turns = demo_store.get_turn_numbers()
        last_turn = turns[-1]
        events = demo_store.get_events(turn=last_turn, limit=1000)
        groups = _group_events(events)
        labels = [g.label for g in groups]
        if "Game Over" in labels and "End State" in labels:
            es_idx = labels.index("End State")
            go_idx = labels.index("Game Over")
            assert go_idx > es_idx, "Game Over must come after End State"

    def test_turn_0_has_scenario_group(self, demo_store: JSONLEventStore) -> None:
        events = demo_store.get_events(turn=0, limit=1000)
        groups = _group_events(events)
        labels = [g.label for g in groups]
        assert "Scenario" in labels

    def test_turn_0_has_profiles_group(self, demo_store: JSONLEventStore) -> None:
        events = demo_store.get_events(turn=0, limit=1000)
        groups = _group_events(events)
        labels = [g.label for g in groups]
        assert "State Profiles" in labels

    def test_turn_0_has_end_state_group(self, demo_store: JSONLEventStore) -> None:
        events = demo_store.get_events(turn=0, limit=1000)
        groups = _group_events(events)
        labels = [g.label for g in groups]
        assert "End State" in labels

    def test_turn_0_group_order(self, demo_store: JSONLEventStore) -> None:
        events = demo_store.get_events(turn=0, limit=1000)
        groups = _group_events(events)
        labels = [g.label for g in groups]
        assert labels == ["Parameters", "Scenario", "State Profiles", "End State"]

    def test_turn_1_has_end_state_group(self, demo_store: JSONLEventStore) -> None:
        events = demo_store.get_events(turn=1, limit=1000)
        groups = _group_events(events)
        labels = [g.label for g in groups]
        assert "End State" in labels

    def test_profiles_has_two_events(self, demo_store: JSONLEventStore) -> None:
        events = demo_store.get_events(turn=0, limit=1000)
        groups = _group_events(events)
        profiles = [g for g in groups if g.label == "State Profiles"]
        assert len(profiles) == 1
        assert len(profiles[0].events) == 2  # State A and State B


class TestBanner:
    """Banner appears on turn 0 inside a 'Project Kahn' group."""

    @pytest.mark.asyncio
    async def test_banner_on_turn_0(self, demo_store: JSONLEventStore) -> None:
        app = WargameApp(store=demo_store, start_turn=0)
        async with app.run_test() as pilot:
            pane = app.query_one(ContentPane)
            banners = pane.query(KahnBanner)
            assert len(banners) == 1

    @pytest.mark.asyncio
    async def test_banner_wrapped_in_group(self, demo_store: JSONLEventStore) -> None:
        app = WargameApp(store=demo_store, start_turn=0)
        async with app.run_test() as pilot:
            pane = app.query_one(ContentPane)
            banner_groups = pane.query(Collapsible).filter(".group-banner")
            assert len(banner_groups) == 1
            assert banner_groups.first().title == "Project Kahn"

    @pytest.mark.asyncio
    async def test_no_banner_on_turn_1(self, demo_store: JSONLEventStore) -> None:
        app = WargameApp(store=demo_store, start_turn=1)
        async with app.run_test() as pilot:
            pane = app.query_one(ContentPane)
            banners = pane.query(KahnBanner)
            assert len(banners) == 0


class TestKPIPanel:
    """KPI panel modal tests."""

    @pytest.mark.asyncio
    async def test_kpi_panel_mounts(self, demo_store: JSONLEventStore) -> None:
        app = WargameApp(store=demo_store, start_turn=1)
        async with app.run_test() as pilot:
            bar = app.query_one(KPIBar)
            bar._update_kpis(1)
            app.push_screen(KPIPanel(demo_store, 1))
            await pilot.pause()
            assert len(app.screen_stack) > 1

    @pytest.mark.asyncio
    async def test_kpi_panel_closes_on_escape(self, demo_store: JSONLEventStore) -> None:
        app = WargameApp(store=demo_store, start_turn=1)
        async with app.run_test() as pilot:
            app.push_screen(KPIPanel(demo_store, 1))
            await pilot.pause()
            assert len(app.screen_stack) > 1
            await pilot.press("escape")
            await pilot.pause()
            assert len(app.screen_stack) == 1


class TestFixturesTurn0:
    """Verify fixtures generate expected turn 0 events."""

    def test_turn_0_has_scenario_events(self) -> None:
        events = generate_sample_game(n_turns=3)
        turn_0 = [e for e in events if e.turn_number == 0]
        scenario_events = [
            e
            for e in turn_0
            if e.event_type == EventType.SITUATION_REPORT and e.phase == "scenario"
        ]
        assert len(scenario_events) == 1
        assert "Alliance Leadership Test" in scenario_events[0].title

    def test_turn_0_has_profile_events(self) -> None:
        events = generate_sample_game(n_turns=3)
        turn_0 = [e for e in events if e.turn_number == 0]
        profile_events = [
            e
            for e in turn_0
            if e.event_type == EventType.SITUATION_REPORT and e.phase == "profiles"
        ]
        assert len(profile_events) == 2
        sides = {e.structured_data.get("side") for e in profile_events}
        assert sides == {"A", "B"}

    def test_turn_0_has_initial_state(self) -> None:
        events = generate_sample_game(n_turns=3)
        turn_0 = [e for e in events if e.turn_number == 0]
        state_events = [e for e in turn_0 if e.event_type == EventType.STATE_CHANGE]
        assert len(state_events) == 1
        assert state_events[0].title == "Initial conditions"


class TestInitialState:
    """Initial State group appears on turns >= 1."""

    @pytest.mark.asyncio
    async def test_initial_state_on_turn_1(self, demo_store: JSONLEventStore) -> None:
        app = WargameApp(store=demo_store, start_turn=1)
        async with app.run_test() as pilot:
            pane = app.query_one(ContentPane)
            collapsibles = pane.query(Collapsible)
            labels = [c.title for c in collapsibles]
            assert "Initial State" in labels

    @pytest.mark.asyncio
    async def test_no_initial_state_on_turn_0(self, demo_store: JSONLEventStore) -> None:
        app = WargameApp(store=demo_store, start_turn=0)
        async with app.run_test() as pilot:
            pane = app.query_one(ContentPane)
            collapsibles = pane.query(Collapsible)
            labels = [c.title for c in collapsibles]
            assert "Initial State" not in labels

    @pytest.mark.asyncio
    async def test_initial_state_before_phases(self, demo_store: JSONLEventStore) -> None:
        app = WargameApp(store=demo_store, start_turn=1)
        async with app.run_test() as pilot:
            pane = app.query_one(ContentPane)
            collapsibles = pane.query(Collapsible)
            labels = [c.title for c in collapsibles]
            if "Initial State" in labels and "Reflection" in labels:
                assert labels.index("Initial State") < labels.index("Reflection")


class TestKPIPanelClick:
    """KPI bar click opens the panel modal."""

    @pytest.mark.asyncio
    async def test_kpi_bar_click_opens_panel(self, demo_store: JSONLEventStore) -> None:
        app = WargameApp(store=demo_store, start_turn=1)
        async with app.run_test() as pilot:
            bar = app.query_one(KPIBar)
            bar._update_kpis(1)
            # Push the panel directly as the handler would
            app.push_screen(KPIPanel(demo_store, bar._current_turn))
            await pilot.pause()
            assert len(app.screen_stack) > 1

    @pytest.mark.asyncio
    async def test_kpi_panel_has_table(self, demo_store: JSONLEventStore) -> None:
        app = WargameApp(store=demo_store, start_turn=1)
        async with app.run_test() as pilot:
            app.push_screen(KPIPanel(demo_store, 1))
            await pilot.pause()
            table = app.query_one(DataTable)
            assert table is not None
            # Table should have rows for turns with KPI data
            assert table.row_count > 0


class TestSidebarPhases:
    """Sidebar shows phase sub-items for turns."""

    @pytest.mark.asyncio
    async def test_turn_0_has_parameters_leaf(self, demo_store: JSONLEventStore) -> None:
        app = WargameApp(store=demo_store)
        async with app.run_test() as pilot:
            index = app.query_one(TurnIndex)
            turn_0_node = index.root.children[0]
            leaf_labels = [str(child.label) for child in turn_0_node.children]
            assert "Parameters" in leaf_labels

    @pytest.mark.asyncio
    async def test_turn_0_has_scenario_phase(self, demo_store: JSONLEventStore) -> None:
        app = WargameApp(store=demo_store)
        async with app.run_test() as pilot:
            index = app.query_one(TurnIndex)
            # Turn 0 node should have scenario and profiles sub-items
            turn_0_node = index.root.children[0]
            leaf_labels = [str(child.label) for child in turn_0_node.children]
            assert "Scenario" in leaf_labels
            assert "State Profiles" in leaf_labels

    @pytest.mark.asyncio
    async def test_turn_1_has_initial_state_leaf(self, demo_store: JSONLEventStore) -> None:
        app = WargameApp(store=demo_store)
        async with app.run_test() as pilot:
            index = app.query_one(TurnIndex)
            turn_1_node = index.root.children[1]
            leaf_labels = [str(child.label) for child in turn_1_node.children]
            assert "Initial State" in leaf_labels
            assert "End State" in leaf_labels

    @pytest.mark.asyncio
    async def test_turn_1_leaf_order(self, demo_store: JSONLEventStore) -> None:
        app = WargameApp(store=demo_store)
        async with app.run_test() as pilot:
            index = app.query_one(TurnIndex)
            turn_1_node = index.root.children[1]
            leaf_labels = [str(child.label) for child in turn_1_node.children]
            # Initial State should come before phase groups, End State after
            if "Initial State" in leaf_labels and "Reflection" in leaf_labels:
                assert leaf_labels.index("Initial State") < leaf_labels.index("Reflection")
            if "End State" in leaf_labels and "Action" in leaf_labels:
                assert leaf_labels.index("End State") > leaf_labels.index("Action")
