"""Headless tests for skill execution via slopr.analysis.run_skill.

Tests monkeypatch _sync_run so no real API call is made.  Each test
verifies that:
  - the correct prompt template is rendered and passed to the backend
  - the returned tuple (prompt, result, meta) is wired through correctly
  - all five built-in skills work for at least one applicable phase
  - inapplicable skills are excluded by applicable_commands / applicable_skills
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

import slopr.analysis as analysis_mod
from slopr.analysis import (
    BUILTIN_SKILLS,
    _render_prompt,
    _format_event,
    _context_block,
    applicable_commands,
    applicable_skills,
    run_skill,
)
from slopr.models import EventSource, EventType, GameEvent


# ── Helpers ───────────────────────────────────────────────────────────────────


def _evt(
    seq: int = 1,
    turn: int = 1,
    phase: str = "action",
    event_type: EventType = EventType.LLM_DECISION,
    title: str = "Test Event",
    body: str = "Test body.",
) -> GameEvent:
    return GameEvent(
        sequence_number=seq,
        turn_number=turn,
        event_type=event_type,
        source=EventSource.LLM,
        phase=phase,
        title=title,
        body=body,
    )


def _get_skill(skill_id: str):
    return next(s for s in BUILTIN_SKILLS if s.id == skill_id)


def _fake_sync_run(
    skill_id: str,
    prompt: str,
    model: str,
    max_tokens: int = 1024,
    temperature: float = 1.0,
    thinking: str = "none",
):
    """Mock backend — echoes prompt and returns canned metadata."""
    return (
        prompt,
        f"[MOCK RESULT for {skill_id}]",
        {"input_tokens": 42, "output_tokens": 7},
    )


# ── run_skill — core contract ─────────────────────────────────────────────────


class TestRunSkillContract:
    """run_skill() correctly wires prompt → backend → result tuple."""

    def test_returns_three_tuple(self):
        skill = _get_skill("analyze_event")
        event = _evt(phase="action")
        with patch.object(analysis_mod, "_sync_run", side_effect=_fake_sync_run):
            prompt, result, meta = asyncio.run(
                run_skill(skill, event, [], model="test-model")
            )
        assert isinstance(prompt, str)
        assert isinstance(result, str)
        assert isinstance(meta, dict)

    def test_prompt_contains_focal_event_title(self):
        skill = _get_skill("analyze_event")
        event = _evt(title="Nuclear Launch Detected", phase="action")
        with patch.object(analysis_mod, "_sync_run", side_effect=_fake_sync_run):
            prompt, _, _ = asyncio.run(
                run_skill(skill, event, [], model="test-model")
            )
        assert "Nuclear Launch Detected" in prompt

    def test_prompt_contains_context_event_title(self):
        skill = _get_skill("analyze_event")
        focal = _evt(seq=5, title="Focal Event", phase="action")
        ctx = [_evt(seq=i, title=f"Context {i}", phase="action") for i in range(1, 4)]
        with patch.object(analysis_mod, "_sync_run", side_effect=_fake_sync_run):
            prompt, _, _ = asyncio.run(
                run_skill(skill, focal, ctx, model="test-model")
            )
        assert "Context 1" in prompt
        assert "Context 2" in prompt

    def test_result_comes_from_backend(self):
        skill = _get_skill("analyze_event")
        event = _evt()
        with patch.object(analysis_mod, "_sync_run", side_effect=_fake_sync_run):
            _, result, _ = asyncio.run(
                run_skill(skill, event, [], model="test-model")
            )
        assert "[MOCK RESULT for analyze_event]" in result

    def test_meta_tokens_forwarded(self):
        skill = _get_skill("analyze_event")
        event = _evt()
        with patch.object(analysis_mod, "_sync_run", side_effect=_fake_sync_run):
            _, _, meta = asyncio.run(
                run_skill(skill, event, [], model="test-model")
            )
        assert meta["input_tokens"] == 42
        assert meta["output_tokens"] == 7

    def test_model_forwarded_to_backend(self):
        skill = _get_skill("analyze_event")
        event = _evt()
        received_models = []

        def capture(skill_id, prompt, model, max_tokens=1024, temperature=1.0, thinking="none"):
            received_models.append(model)
            return _fake_sync_run(skill_id, prompt, model)

        with patch.object(analysis_mod, "_sync_run", side_effect=capture):
            asyncio.run(run_skill(skill, event, [], model="claude-haiku-4-5"))
        assert received_models == ["claude-haiku-4-5"]


# ── Each built-in skill executes for its applicable phases ────────────────────


_SKILL_PHASE_SAMPLES = [
    ("analyze_event",      "action"),
    ("analyze_event",      "signal"),
    ("analyze_event",      "reflection"),
    ("analyze_event",      "forecast"),
    ("compare_ab",         "action"),
    ("compare_ab",         "signal"),
    ("compare_ab",         "forecast"),
    ("compare_ab",         "reflection"),
    ("escalation_risk",    "action"),
    ("escalation_risk",    "signal"),
    ("leader_psychology",  "reflection"),
    ("leader_psychology",  "forecast"),
    ("counterfactual",     "action"),
    ("counterfactual",     "signal"),
]


@pytest.mark.parametrize("skill_id,phase", _SKILL_PHASE_SAMPLES)
def test_skill_executes_for_phase(skill_id: str, phase: str):
    """Each skill runs without error for each of its applicable phases."""
    skill = _get_skill(skill_id)
    event = _evt(phase=phase)
    with patch.object(analysis_mod, "_sync_run", side_effect=_fake_sync_run):
        prompt, result, meta = asyncio.run(
            run_skill(skill, event, [], model="test-model")
        )
    assert prompt  # non-empty prompt was built
    assert result == f"[MOCK RESULT for {skill_id}]"
    assert "input_tokens" in meta


# ── Phase applicability filtering ─────────────────────────────────────────────


class TestSkillPhaseFiltering:
    """applicable_commands() and applicable_skills() honour phase restrictions."""

    def test_escalation_risk_excluded_from_reflection(self):
        event = _evt(phase="reflection")
        ids = [s.id for s in applicable_commands(event)]
        assert "escalation_risk" not in ids

    def test_escalation_risk_excluded_from_scenario(self):
        event = _evt(phase="scenario")
        ids = [s.id for s in applicable_commands(event)]
        assert "escalation_risk" not in ids

    def test_leader_psychology_excluded_from_action(self):
        event = _evt(phase="action")
        ids = [s.id for s in applicable_commands(event)]
        assert "leader_psychology" not in ids

    def test_compare_ab_excluded_from_scenario(self):
        event = _evt(phase="scenario")
        ids = [s.id for s in applicable_commands(event)]
        assert "compare_ab" not in ids

    def test_analyze_event_applies_to_all_phases(self):
        for phase in ("action", "signal", "reflection", "forecast", "scenario", "profiles", ""):
            event = _evt(phase=phase)
            ids = [s.id for s in applicable_commands(event)]
            assert "analyze_event" in ids, f"analyze_event missing for phase={phase!r}"

    def test_counterfactual_applies_to_all_phases(self):
        for phase in ("action", "signal", "reflection", "forecast", ""):
            event = _evt(phase=phase)
            ids = [s.id for s in applicable_commands(event)]
            assert "counterfactual" in ids

    def test_applicable_skills_with_custom_list(self):
        """applicable_skills() filters an arbitrary skill list, not just builtins."""
        from slopr.skill_store import Skill
        custom = [
            Skill(
                id="custom_action_only",
                label="Action only",
                applicable_phases=["action"],
                prompt_template="Test {event_block} {context_block}",
                builtin=False,
            )
        ]
        event_action = _evt(phase="action")
        event_signal = _evt(phase="signal")
        assert len(applicable_skills(event_action, custom)) == 1
        assert len(applicable_skills(event_signal, custom)) == 0


# ── Prompt content per skill ──────────────────────────────────────────────────


class TestSkillPromptContent:
    """Each skill's prompt template contains skill-specific framing."""

    def _prompt(self, skill_id: str, phase: str = "action") -> str:
        skill = _get_skill(skill_id)
        event = _evt(phase=phase)
        return _render_prompt(skill, _format_event(event), _context_block([]))

    def test_escalation_prompt_mentions_escalation(self):
        prompt = self._prompt("escalation_risk", "action")
        assert "escalat" in prompt.lower()

    def test_escalation_prompt_mentions_risk_rating(self):
        prompt = self._prompt("escalation_risk", "action")
        assert "Low" in prompt or "Medium" in prompt or "High" in prompt

    def test_compare_ab_prompt_mentions_actor_a_and_b(self):
        prompt = self._prompt("compare_ab", "action")
        assert "Actor A" in prompt and "Actor B" in prompt

    def test_leader_psychology_prompt_mentions_leader(self):
        prompt = self._prompt("leader_psychology", "reflection")
        assert "leader" in prompt.lower() or "psychology" in prompt.lower()

    def test_counterfactual_prompt_mentions_alternative(self):
        prompt = self._prompt("counterfactual", "action")
        assert "alternative" in prompt.lower() or "different" in prompt.lower()

    def test_analyze_event_prompt_mentions_strategy(self):
        prompt = self._prompt("analyze_event", "action")
        assert "strategic" in prompt.lower() or "intentions" in prompt.lower()


# ── run_skill with structured_data in focal event ────────────────────────────


class TestRunSkillWithStructuredData:
    """Events with structured_data have that data included in the prompt."""

    def test_structured_data_included_in_prompt(self):
        skill = _get_skill("analyze_event")
        event = GameEvent(
            sequence_number=1,
            turn_number=2,
            event_type=EventType.KPI_UPDATE,
            source=EventSource.LLM,
            phase="action",
            title="KPI Update",
            body="",
            structured_data={"a_action_value": 0.85, "b_action_value": 0.3},
        )
        with patch.object(analysis_mod, "_sync_run", side_effect=_fake_sync_run):
            prompt, _, _ = asyncio.run(
                run_skill(skill, event, [], model="test-model")
            )
        assert "a_action_value" in prompt or "0.85" in prompt

    def test_long_body_truncated_in_prompt(self):
        skill = _get_skill("analyze_event")
        event = _evt(body="Z" * 1000, phase="action")
        with patch.object(analysis_mod, "_sync_run", side_effect=_fake_sync_run):
            prompt, _, _ = asyncio.run(
                run_skill(skill, event, [], model="test-model")
            )
        assert "Z" * 800 in prompt
        assert "…" in prompt
        # Confirm body is truncated (not full 1000 chars present as a block)
        assert "Z" * 801 not in prompt
