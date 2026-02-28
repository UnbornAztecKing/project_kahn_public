"""Tests for slopr.analysis — skills, prompt building, and tag persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from slopr.analysis import (
    BUILTIN_SKILLS,
    Skill,
    _context_block,
    _format_event,
    _render_prompt,
    applicable_commands,
)
# Backward-compat aliases still importable
from slopr.analysis import COMMANDS, AnalysisCommand
from slopr.models import EventSource, EventType, GameEvent
from slopr.store import JSONLEventStore


# ── Helpers ───────────────────────────────────────────────────────────────────


def _evt(
    seq: int,
    turn: int = 1,
    phase: str = "",
    event_type: EventType = EventType.LLM_DECISION,
    **kw: object,
) -> GameEvent:
    defaults: dict = {
        "sequence_number": seq,
        "turn_number": turn,
        "event_type": event_type,
        "source": EventSource.LLM,
        "phase": phase,
        "title": f"Event {seq}",
        "body": f"Body {seq}",
    }
    defaults.update(kw)
    return GameEvent(**defaults)


# ── applicable_commands (backward compat) ─────────────────────────────────────


class TestApplicableCommands:
    """applicable_commands() filters by event phase."""

    def test_analyze_event_returned_for_all_phases(self) -> None:
        for phase in ("action", "signal", "reflection", "forecast", "profiles", ""):
            event = _evt(1, phase=phase)
            ids = [c.id for c in applicable_commands(event)]
            assert "analyze_event" in ids, f"analyze_event missing for phase={phase!r}"

    def test_counterfactual_returned_for_all_phases(self) -> None:
        for phase in ("action", "signal", "reflection", "forecast", ""):
            event = _evt(1, phase=phase)
            ids = [c.id for c in applicable_commands(event)]
            assert "counterfactual" in ids

    def test_escalation_risk_returned_for_action(self) -> None:
        event = _evt(1, phase="action")
        ids = [c.id for c in applicable_commands(event)]
        assert "escalation_risk" in ids

    def test_escalation_risk_returned_for_signal(self) -> None:
        event = _evt(1, phase="signal")
        ids = [c.id for c in applicable_commands(event)]
        assert "escalation_risk" in ids

    def test_escalation_risk_not_returned_for_profiles(self) -> None:
        event = _evt(1, phase="profiles")
        ids = [c.id for c in applicable_commands(event)]
        assert "escalation_risk" not in ids

    def test_leader_psychology_returned_for_reflection(self) -> None:
        event = _evt(1, phase="reflection")
        ids = [c.id for c in applicable_commands(event)]
        assert "leader_psychology" in ids

    def test_leader_psychology_not_returned_for_action(self) -> None:
        event = _evt(1, phase="action")
        ids = [c.id for c in applicable_commands(event)]
        assert "leader_psychology" not in ids

    def test_compare_ab_returned_for_action(self) -> None:
        event = _evt(1, phase="action")
        ids = [c.id for c in applicable_commands(event)]
        assert "compare_ab" in ids

    def test_compare_ab_not_returned_for_scenario(self) -> None:
        event = _evt(1, phase="scenario")
        ids = [c.id for c in applicable_commands(event)]
        assert "compare_ab" not in ids

    def test_returns_list_of_skills(self) -> None:
        event = _evt(1, phase="action")
        result = applicable_commands(event)
        assert all(isinstance(c, Skill) for c in result)

    def test_empty_phase_treated_as_no_filter(self) -> None:
        """Events with empty phase should still return phase-unrestricted commands."""
        event = _evt(1, phase="")
        result = applicable_commands(event)
        unrestricted = [c for c in BUILTIN_SKILLS if not c.applicable_phases]
        assert len(result) == len(unrestricted)

    def test_commands_alias_equals_builtin_skills(self) -> None:
        """COMMANDS is a backward-compat alias for BUILTIN_SKILLS."""
        assert COMMANDS is BUILTIN_SKILLS

    def test_analysis_command_alias(self) -> None:
        """AnalysisCommand is a backward-compat alias for Skill."""
        assert AnalysisCommand is Skill


# ── _render_prompt ────────────────────────────────────────────────────────────


def _get_skill(skill_id: str) -> Skill:
    """Retrieve a built-in skill by id for testing."""
    return next(s for s in BUILTIN_SKILLS if s.id == skill_id)


class TestRenderPrompt:
    """_render_prompt() includes focal event data and skill-specific framing."""

    def test_analyze_event_includes_title(self) -> None:
        event = _evt(1, phase="action", title="Launch strike")
        skill = _get_skill("analyze_event")
        prompt = _render_prompt(skill, _format_event(event), _context_block([]))
        assert "Launch strike" in prompt

    def test_escalation_risk_mentions_escalation(self) -> None:
        event = _evt(1, phase="action")
        skill = _get_skill("escalation_risk")
        prompt = _render_prompt(skill, _format_event(event), _context_block([]))
        assert "escalat" in prompt.lower()

    def test_compare_ab_mentions_actors(self) -> None:
        event = _evt(1, phase="signal")
        skill = _get_skill("compare_ab")
        prompt = _render_prompt(skill, _format_event(event), _context_block([]))
        assert "Actor A" in prompt or "Actor B" in prompt

    def test_counterfactual_asks_for_alternative(self) -> None:
        event = _evt(1, phase="action")
        skill = _get_skill("counterfactual")
        prompt = _render_prompt(skill, _format_event(event), _context_block([]))
        assert "alternative" in prompt.lower() or "different" in prompt.lower()

    def test_leader_psychology_mentions_leader(self) -> None:
        event = _evt(1, phase="reflection")
        skill = _get_skill("leader_psychology")
        prompt = _render_prompt(skill, _format_event(event), _context_block([]))
        assert "leader" in prompt.lower() or "psychology" in prompt.lower()

    def test_context_events_included(self) -> None:
        focal = _evt(5, phase="action")
        ctx = [_evt(i, phase="action", title=f"Context {i}") for i in range(1, 4)]
        skill = _get_skill("analyze_event")
        prompt = _render_prompt(skill, _format_event(focal), _context_block(ctx))
        assert "Context 1" in prompt
        assert "Context 2" in prompt

    def test_body_truncated_at_800_chars(self) -> None:
        long_body = "X" * 1000
        event = _evt(1, body=long_body)
        skill = _get_skill("analyze_event")
        prompt = _render_prompt(skill, _format_event(event), _context_block([]))
        # Prompt should contain the start of the body but be truncated
        assert "X" * 800 in prompt
        assert "…" in prompt


# ── store.append_event + get_tags_for ────────────────────────────────────────


class TestStoreTags:
    """append_event() persists events and get_tags_for() retrieves them."""

    def _write_store(self, tmp_path: Path, n: int = 3) -> tuple[Path, JSONLEventStore]:
        path = tmp_path / "game.jsonl"
        events = [
            _evt(i, turn=1, event_type=EventType.SITUATION_REPORT)
            for i in range(1, n + 1)
        ]
        with open(path, "w") as fh:
            for e in events:
                fh.write(e.model_dump_json() + "\n")
        store = JSONLEventStore(path)
        return path, store

    def test_append_event_persists_to_file(self, tmp_path: Path) -> None:
        path, store = self._write_store(tmp_path)
        original_count = store.event_count()

        tag = GameEvent(
            sequence_number=original_count + 1,
            turn_number=1,
            event_type=EventType.TAG,
            source=EventSource.HUMAN,
            title="[Test tag]",
            body="Analysis result.",
        )
        store.append_event(tag)

        # Reload from disk to verify persistence
        reloaded = JSONLEventStore(path)
        assert reloaded.event_count() == original_count + 1
        found = reloaded.get_event(tag.id)
        assert found is not None
        assert found.event_type == EventType.TAG

    def test_append_event_updates_in_memory_index(self, tmp_path: Path) -> None:
        path, store = self._write_store(tmp_path)
        original_count = store.event_count()

        tag = GameEvent(
            sequence_number=original_count + 1,
            turn_number=1,
            event_type=EventType.TAG,
            source=EventSource.HUMAN,
            title="[In-memory]",
            body="",
        )
        store.append_event(tag)

        assert store.event_count() == original_count + 1
        assert store.get_event(tag.id) is not None

    def test_get_tags_for_returns_matching(self, tmp_path: Path) -> None:
        path, store = self._write_store(tmp_path, n=2)
        events = store.get_events(turn=1, limit=10)
        parent_x = events[0]
        parent_y = events[1]

        seq = store.get_latest_sequence()
        for i in range(2):
            seq += 1
            store.append_event(GameEvent(
                sequence_number=seq,
                turn_number=1,
                event_type=EventType.TAG,
                source=EventSource.HUMAN,
                parent_id=parent_x.id,
                title=f"[Tag X {i}]",
                body="",
            ))

        seq += 1
        store.append_event(GameEvent(
            sequence_number=seq,
            turn_number=1,
            event_type=EventType.TAG,
            source=EventSource.HUMAN,
            parent_id=parent_y.id,
            title="[Tag Y]",
            body="",
        ))

        tags_x = store.get_tags_for(parent_x.id)
        tags_y = store.get_tags_for(parent_y.id)

        assert len(tags_x) == 2
        assert len(tags_y) == 1
        assert all(a.parent_id == parent_x.id for a in tags_x)
        assert tags_y[0].parent_id == parent_y.id

    def test_get_tags_for_returns_empty_when_none(self, tmp_path: Path) -> None:
        path, store = self._write_store(tmp_path)
        events = store.get_events(turn=1, limit=5)
        result = store.get_tags_for(events[0].id)
        assert result == []

    def test_get_tags_for_returns_legacy_annotations(self, tmp_path: Path) -> None:
        """Legacy ANNOTATION events are returned by get_tags_for for backward compat."""
        path, store = self._write_store(tmp_path, n=1)
        parent = store.get_events(turn=1, limit=5)[0]

        seq = store.get_latest_sequence() + 1
        store.append_event(GameEvent(
            sequence_number=seq,
            turn_number=1,
            event_type=EventType.ANNOTATION,  # legacy type
            source=EventSource.HUMAN,
            parent_id=parent.id,
            title="[Legacy]",
            body="",
        ))

        result = store.get_tags_for(parent.id)
        assert len(result) == 1
        assert result[0].event_type == EventType.ANNOTATION

    def test_append_event_raises_without_backing_path(self) -> None:
        store = JSONLEventStore()  # no path
        tag = GameEvent(
            sequence_number=1,
            turn_number=1,
            event_type=EventType.TAG,
            source=EventSource.HUMAN,
            title="[No path]",
            body="",
        )
        with pytest.raises(RuntimeError, match="no backing path"):
            store.append_event(tag)
