"""Wargame TUI — main application."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.timer import Timer
from textual.widgets import Footer, Header

from slopr.branches import BranchStatus, BranchStore
from slopr.sim_queue import SimQueue, SimStatus
from slopr.store import EventStore, JSONLEventStore

if TYPE_CHECKING:
    from slopr.models import GameEvent
    from slopr.tail import Tailer

from slopr.widgets.branch_manager import BranchActivated, BranchDeleted, BranchEdited, BranchSimRequested
from slopr.widgets.branch_pane import BranchPane
from slopr.widgets.content_pane import ContentPane, EventCardClicked, EventCardDoubleClicked, EventCardRightClicked
from slopr.widgets.context_menu import AnalysisRequested, ContextMenuScreen
from slopr.widgets.edit_event_modal import EditEventModal, EditResult
from slopr.widgets.kpi_bar import KPIBar, KPIBarClicked
from slopr.widgets.kpi_panel import KPIPanel
from slopr.widgets.search_bar import SearchBar, SearchSubmitted
from slopr.widgets.search_modal import SearchModal
from slopr.widgets.sim_manager_pane import SimCancelRequested, SimManagerPane, SimRetryRequested
from slopr.provider_config import ProviderConfigStore
from slopr.skill_store import SkillStore
from slopr.task_store import TaskEntry, TaskStore
from slopr.widgets.provider_config_pane import ProviderConfigChanged, ProviderConfigPane
from slopr.widgets.tags_pane import TagsPane
from slopr.widgets.skills_pane import SkillsPane
from slopr.widgets.tasks_pane import TasksPane
from slopr.widgets.turn_sidebar import PaneNavSelected, PaneNavBar, PhaseSelected, TurnIndex, TurnSelected, TurnSidebar


class WargameApp(App):
    """Event-stream viewer for Project Kahn simulations."""

    TITLE = "Project Kahn — Wargame Viewer"
    CSS_PATH = "wargame.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("slash", "toggle_search", "Search", show=True),
        Binding("ctrl+f", "open_search_modal", "Find", show=True),
        Binding("ctrl+b", "switch_branches", "Branches", show=True),
        Binding("ctrl+s", "switch_sims", "Sims", show=True),
        Binding("ctrl+t", "switch_tasks",  "Tasks",  show=True),
        Binding("ctrl+g", "switch_tags",   "Tags",   show=True),
        Binding("ctrl+k", "switch_skills", "Skills", show=True),
        Binding("ctrl+p", "switch_provider_config", "Config", show=True),
        Binding("tab", "focus_next", "Next pane", show=False),
        Binding("shift+tab", "focus_previous", "Prev pane", show=False),
    ]

    def __init__(
        self,
        store: EventStore | None = None,
        path: Path | str | None = None,
        source_path: Path | None = None,
        start_turn: int | None = None,
        split_threshold: int = 100,
        double_newlines: bool = True,
        wrap_indent: int = 0,
        branch_store: BranchStore | None = None,
        sim_queue: SimQueue | None = None,
        analysis_model: str = "claude-sonnet-4-6",
    ) -> None:
        super().__init__()
        self._store = store or JSONLEventStore() if path is None else JSONLEventStore(path)
        self._source_path = source_path
        self._start_turn = start_turn
        self._split_threshold = split_threshold
        self._double_newlines = double_newlines
        self._wrap_indent = wrap_indent
        self._tailer: Tailer | None = None
        self._poll_timer: Timer | None = None
        self._branch_store: BranchStore | None = branch_store
        self._active_branch_id: str | None = None
        self._branch_tailer: Tailer | None = None
        self._sim_queue: SimQueue | None = sim_queue
        self._analysis_model: str = analysis_model
        self._skill_store: SkillStore | None = None
        self._provider_config_store: ProviderConfigStore | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main-container"):
            yield TurnSidebar(self._store)
            yield ContentPane(
                self._store,
                split_threshold=self._split_threshold,
                double_newlines=self._double_newlines,
                wrap_indent=self._wrap_indent,
                classes="main-pane --active",
                id="pane-events",
            )
            yield BranchPane(classes="main-pane", id="pane-branches")
            yield SimManagerPane(classes="main-pane", id="pane-sims")
            yield TasksPane(classes="main-pane", id="pane-tasks")
            yield TagsPane(classes="main-pane", id="pane-tags")
            yield SkillsPane(classes="main-pane", id="pane-skills")
            yield ProviderConfigPane(classes="main-pane", id="pane-config")
        yield KPIBar(self._store)
        yield SearchBar()
        yield Footer()

    def on_mount(self) -> None:
        turns = self._store.get_turn_numbers()
        if turns:
            start = self._start_turn if self._start_turn in turns else turns[0]
            self.query_one(ContentPane).load_turn(start)

        if self._source_path is not None and isinstance(self._store, JSONLEventStore):
            from slopr.tail import Tailer

            self._tailer = Tailer(
                self._source_path,
                self._store,
                on_new_events=self._on_new_events,
            )
            self._poll_timer = self.set_interval(0.1, self._poll_tail)

        if self._branch_store is not None:
            bp = self.query_one(BranchPane)
            bp.set_store(self._branch_store)

        if self._sim_queue is not None:
            sp = self.query_one(SimManagerPane)
            sp.set_queue(self._sim_queue)
            if self._branch_store is not None:
                sp.set_branch_store(self._branch_store)

        if self._source_path is not None:
            task_store = TaskStore(TaskStore.path_for(self._source_path))
            self.query_one(TasksPane).set_store(task_store)
            self._skill_store = SkillStore(SkillStore.path_for(self._source_path))
            self.query_one(SkillsPane).set_store(self._skill_store)
            self._provider_config_store = ProviderConfigStore(
                ProviderConfigStore.path_for(self._source_path)
            )
            pcp = self.query_one(ProviderConfigPane)
            pcp.set_store(self._provider_config_store)
            # Sync _analysis_model to the persisted active provider model
            self._analysis_model = self._provider_config_store.active_config.model

    def _poll_tail(self) -> None:
        """Timer callback — ask the tailer(s) to check for new file content."""
        if self._tailer is not None:
            self._tailer.poll()
        if self._branch_tailer is not None:
            self._branch_tailer.poll()

    def _on_new_events(self) -> None:
        """Called by the Tailer when new events arrive — refreshes sidebar, reloads current turn."""
        self.query_one(TurnIndex).refresh_turns()
        cp = self.query_one(ContentPane)
        if cp._current_turn is not None:
            cp.force_load_turn(cp._current_turn)
            self.query_one(KPIBar)._update_kpis(cp._current_turn)
        else:
            turns = self._store.get_turn_numbers()
            if turns:
                cp.load_turn(turns[0])
                self.query_one(KPIBar)._update_kpis(turns[0])

        # Refresh sim manager live log
        if self._sim_queue is not None:
            self.query_one(SimManagerPane).refresh_sims()

        # Refresh branch KPI compare table so it updates live during a running sim
        try:
            self.query_one(BranchPane)._refresh_compare()
        except Exception:
            pass

        # Refresh tags pane if it is active
        try:
            ap = self.query_one(TagsPane)
            if ap.has_class("--active"):
                ap.refresh_tags()
        except Exception:
            pass

    # ── Pane switching ────────────────────────────────────────────────────

    def _switch_pane(self, pane: str) -> None:
        """Show one content pane and hide the others."""
        mapping = {
            "events":   "#pane-events",
            "branches": "#pane-branches",
            "sims":     "#pane-sims",
            "tasks":    "#pane-tasks",
            "tags":     "#pane-tags",
            "skills":   "#pane-skills",
            "config":   "#pane-config",
        }
        for w in self.query(".main-pane"):
            w.remove_class("--active")
        target = mapping.get(pane)
        if target:
            self.query_one(target).add_class("--active")
        try:
            self.query_one(PaneNavBar).set_active(pane)
        except Exception:
            pass

    def action_switch_branches(self) -> None:
        self._switch_pane("branches")

    def action_switch_sims(self) -> None:
        self._switch_pane("sims")
        # Auto-select the running sim (if any) when entering the pane
        try:
            self.query_one(SimManagerPane).select_first_running()
        except Exception:
            pass

    def action_switch_tasks(self) -> None:
        self._switch_pane("tasks")

    def action_switch_tags(self) -> None:
        self._switch_pane("tags")
        try:
            ap = self.query_one(TagsPane)
            ap.set_store(self._store)
            ap.refresh_tags()
        except Exception:
            pass

    def action_switch_skills(self) -> None:
        self._switch_pane("skills")
        try:
            sp = self.query_one(SkillsPane)
            if self._skill_store is not None:
                sp.set_store(self._skill_store)
            sp.refresh_skills()
        except Exception:
            pass

    def action_switch_provider_config(self) -> None:
        self._switch_pane("config")
        try:
            pcp = self.query_one(ProviderConfigPane)
            if self._provider_config_store is not None:
                pcp.set_store(self._provider_config_store)
            pcp.refresh_providers()
        except Exception:
            pass

    def on_provider_config_changed(self, message: ProviderConfigChanged) -> None:
        """Update the active analysis model when the user changes provider config."""
        self._analysis_model = message.store.active_config.model

    def on_pane_nav_selected(self, message: PaneNavSelected) -> None:
        self._switch_pane(message.pane)

    # ── Turn / phase navigation ───────────────────────────────────────────

    def on_turn_selected(self, message: TurnSelected) -> None:
        """Route sidebar turn selection to content pane and KPI bar."""
        self._switch_pane("events")
        self._navigate_to_turn(message.turn)

    def on_phase_selected(self, message: PhaseSelected) -> None:
        """Route sidebar phase selection to content pane scroll."""
        self._switch_pane("events")
        cp = self.query_one(ContentPane)
        cp.force_load_turn(message.turn)
        self.query_one(KPIBar)._update_kpis(message.turn)
        cp.scroll_to_group(message.group)

    # ── Search ────────────────────────────────────────────────────────────

    def action_toggle_search(self) -> None:
        self.query_one(SearchBar).toggle()

    def action_open_search_modal(self) -> None:
        def _on_dismiss(turn: int | None) -> None:
            if turn is not None:
                self._switch_pane("events")
                self._navigate_to_turn(turn)

        self.push_screen(SearchModal(self._store), _on_dismiss)

    def on_search_submitted(self, message: SearchSubmitted) -> None:
        results = self._store.search(message.query, limit=1)
        if results:
            self._switch_pane("events")
            self._navigate_to_turn(results[0].turn_number)

    # ── Event card interactions ───────────────────────────────────────────

    def on_event_card_clicked(self, message: EventCardClicked) -> None:
        self.log(f"Event clicked: {message.event_id} (turn {message.turn_number})")

    def on_event_card_double_clicked(self, message: EventCardDoubleClicked) -> None:
        """Open the edit modal; on commit create a branch and activate it."""
        if self._branch_store is None:
            self.notify(
                "No branch manifest — open a file with branches enabled (Ctrl+B)",
                severity="warning",
            )
            return

        primary = message.event
        # Find the counterparty's LLM_DECISION in the same turn/phase (if any).
        peer_event = self._find_peer_event(primary)

        # Fork at the later event so both A and B decisions are included.
        if peer_event is not None and peer_event.sequence_number > primary.sequence_number:
            fork_event_id = peer_event.id
        else:
            fork_event_id = primary.id

        def _on_commit(result: EditResult | None) -> None:
            if result is None:
                return
            entry = self._branch_store.create_branch(  # type: ignore[union-attr]
                parent_branch_id=self._active_branch_id,
                parent_event_id=fork_event_id,
                label=result.branch_label,
                annotation=result.branch_annotation,
                edited_event=result.edited_event.model_dump(mode="json"),
                peer_edited_event=(
                    result.peer_edited_event.model_dump(mode="json")
                    if result.peer_edited_event is not None
                    else None
                ),
            )
            self.query_one(BranchPane).refresh_pane(self._branch_store)
            self._activate_branch(entry.id)
            # Stay on branches pane so user can review the new branch metadata
            self._switch_pane("branches")

        self.push_screen(EditEventModal(primary, peer_event=peer_event), _on_commit)

    def _find_peer_event(self, event: "GameEvent") -> "GameEvent | None":
        """Return the counterparty's LLM_DECISION event in the same turn/phase.

        Matches by the ``side`` field in ``structured_data`` ("A" or "B") rather
        than by ``source_detail``, which stores the model name string at runtime.
        """
        from slopr.models import EventType

        sd = event.structured_data or {}
        side = sd.get("side")
        if side not in ("A", "B"):
            return None
        peer_side = "B" if side == "A" else "A"

        candidates = [
            e for e in self._store.get_events(turn=event.turn_number, limit=100)
            if e.event_type == EventType.LLM_DECISION
            and e.phase == event.phase
            and (e.structured_data or {}).get("side") == peer_side
        ]
        return candidates[0] if candidates else None

    def on_event_card_right_clicked(self, message: EventCardRightClicked) -> None:
        """Show the skill context menu for the right-clicked event."""
        from textual.geometry import Offset
        from slopr.analysis import applicable_commands
        from slopr.skill_store import BUILTIN_SKILLS

        # Use SkillStore if available, fall back to built-ins
        if self._skill_store is not None:
            skills = self._skill_store.applicable_skills(message.event)
        else:
            skills = applicable_commands(message.event)
        if not skills:
            return

        offset = Offset(message.screen_x, message.screen_y)

        def _on_skill(skill_id: str | None) -> None:
            if skill_id is not None:
                asyncio.get_event_loop().create_task(
                    self._run_skill(skill_id, message.event)
                )

        self.push_screen(ContextMenuScreen(skills, offset), _on_skill)

    async def _run_skill(self, skill_id: str, focal_event: "GameEvent") -> None:
        """Submit the skill call to the Tasks pane (no blocking modal)."""
        from slopr.analysis import BUILTIN_SKILLS, run_skill
        from slopr.skill_store import BUILTIN_SKILLS as _BS

        # Look up skill from skill store first, then builtins
        skill = None
        if self._skill_store is not None:
            skill = self._skill_store.get(skill_id)
        if skill is None:
            skill = next((s for s in BUILTIN_SKILLS if s.id == skill_id), None)
        if skill is None:
            return

        # Gather a few context events from the same turn
        context = [
            e for e in self._store.get_events(turn=focal_event.turn_number, limit=50)
            if e.id != focal_event.id
        ][:8]

        # Derive model + sampling params from the active provider config (if available).
        if self._provider_config_store is not None:
            _cfg = self._provider_config_store.active_config
            _model       = _cfg.model
            _max_tokens  = _cfg.max_tokens
            _temperature = _cfg.temperature
            _thinking    = _cfg.thinking
        else:
            _model       = self._analysis_model
            _max_tokens  = 1024
            _temperature = 1.0
            _thinking    = "none"

        coro = run_skill(
            skill, focal_event, context,
            model=_model,
            max_tokens=_max_tokens,
            temperature=_temperature,
            thinking=_thinking,
        )

        def _on_done(task: TaskEntry) -> None:
            if task.result:
                self._save_tag(  # type: ignore[union-attr]
                    focal_event, skill.label, task.result, task,
                    skill_glyph=skill.glyph,
                )

        tasks_pane = self.query_one(TasksPane)
        tasks_pane.add_task(
            skill_label=skill.label,
            event_title=focal_event.title or focal_event.event_type.value,
            model=_model,
            coro=coro,
            on_done=_on_done,
        )
        self._switch_pane("tasks")
        self.notify(f"Skill started: {skill.label}", timeout=2)

    def _save_tag(
        self,
        parent_event: "GameEvent",
        skill_label: str,
        body: str,
        task_entry: "TaskEntry | None" = None,
        skill_glyph: str = "",
    ) -> None:
        """Write a TAG event to the active store and refresh the turn."""
        from slopr.models import EventSource, EventType, GameEvent as _GameEvent

        sd: dict = {"parent_event_id": parent_event.id}
        if skill_glyph:
            sd["skill_glyph"] = skill_glyph
        if task_entry is not None:
            sd.update({
                "task_id": task_entry.task_id,
                "task_label": task_entry.skill_label,
                "model": task_entry.model,
                "input_tokens": task_entry.input_tokens,
                "output_tokens": task_entry.output_tokens,
            })

        seq = self._store.get_latest_sequence() + 1
        tag = _GameEvent(
            sequence_number=seq,
            turn_number=parent_event.turn_number,
            phase=parent_event.phase,
            event_type=EventType.TAG,
            source=EventSource.HUMAN,
            source_detail="analysis",
            parent_id=parent_event.id,
            title=f"[{skill_label}]",
            body=body,
            structured_data=sd,
        )
        try:
            self._store.append_event(tag)
        except Exception as exc:
            self.notify(f"Could not save tag: {exc}", severity="error")
            return

        # Reload the current turn to show the new tag badge
        cp = self.query_one(ContentPane)
        current = cp._current_turn
        if current is not None:
            cp._current_turn = None  # force reload
            cp.load_turn(current)

        # Refresh turn sidebar so "†" indicator appears
        try:
            from slopr.widgets.turn_sidebar import TurnIndex
            self.query_one(TurnIndex).refresh_turns()
        except Exception:
            pass

        self.notify("Tag saved.", severity="information")

    # ── KPI bar ───────────────────────────────────────────────────────────

    def on_kpibar_clicked(self, message: KPIBarClicked) -> None:
        kpi_bar = self.query_one(KPIBar)

        def _on_dismiss(turn: int | None) -> None:
            if turn is not None:
                self._navigate_to_turn(turn)

        self.push_screen(KPIPanel(self._store, kpi_bar._current_turn), _on_dismiss)

    # ── Branch messages ───────────────────────────────────────────────────

    def on_branch_activated(self, message: BranchActivated) -> None:
        self._activate_branch(message.branch_id)

    def on_branch_sim_requested(self, message: BranchSimRequested) -> None:
        asyncio.get_event_loop().create_task(
            self._spawn_branch_sim(message.branch_id, message.sim_kwargs)
        )

    def on_branch_edited(self, message: BranchEdited) -> None:
        """Apply label/annotation/event edits and optionally reset the branch to its fork."""
        if self._branch_store is None:
            return
        self._branch_store.update_branch(
            message.branch_id,
            label=message.label,
            annotation=message.annotation,
            event_title=message.event_title or None,
            event_body=message.event_body or None,
        )
        if message.reset_to_fork:
            self._branch_store.reset_branch_to_fork(message.branch_id)
        self.query_one(BranchPane).refresh_pane(self._branch_store)

    def on_branch_deleted(self, message: BranchDeleted) -> None:
        if self._branch_store is None:
            return
        self._branch_store.delete_branch(message.branch_id)
        if self._active_branch_id == message.branch_id:
            self._activate_branch(None)
        self.query_one(BranchPane).refresh_pane(self._branch_store)

    # ── Sim manager messages ──────────────────────────────────────────────

    def on_sim_cancel_requested(self, message: SimCancelRequested) -> None:
        """Update queue status after cancel (SIGTERM already sent by pane)."""
        if self._sim_queue is not None:
            self._sim_queue.update(message.request_id, status=SimStatus.FAILED)
            self.query_one(SimManagerPane).refresh_sims()

    def on_sim_retry_requested(self, message: SimRetryRequested) -> None:
        """Re-spawn a failed sim with the same configuration."""
        if self._sim_queue is None or self._branch_store is None:
            return
        req = self._sim_queue.get(message.request_id)
        if req is None:
            return
        sim_kwargs = {
            "model_a": req.model_a,
            "model_b": req.model_b,
            "turns":   req.turns,
        }
        asyncio.get_event_loop().create_task(
            self._spawn_branch_sim(req.branch_id, sim_kwargs)
        )

    # ── Branch activation ─────────────────────────────────────────────────

    def _activate_branch(self, branch_id: str | None) -> None:
        """Switch the content pane, sidebar, and KPI bar to the given branch store."""
        if self._branch_store is None:
            return

        self._active_branch_id = branch_id
        self._branch_tailer = None

        new_store = self._branch_store.get_store(branch_id)
        # Reload from disk so we pick up any events written since last load
        # (e.g. edited events patched in by create_branch, or a sim in progress).
        new_store.reload()
        self._store = new_store

        sidebar = self.query_one(TurnSidebar)
        sidebar._store = new_store
        turn_index = sidebar.query_one(TurnIndex)
        turn_index._store = new_store

        # Compute edited IDs for this branch (used for ~ glyph on phase leaves)
        edited_ids: set[str] = set()
        if branch_id is not None and self._branch_store is not None:
            try:
                entry = self._branch_store.get_entry(branch_id)
                if entry.edited_event and entry.edited_event.get("parent_id"):
                    edited_ids.add(entry.edited_event["parent_id"])
                if entry.peer_edited_event and entry.peer_edited_event.get("parent_id"):
                    edited_ids.add(entry.peer_edited_event["parent_id"])
            except KeyError:
                pass
        turn_index._branch_edited_ids = edited_ids
        turn_index.refresh_turns()

        cp = self.query_one(ContentPane)
        cp._store = new_store

        try:
            ap = self.query_one(TagsPane)
            ap.set_store(new_store)
            if ap.has_class("--active"):
                ap.refresh_tags()
        except Exception:
            pass

        kpi = self.query_one(KPIBar)
        kpi._store = new_store

        turns = new_store.get_turn_numbers()
        if turns:
            cp.force_load_turn(turns[0])
            kpi._update_kpis(turns[0])

        branch_path = self._branch_store.get_jsonl_path(branch_id)
        if branch_path.exists():
            from slopr.tail import Tailer

            self._branch_tailer = Tailer(
                branch_path,
                new_store,
                on_new_events=self._on_new_events,
            )
            if self._poll_timer is None:
                self._poll_timer = self.set_interval(0.1, self._poll_tail)

    # ── Background simulation spawning ────────────────────────────────────

    async def _spawn_branch_sim(self, branch_id: str, sim_kwargs: dict) -> None:
        """Spawn a background sim.py process for *branch_id* and live-tail output."""
        if self._branch_store is None:
            return

        entry = self._branch_store.get_entry(branch_id)

        # Register in SimQueue
        req = None
        if self._sim_queue is not None:
            req = self._sim_queue.add(
                branch_id=branch_id,
                branch_label=entry.label,
                scenario="(branch)",
                model_a=sim_kwargs.get("model_a", "claude-sonnet-4-6"),
                model_b=sim_kwargs.get("model_b", "gpt-5.2"),
                turns=int(sim_kwargs.get("turns", 15)),
            )
            sp = self.query_one(SimManagerPane)
            sp.refresh_sims()

        try:
            proc = await self._branch_store.spawn_sim(
                branch_id,
                model_a=sim_kwargs.get("model_a", "claude-sonnet-4-6"),
                model_b=sim_kwargs.get("model_b", "gpt-5.2"),
                turns=int(sim_kwargs.get("turns", 15)),
            )
        except Exception as exc:
            self.notify(f"Failed to spawn sim: {exc}", severity="error")
            if req is not None and self._sim_queue is not None:
                self._sim_queue.update(req.id, status=SimStatus.FAILED)
                self.query_one(SimManagerPane).refresh_sims()
            return

        if req is not None and self._sim_queue is not None:
            self._sim_queue.update(req.id, status=SimStatus.RUNNING, pid=proc.pid)
            sp = self.query_one(SimManagerPane)
            sp.refresh_sims()
            sp.select_request(req.id)

        self.query_one(BranchPane).refresh_pane(self._branch_store)
        self._activate_branch(branch_id)
        self._switch_pane("sims")
        self.notify(f"Sim started (pid {proc.pid}): {entry.label}")

        await proc.wait()

        final_status = (
            BranchStatus.COMPLETE if proc.returncode == 0 else BranchStatus.FAILED
        )
        self._branch_store.update_status(branch_id, final_status)

        if req is not None and self._sim_queue is not None:
            sim_final = SimStatus.COMPLETE if proc.returncode == 0 else SimStatus.FAILED
            # Determine the last turn that was written to the branch JSONL
            last_turn: int | None = None
            try:
                branch_store = self._branch_store.get_store(branch_id)
                branch_store.reload()
                turns = branch_store.get_turn_numbers()
                if turns:
                    last_turn = turns[-1]
            except Exception:
                pass
            self._sim_queue.update(req.id, status=sim_final, current_turn=last_turn)
            self.query_one(SimManagerPane).refresh_sims()

        self.query_one(BranchPane).refresh_pane(self._branch_store)

        entry = self._branch_store.get_entry(branch_id)
        severity = "information" if proc.returncode == 0 else "error"
        self.notify(f"Sim {final_status.value}: {entry.label}", severity=severity)

    # ── Navigation helpers ────────────────────────────────────────────────

    def _navigate_to_turn(self, turn: int) -> None:
        self.query_one(ContentPane).force_load_turn(turn)
        self.query_one(KPIBar)._update_kpis(turn)

    async def action_quit(self) -> None:
        if self._poll_timer is not None:
            self._poll_timer.stop()
        self.exit()
